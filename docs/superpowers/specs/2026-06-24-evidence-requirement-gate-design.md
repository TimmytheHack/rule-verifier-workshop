# Evidence Requirement Gate 设计

## 背景

当前 uploaded admissions 的 LLM semantic recommendation 已经形成安全链路：

```text
DeepSeekSemanticIntentExtractor
-> PreferenceGrounder
-> SemanticQueryVerifier
-> SemanticSQLBuilder
-> DuckDB candidates
-> DeepSeekRankingPlanGenerator
-> RankingVerifier
-> GenericRankingEngine
-> EvidencePack
-> AnswerGenerator
```

这条链路已经禁止 LLM 生成 SQL、直接排序或新增候选 row。但 `EvidenceRequirementClassifier`
仍未进入主链路，导致 LLM 抽取出的 preference 会先进入 grounding 语境，再由后续 verifier
排除。对于 recommendation 场景，这个顺序不够理想：`学校好一点`、`好就业`、`计算机相关`、
`稳一点`、`不想去国外` 这类表达可能分别需要 reviewed field、reviewed KB、reviewed ranking
policy 或用户确认边界；它们应当在进入 SQL filter 和 RankingPlan 之前先被分流。

核心不变：

```text
LLM proposes.
System classifies evidence need.
System verifies executable structure.
EvidencePack constrains answer.
```

## 目标

第一版把 `EvidenceRequirementClassifier` 接入 uploaded admissions 的 LLM semantic
recommendation runtime，并放在 `DeepSeekSemanticIntentExtractor` 之后、`PreferenceGrounder`
之前：

```text
DeepSeekSemanticIntentExtractor
-> EvidenceRequirementClassifier
-> PreferenceGrounder
-> SemanticQueryVerifier
-> SemanticSQLBuilder
-> DuckDB candidates
-> DeepSeekRankingPlanGenerator
-> RankingVerifier
-> GenericRankingEngine
```

gate 的职责是按 evidence need 分流每个 LLM 抽取出的 preference：

- `table_field`：允许继续进入 `PreferenceGrounder`，但仍必须通过 reviewed mapping 和 verifier。
- `knowledge_base_or_reviewed_field`：当前没有 reviewed KB 或 reviewed field 时，不进入 SQL filter。
- `reviewed_ranking_policy`：当前没有 ranking policy registry 时，不进入 RankingPlan。
- `user_boundary`：需要用户确认边界，不进入 SQL filter 或 RankingPlan。
- `unsupported`：不可执行，不进入 SQL filter 或 RankingPlan。

被排除的 preference 必须写入 `not_executed_preferences`、`unanswerable_intents` 和
`EvidencePack` planner metadata。最终回答不得声称这些偏好已经被执行或支持。

## 非目标

- 不覆盖 `admissions_major_rank`。例如“广东物化生，10000名，列出冲稳保”保持现有确定性查询。
- 不覆盖 legacy admissions planner。
- 不覆盖手动 supplied `soft_preferences.semantic_intent` 的调试和回放路径。
- 不改 answer generation 边界；`TemplateReportBuilder` 和可选 LLM answer 仍只能读取 `EvidencePack`。
- 不实现 raw SQL 或通用 SQL planner。
- 不实现 reviewed KB ingestion、检索、引用、验证闭环。
- 不实现 reviewed ranking policy registry。
- 不用 classifier 替代 `PreferenceGrounder`、`SemanticQueryVerifier` 或 `RankingVerifier`。

## 适用范围

gate 只在以下条件同时满足时强制运行：

- uploaded dataset；
- approved admissions domain pack；
- `planner_mode=auto` 或 `planner_mode=llm_semantic`；
- `DeepSeekSemanticIntentExtractor` 成功产出 `query_type=semantic_recommendation`；
- semantic intent 不是通过 `soft_preferences.semantic_intent` 手动 supplied。

`planner_mode=auto` 中，如果 classifier 调用失败或返回非法 payload，系统必须记录
`fallback_reason=evidence_requirement_classification_failed`。如果可以安全回到 legacy path，则走
legacy fallback；如果是强制 `planner_mode=llm_semantic`，返回 `blocked`，不执行 semantic
recommendation SQL。

## 组件设计

### EvidenceRequirementGate

新增一个小的 runtime gate，职责是把 classifier 结果转成可执行 preference 子集和 evidence
annotations。它不构造 SQL，不验证字段，不判断最终 executability。

输入：

- 原始用户问题；
- LLM 产出的 `SemanticIntent`；
- reviewed `schema_context`；
- `SemanticQueryOptionsBuilder` 产出的 `query_options`。

输出：

- `filtered_intent`：保留允许进入后续 verifier 的 preference；
- `excluded_preferences`：需要 KB、ranking policy、用户边界或 unsupported 的 preference；
- `planner_trace`：classifier 是否调用、provider、usage、rejected requirements、fallback reason；
- `warnings` / `unanswerable_intents` 可用的结构化条目。

### Preference 匹配

classifier 的 `source_text` 来自用户原文片段，LLM intent preference 也有 `source_text`。
第一版匹配规则保持保守：

- 优先用完全相同的 `source_text` 匹配；
- 其次允许片段包含关系匹配；
- 无法可靠匹配的 requirement 只进入 evidence metadata，不删除 intent preference；
- 无法可靠分类的 intent preference 继续交给 `PreferenceGrounder` 和 verifier，而不是由 gate
  自行判定可执行。

这个规则避免 classifier 漏分或分段不一致时误删可执行偏好。安全边界仍由后续 verifier 把关。

