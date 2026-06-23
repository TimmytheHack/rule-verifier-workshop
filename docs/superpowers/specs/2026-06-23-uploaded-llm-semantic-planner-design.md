# Uploaded Dataset LLM Semantic Planner First 设计

## 背景

当前重构已经引入 reviewed semantic capability、`SemanticIntent`、verified SQL、`RankingPlan`、`EvidencePack` 和 uploaded dataset flow。但普通 uploaded admissions 查询仍然先经过 regex / admissions 专用 planner；DeepSeek 只有在 deterministic extractor 缺槽时才作为 fallback 调用。

这导致旧 hardcode 路径继续吞掉典型问题，例如“广东物化生，10000名，列出冲稳保”或“排位15000，想读人工智能、计算机，留广东”。系统虽然能回答，但 `token_usage` 为 0，说明 LLM semantic planner 没有参与主链路。

## 目标

把 uploaded dataset / reviewed domain pack 的默认自然语言查询入口改为 LLM semantic planner first：

```text
用户问题
-> DeepSeekSemanticIntentExtractor
-> SemanticIntent verifier / QueryAST builder
-> SQLBuilder
-> DuckDBExecutor
-> EvidencePack
-> AnswerGenerator
```

核心不变：

```text
LLM proposes.
System verifies.
SQL executes.
EvidencePack constrains answer.
```

## 非目标

- 不把 built-in legacy admissions demo 一次性切到 LLM first。
- 不允许 DeepSeek 生成 SQL、hard rules、approved ops 或最终候选 item。
- 不让 LLM 直接执行推荐排序。
- 不绕过 reviewed mapping、`RuleVerifier`、`RankingVerifier`、DuckDB fingerprint guard 或 `WorkbenchResponse` contract。
- 不把 raw Excel 行传给 LLM planner。

## 范围

本次只覆盖 `DatasetService.query()` 进入的 uploaded dataset flow，且 domain pack 已审核通过。

默认行为：

- uploaded dataset + approved admissions domain + `ENABLE_LLM=true` + DeepSeek key 可用：
  - 先调用 `DeepSeekSemanticIntentExtractor`。
  - `SemanticIntent` 经过系统校验后才构造 verified QueryAST。
  - 若 LLM 输出无法验证，返回 blocked / needs_confirmation / candidate-only，不静默执行未验证偏好。
- uploaded dataset + LLM 不可用：
  - 明确降级到 deterministic fallback。
  - `EvidencePack` 记录 `planner_mode=fallback_regex` 和降级原因。
- built-in admissions demo：
  - 暂时保持现有行为，避免一次改动影响 legacy demo、前端默认样例和旧验收。

## 组件设计

### PlannerMode

新增或扩展 Workbench 配置字段：

```text
planner_mode:
  auto
  llm_semantic
  regex_fallback
```

`DatasetService.query()` 对 uploaded approved domain 默认传 `planner_mode=auto`。

`auto` 规则：

- 如果是 uploaded dataset 且 LLM 可用，选择 `llm_semantic`。
- 如果 LLM 不可用，选择 `regex_fallback`，并记录降级原因。
- 如果是 built-in legacy admissions，则保持现有路径。

### LLM Semantic Planner

`DeepSeekSemanticIntentExtractor` 仍只输出候选 `SemanticIntent`：

- `query_type`
- `user_context`
- `preferences`
- `requested_output`
- `usage`
- `raw_payload` 的安全摘要

输出必须经过现有 Pydantic model 校验，并且公开响应不得泄漏 forbidden payload。

### Intent Verification

系统根据 reviewed mapping 验证 `SemanticIntent`：

- 字段存在且 reviewed 才能进入 QueryAST。
- operator 在字段白名单内才可执行。
- 值必须来自用户输入、reviewed value index 或确认边界。
- 缺字段偏好进入 `not_executed_preferences`。
- 模糊偏好进入 confirmation candidate 或 explanation-only。

### Admissions Major Rank

“广东物化生，10000名，列出冲稳保”仍可以走 `admissions_major_rank`，但 query type 应由 LLM `SemanticIntent` 提出，再由系统验证。

执行仍使用当前确定性逻辑：

- 使用 2025。
- 使用 `科类=物理类/物理`。
- 使用 `最低位次` 作为专业最低录取排名。
- SQL 先按年份、科类、位次窗口召回。
- SQL 后确定性过滤 `选科要求`，物化生满足化学、生物相关要求。
- 输出冲 10、稳 13、保 10。

### Semantic Recommendation

“排位15000，想读人工智能、计算机，不想去国外，留广东”走 `semantic_recommendation`：

- LLM 提出 `major_name contains_any ["人工智能","计算机"]`。
- LLM 提出 `school_province in ["广东"]`。
- LLM 提出 `school_country_or_region not_in [...]`。
- 系统验证前两项可执行。
- `school_country_or_region` 缺字段，必须进入 `not_executed_preferences`。
- 没有 verified `RankingPlan` 时只能输出 candidate list，不能声称推荐排序。

### Score Without Rank

“630分，没有排位”仍返回 `needs_confirmation`。

允许 LLM 提取 `user_score=630`，但系统不得用分数估算风险；必须要求广东省排位/位次。

## EvidencePack 要求

EvidencePack 必须新增或明确以下字段：

```json
{
  "planner": {
    "mode": "llm_semantic",
    "provider": "deepseek",
    "called": true,
    "fallback_used": false,
    "token_usage": {
      "prompt_tokens": 0,
      "completion_tokens": 0,
      "total_tokens": 0
    }
  },
  "semantic_intent": {
    "query_type": "semantic_recommendation",
    "user_context": {},
    "preferences": []
  },
  "verified_intents": [],
  "rejected_intents": []
}
```

公开响应中的 `token_usage.extractor.total_tokens` 必须能反映真实 DeepSeek 调用。单元测试可以使用 fake client 返回非零 token；live probe 可以调用真实 DeepSeek。

## 错误处理

- DeepSeek 网络失败：
  - 如果 `planner_mode=llm_semantic`，返回 `blocked`，说明 LLM planner 不可用。
  - 如果 `planner_mode=auto`，可降级到 regex fallback，但必须在 EvidencePack 记录 `fallback_used=true` 和错误类型摘要。
- LLM 输出 schema 不合法：
  - 不执行 SQL。
  - 返回 `blocked` 或 `needs_confirmation`。
  - 不把原始非法 payload 暴露给前端。
- LLM 输出 unsupported preference：
  - 保存为 rejected / not executed，不执行。

## 测试策略

单元测试使用 fake DeepSeek client，不依赖真实 API：

- uploaded admissions 普通查询默认触发 LLM planner。
- `token_usage.extractor.total_tokens > 0`。
- `SemanticIntent` 出现在 EvidencePack。
- verified intent 才生成 SQL。
- unsupported intent 进入 `not_executed_preferences`。
- 分数无排位返回 `needs_confirmation`。
- DeepSeek 输出 SQL payload 时被拒绝且 public response 不泄漏。

集成测试使用现有 uploaded admissions fixture：

- “广东物化生，10000名，列出冲稳保...”返回 ok。
- 结果包含冲 10、稳 13、保 10。
- “排位15000，想读人工智能、计算机...”返回 ok 或 candidate list。
- “不想去国外”保留为 not executed。

live probe：

- `scripts/run_semantic_capability_probe.py --live-llm` 必须输出 planner usage。
- 真实 DeepSeek 成功时 token usage 非零。
- 失败时输出降级或 blocked 原因。

## 验收标准

- 同一份 uploaded Excel 和同一提示词，普通 query 不需要手动传 `semantic_intent`。
- 在 LLM 可用时，uploaded query 真实调用 DeepSeek，`token_usage.extractor.total_tokens > 0`。
- Q1 能返回冲稳保 33 条，且记录使用 2025、物理类、化学/生物选科过滤、专业最低位次。
- Q2 能返回候选列表，且明确没有 verified `RankingPlan` 时不声称推荐排序。
- Q2 的“不想去国外”因缺少已审核字段而不执行。
- Q3 只有分数没有排位时返回 `needs_confirmation`。
- 所有 SQL 仍由 verified QueryAST 生成，不接受 raw SQL。
- 完整测试通过。