### Filtering 规则

`table_field` requirement 不代表可执行，只代表可以继续进入系统 verifier。

以下类型必须从 `filtered_intent.preferences` 中移除：

- `knowledge_base_or_reviewed_field`；
- `reviewed_ranking_policy`；
- `user_boundary`；
- `unsupported`。

移除条目需要保留：

- `source_text`；
- `candidate_semantic` 或 intent preference semantic；
- `requirement_type`；
- `executable=false`；
- `reason`；
- `match_type=evidence_requirement_gate`。

### RankingPlan 输入

`DeepSeekRankingPlanGenerator` 必须接收 gate 后的 `filtered_intent`。这样需要外部证据、
reviewed ranking policy 或用户边界的 preference 不会出现在 RankingPlan prompt 中。

即使 LLM 仍返回不允许的 criterion，`RankingVerifier` 继续作为最终边界：

- 字段必须 reviewed；
- operation 必须允许；
- value evidence 必须可信；
- unsupported criterion 进入 `excluded_criteria`；
- `ranking.status` 不能被 classifier 直接改为 ranked。

### EvidencePack

`EvidencePack.planner` 增加 `evidence_requirements`：

```json
{
  "status": "classified",
  "provider": "deepseek",
  "called": true,
  "fallback_used": false,
  "token_usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  },
  "requirements": [],
  "excluded_preferences": [],
  "rejected_requirements": []
}
```

当 classifier 未调用时，节点可省略或记录 `status=not_applicable`。当 classifier 失败时，
`status=classification_failed`，并记录 `fallback_reason` 和安全摘要。

semantic recommendation 的 `execution_summary` 继续保留：

- `not_executed_preferences`；
- `verified_query_plan`；
- `ranking`；
- `selection_evidence`。

gate 排除的 preference 要合并进 `not_executed_preferences` 和 `unanswerable_intents`。
顶层 `unexecuted_preferences` / `no_schema_field_preferences` 也必须能展示这些未执行原因。

## 数据流

### 成功分类

```text
用户问题
-> DeepSeekSemanticIntentExtractor 产出 SemanticIntent
-> EvidenceRequirementClassifier 分类 intent preferences
-> EvidenceRequirementGate 移除非 table_field preference
-> PreferenceGrounder ground 剩余 preferences
-> SemanticQueryVerifier 验证 QueryAST
-> SemanticSQLBuilder 生成参数化 SQL
-> DuckDBExecutor 召回 bounded candidates
-> DeepSeekRankingPlanGenerator 基于 filtered_intent 生成候选 RankingPlan
-> RankingVerifier 验证 criteria
-> GenericRankingEngine 可选排序
-> EvidencePack 记录 gate、SQL、ranking 和 not executed evidence
```

### 分类失败

`planner_mode=llm_semantic`：

```text
分类失败
-> blocked
-> execution_summary.sql=""
-> EvidencePack.planner.evidence_requirements.status="classification_failed"
```

`planner_mode=auto`：

```text
分类失败
-> legacy fallback
-> EvidencePack.planner.prior_planner 记录 classification failure
```

## 回答边界

answer generator 仍然只看 `EvidencePack`。

回答可以说明：

- 哪些偏好进入了 verified SQL；
- 哪些偏好因需要 reviewed KB、reviewed field、ranking policy 或用户边界而未执行；
- 没有 verified `RankingPlan` 时，结果只是候选列表。

回答不得说明：

- `好就业` 已经被筛选；
- `学校好一点` 已经被排序；
- `不想去国外` 已经被执行，除非存在 reviewed field；
- classifier 的 rationale 是事实结论。

## 测试策略

单元测试使用 fake DeepSeek client，不调用真实 API。

必须新增失败优先测试：

- LLM intent 抽取 `major_name`、`school_province`、`employment_outlook`、`school_quality`，
  classifier 只允许前两项，SQL 只包含 allowed preferences。
- 被 gate 排除的 `好就业`、`学校好一点` 进入 `not_executed_preferences` 和
  `unanswerable_intents`。
- RankingPlan generator 接收的 intent 不包含被 gate 排除的 preference。
- `admissions_major_rank` 不调用 classifier。
- legacy planner 不调用 classifier。
- supplied `soft_preferences.semantic_intent` 不调用 classifier。
- classifier 返回 forbidden SQL payload 时，public response 不泄漏 SQL 文本。
- classifier 调用失败时，`planner_mode=llm_semantic` 返回 `blocked`。
- classifier 调用失败时，`planner_mode=auto` 记录 fallback reason 并走 legacy fallback。

回归测试：

- `python -m unittest discover -s tests` 必须通过。
- docs 中关于 semantic recommendation、RankingPlan 和 EvidencePack planner metadata 的描述同步更新。

## 验收标准

- uploaded admissions + LLM semantic recommendation 会强制运行 evidence requirement gate。
- 只有 `table_field` preference 可以进入 `PreferenceGrounder`，且仍受 verifier 约束。
- 需要 reviewed KB、reviewed ranking policy、用户边界或 unsupported 的 preference 不进入 SQL filter。
- `DeepSeekRankingPlanGenerator` 不接收被 gate 排除的 preference。
- `EvidencePack.planner.evidence_requirements` 能说明 classifier 调用状态和未执行原因。
- 顶层未执行偏好、`unanswerable_intents` 和 answer 文本与 gate 结果一致。
- `admissions_major_rank`、legacy planner、supplied semantic intent、answer generation 和通用 SQL planner
  行为保持不变。
