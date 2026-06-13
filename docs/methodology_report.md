# 方法论报告：偏好到规则验证

## 1. 项目定位

本项目是一个 research-engineering 方法论项目，不是普通的高考志愿推荐 bot。

当前案例是基于结构化 Excel 数据的广东高考志愿填报场景。核心研究问题是：

```text
当用户用自然语言表达偏好时，系统如何判断哪些部分可以安全编译为 deterministic executable rules，哪些部分需要人类确认，哪些部分只能保留为语义信息或由 LLM 辅助解释？
```

主要贡献是防止把模糊自然语言偏好不安全地提升为确定性可执行规则。

系统不应该直接给出推荐列表，除非它能解释：

- 哪些用户偏好变成了可执行规则；
- 哪些偏好需要确认；
- 哪些偏好因为 schema 不支持而不能执行；
- 每条返回结果为什么满足已验证规则。

## 2. 为什么这不是推荐 Bot

普通推荐 bot 的目标是直接给出有用建议。本项目研究的是推荐之前的步骤：

```text
natural-language preference -> verified executable rule set
```

当前系统不生成完整志愿表，不按学校声誉排序，不预测就业结果，也不做宽泛的录取判断。它关注的是：一个偏好是否能落到真实数据字段上，并被安全执行。

这个区别很重要，因为模糊表达一旦被静默转换成精确过滤条件，就可能产生误导。例如：

```text
学校稳一点
```

不应该自动变成：

```text
录取概率 = 高
```

或：

```text
safety_level = 稳妥
```

除非系统有 schema-grounded rule，并且用户确认了这种解释。

## 3. 最低可执行信息

志愿填报系统的第一步不是推荐，而是检查是否具备最低可执行信息：考生位次、科类、批次、目标数据字段和用户偏好边界。缺少这些信息时，系统应该追问或标记不可执行，而不是让 LLM 直接生成建议。

对广东场景，最小 user gate 是：

```text
生源地 = 广东
科类 = 物理 / 历史
位次 = user_rank
批次 = 本科 / 专科 / 提前批等
```

其中位次比分数更重要。不同年份分数线波动大，位次更适合和往年录取数据比较。如果用户只给分数没有给位次，系统应该追问：

```text
请提供你的省排名/位次。仅凭分数无法稳定判断风险。
```

数据集的最低可执行字段包括：

```text
院校名称
院校代码
院校专业组代码
专业名称
专业代码
科类
批次
城市
计划人数
学费
往年最低分
往年最低位次
专业组最低位次
选科要求
本科/专科
公私性质
院校标签 / 院校水平
```

广东尤其不能只输出学校名，因为很多判断发生在“院校专业组 + 专业”层面。合格输出至少应包含：

```text
院校名称
院校专业组代码
专业名称
城市
学费
专业组最低位次
专业最低位次 / 如果有
安全边际
```

风险判断需要 `user_rank`、往年专业组最低位次、专业最低位次、招生计划人数、是否新增专业或专业组、以及近两年/三年录取趋势。当前 MVP 只使用 `专业组最低位次1`，这可以演示 rule verification，但方法论必须承认限制：只用一年位次不够稳，更完整系统应该使用 2-3 年最低位次、计划人数变化、是否新增等信息。

用户偏好分三类处理：

| 类型 | 示例 | 处理方式 |
|---|---|---|
| Deterministic | `学费两万以内`、`城市在广州深圳`、`专业名称包含计算机` | 字段存在且值边界明确时可以执行。 |
| Candidate | `稳一点`、`太贵`、`计算机相关`、`学校好一点`、`离家近` | 需要确认阈值、集合、代理指标或家庭城市。 |
| LLM/external/reference only | `就业前景好`、`学校氛围好`、`宿舍条件好`、`专业未来趋势`、`城市发展潜力` | 没有对应字段时不能执行，只能解释、标记外部信息需求或保留为参考。 |

最终自然语言答案也有最低要求：说明执行了哪些规则、哪些规则需要确认、哪些偏好没有执行、筛选出多少结果、展示前若干结果、每个结果为什么保留、风险提醒，以及下一步需要用户补充什么。

这些分类被记录在 `rules/information_requirements.json` 中，作为方法论和可执行规则之间的审查边界。

## 4. 方法论 Pipeline

当前方法论是：

```text
Natural-language input
-> preference decomposition
-> rule class assignment
-> schema grounding
-> rule verification
-> human confirmation
-> candidate promotion or rejection
-> executable rule set
-> backend-specific query execution
-> result trace
-> evidence pack
-> answer/report generation
-> evaluation
```

核心原则：

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
No trace, no verified result.
No evidence pack, no final answer.
Neural proposes; symbolic verifies and executes.
```

升级后的实现还在 `rules/rule_lifecycle_schema.json` 中记录了 rule lifecycle 边界：

```text
extracted_preference
-> proposed_rule
-> schema_grounded_rule
-> verified_rule
-> confirmed_rule
-> executable_rule
-> executed_rule
-> traced_result
-> evidence_pack
-> generated_answer
```

这个 lifecycle 很重要，因为它区分了 extractor 提出了什么，以及 verifier 最终允许什么执行。

答案层必须位于 trace 之后。它不读取 raw Excel，也不判断 executability。它只接收
evidence pack，字段包括：

- `user_request`；
- `executed_rules`；
- `candidate_confirmations`；
- `not_executed_preferences`；
- `result_count`；
- `top_k_results`；
- `trace_summary`。

`TemplateReportBuilder` 根据 evidence pack 确定性生成中文答案。可选的
`DeepSeekAnswerGenerator` 也只能接收同一个 evidence pack。由于 LLM 可能省略
必要字段，DeepSeek 路径会追加一段确定性的证据覆盖清单，补齐已执行规则、前若干
专业组结果、未执行偏好和安全说明。

答案层的最小结果形状包括 `院校名称`、`院校专业组代码`、`专业代码`、`专业名称`、
`专业全称`、`城市`、`学费`、`专业组最低位次`、可用时的 `专业最低位次` 和
safety margin。`专业代码` 与 `专业全称` 必须保留，因为两条结果可能共享同一学校、
同一专业组代码和同一个短专业名，但实际对应不同培养方向。

实现中还增加了 attribute-level grounding audit，放在 rule construction 之前：

```text
extracted attributes
-> attribute grounding audit
-> rule construction
-> rule verification
```

这意味着抽取出来的 attributes 默认不等于可执行。它们必须先被标记为：

| Attribute status | 含义 |
|---|---|
| `schema_grounded` | 能映射到当前 Excel schema 字段，但仍需要 rule verification。 |
| `confirmable` | 能映射到字段，但表达模糊或语义化，需要用户确认。 |
| `context_only` | 只作为上下文或公式输入，不能作为 Excel filter。 |
| `missing_schema` | 当前没有对应 Excel 字段，不能执行。 |
| `ignored_not_schema_mapped` | extractor 输出了未知属性，rule construction 会忽略。 |

这样可以补上一个重要缺口：extractor 可以提到 `公办`、`学校名气`、`偏远城市` 等属性，但只要它们没有 grounded 到 Excel schema，就不能成为 executable rules。

## 5. 规则分类

### 确定性规则

确定性规则是明确的、schema-grounded、类型安全、可直接执行的规则。

MVP 示例：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
学费 <= 20000
```

当字段存在、操作符允许，并且用户表达足够明确时，exact keyword match 或明确数值边界可以作为 deterministic rule。比如 `学费两万以内` 可以归一化为 `学费 <= 20000`；但 `太贵` 没有明确阈值，仍然是 candidate。

### 候选规则

候选规则是对模糊偏好的可能操作化解释。它们必须在用户确认后才能执行。

示例：

```text
稳一点 -> 选择 safety margin：5%、10% 或 15%
太贵 -> 选择学费上限
计算机相关 -> 确认是否包含 软件工程、人工智能、数据科学、网络安全
学校好一点 -> 确认是否使用某个排名/标签来源，或不执行
```

候选规则在 promotion 之前必须被阻止执行。

### 需要 LLM 或不可执行的部分

这类部分是当前 schema 无法安全支持的偏好。

示例：

```text
不要中外合作
```

当前 Excel schema 没有专门的 `cooperation_type` 字段。因此系统会保留这个偏好，但不会执行它。

MVP 也不会从自由文本字段中推断 `cooperation_type`。未来可以考虑这种派生字段，但前提是先建立并验证结构化字段。

## 6. 当前 Demo

输入：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

抽取偏好：

```json
{
  "source_province": "广东",
  "subject_type": "物理",
  "user_rank": 32000,
  "major_keyword": "计算机",
  "preferred_cities": ["广州", "深圳"],
  "risk_preference_raw": "稳一点",
  "tuition_preference_raw": "太贵",
  "cooperation_preference_raw": "不想去太贵的中外合作"
}
```

模拟确认：

```text
稳一点 -> safety margin = 10%
太贵 -> tuition cap = 20000
计算机相关扩展 -> false
```

最终可执行规则：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

阈值 `35200` 来自：

```text
32000 * 1.10 = 35200
```

当前 workbook 运行结果是 93 条过滤结果。

## 7. Schema Registry 是系统边界

Schema registry 定义系统可以执行什么。一个规则只有在字段存在于 registry 且通过 verification 后，才能成为 deterministic rule。

Attribute extraction 可以比 executable schema 更宽，但 execution 不可以。每个 extracted slot 都必须先经过 schema boundary audit，再进入 rule construction。

当前 MVP 使用的真实 Excel 字段包括：

```text
生源地
科类
专业名称
城市
专业组最低位次1
学费
```

当前还没有进入 MVP active schema registry 的字段包括：

```text
cooperation_type
school_ownership
school_reputation
employment_outlook
distance_from_home
major_family
major_popularity
city_remoteness
```

其中一部分概念已经在 schema profile 中找到了 Excel 候选列：

- `school_ownership` 可能映射到 `公私性质`。
- `school_reputation` 可能部分映射到 `院校水平`、`院校标签`、`院校排名` 或 `软科排名`。
- `city_remoteness` 或城市质量可能部分映射到 `城市水平标签`。
- `major_popularity` 需要额外策略判断；`专业类` 或 `专业水平` 不等同于“热门/冷门”。

这些字段不能自动执行。它们需要人工 schema review、allowed operators、语义说明和测试后，才能进入 active schema registry。

## 8. 后端抽象

Excel 只是第一个 case study。方法论将 rule verification 和 data execution 分离。

后端抽象是：

| 组件 | 职责 |
|---|---|
| Data Adapter | 加载数据源，并暴露真实字段。 |
| Schema Registry | 定义字段、类型、别名、允许操作符、nullable 和 notes。 |
| Backend-specific Query Compiler | 将 verified rules 编译成 pandas、SQL、MongoDB 或 API 查询形式。 |
| Executor | 在对应 backend 上执行规则。 |
| Result Trace | 解释每条结果由哪些规则产生。 |
| Evidence Pack | 将已验证规则、确认记录、未执行偏好、top results 和 trace summary 打包给答案层。 |
| Report Builder / Answer Generator | 只根据 evidence pack 生成最终答案。 |

当前 executor：

```text
DuckDB executor for verified hard rules
pandas executor for legacy MVP demos, evaluation comparison, and focused tests
```

未来 executor 可以包括：

```text
SQL / DuckDB compiler
MongoDB compiler
API executor for tool-backed data
```

非结构化文本和 PDF 不能被确定性执行，除非先抽取并验证结构化 schema。

Workbench API 启动执行前会先做 data warehouse fingerprint guard：

- DuckDB `__metadata` 必须存在，并记录源 Excel fingerprint。
- `schema_value_index.json` 必须记录同一个源 Excel fingerprint。
- 当前源 Excel 的 fingerprint 必须同时匹配 DuckDB metadata 和 schema/value index metadata。
- row count / column count metadata 不一致时也会阻断执行。
- guard 未通过时返回 structured warning，不静默回退到 raw Excel / pandas execution。

`scripts/build_data_warehouse.py` 负责重建 DuckDB、schema/value index，并输出 `outputs/data/ingestion_summary.json`，其中包含 source path、fingerprint、row/column count、field profiles 和 created_at。

Workbench 的 confirmation loop 也属于执行边界：

- `value_index_audit` 为 `partial_match` 的候选只返回系统生成的 `candidate_id` 和已审查候选值。
- 用户确认只能引用上一轮返回的 `candidate_id`，不能把二次输入文本直接变成 SQL 条件。
- 后端会根据当前 query 重新生成候选；伪造、过期或不属于当前 query 的 `candidate_id` 会被拒绝。
- 已确认 candidate 会重新经过规则形状检查，然后才编译成参数化 DuckDB SQL。
- `no_schema_field` 偏好即使被用户确认也不执行，例如当前没有合作办学类型字段时，`校企合作` / `中外合作` 只能保留为未执行偏好。
- EvidencePack 会记录 `confirmed_rules`、`confirmation_source`、`executed_after_confirmation`、`unconfirmed_candidates` 和 `no_schema_field_preferences`。

## 9. LLM 边界

可选 DeepSeek extractor 只用于 preference extraction 和 source spans。

允许的 LLM 角色：

- 抽取 user context；
- 抽取 preference slots；
- 保留 source spans；
- 提出 candidate interpretations。
- 根据 verified evidence pack 生成答案文案。

不允许的 LLM 角色：

- 提升 candidate rules；
- 验证 schema 是否存在；
- 决定最终 executability；
- 编译查询；
- 执行 deterministic filters；
- 声称缺失字段存在。
- 在答案生成阶段读取 raw Excel；
- 添加 evidence pack 中没有的录取、就业、中外合作、宿舍或学校质量事实。

所有 DeepSeek 输出都必须经过和 regex 输出相同的 rule classifier 和 symbolic verifier。

对于答案生成，DeepSeek 输出只被视为 prose。系统会追加确定性的 evidence
coverage，保证最终答案即使在模型省略字段时，仍包含 verified rules、top
results、未执行偏好和安全说明。

## 10. 规则验证协议

每条可执行规则必须通过：

- field existence check；
- source column existence check；
- type check；
- operator check；
- value normalization check；
- ambiguity check；
- data coverage check；
- conflict check；
- dry-run check；
- traceability check。

Verification output 必须解释规则为什么可执行、被阻止、或等待确认。

现在 verifier 输出的是 verification profile，而不只是 pass/fail：

```json
{
  "schema_grounded": true,
  "field_exists": true,
  "source_column_exists": true,
  "operator_allowed": true,
  "type_valid": true,
  "value_present": true,
  "value_normalized": true,
  "ambiguity_level": "none",
  "requires_human_confirmation": false,
  "execution_level": "executable",
  "executable": true
}
```

关键 execution levels：

| Execution level | 含义 |
|---|---|
| `executable` | deterministic、schema-grounded，可以执行。 |
| `confirmable` | schema-grounded，但模糊或需要确认。 |
| `context_only` | 只是上下文，不是数据过滤规则。 |
| `blocked` | 已 grounded，但当前不能执行。 |
| `rejected` | 没有 schema grounding。 |

## 11. 评估摘要

当前评估比较的是 token budget 下的 task success。

单条 MVP 输入：

| 方法 | 结果行数 | Task success | Total tokens | Over-promotion |
|---|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | 93 | 5/5 | 0 | 0 |
| `deepseek_extractor_symbolic_verifier` | 93 | 5/5 | 834 | 0 |
| `llm_only_baseline` | n/a | 1/5 | 818 | unsafe |
| `schema_aware_llm_only_baseline` | n/a | 1/5 | 1282 | unsafe |

40 条模糊输入评估：

| 方法 | 得分 | 成功率 | Total tokens | Over-promotion rate |
|---|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 1.000 | 0 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 1.000 | 25334 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.535 | 24388 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.780 | 42916 | 0.275 |

当前 benchmark 文件包含 40 条分层输入，覆盖 clear、vague、unsupported、mixed、adversarial、contradictory 和 end-to-end demo cases。DeepSeek extractor 上一轮是 `314/320`；加入多专业词、更多城市归一化和学校性质偏好保留后，达到 `320/320`。这个提升来自更好的 slot representation，不是放宽 verifier。

当前 baseline comparison 包括：

| 方法 | 目的 |
|---|---|
| `llm_only_baseline` | 朴素 LLM-only rule proposal。 |
| `schema_aware_llm_only_baseline` | 更强的 LLM-only baseline，能看到 schema context，但仍没有 symbolic verifier。 |
| `deepseek_extractor_symbolic_verifier` | LLM extraction + symbolic verification。 |
| `regex_extractor_symbolic_verifier` | 保守 symbolic extraction baseline。 |

Pipeline token budget 对比：

| 方案 | 估算/输入 tokens | 结果 |
|---|---:|---|
| Direct LLM with full Excel | 23,040,523 | 未执行；超过现实上下文预算。 |
| Direct LLM with MVP columns only | 483,922 | 仍然很大，并且缺少 deterministic verification。 |
| DeepSeek extractor + symbolic verifier | 834 | 93 rows, 5/5。 |
| Regex extractor + symbolic verifier | 0 | 93 rows, 5/5。 |
| Schema-aware LLM-only baseline | 1282 | 1/5；仍然 unsafe。 |

答案层评估：

| 答案模式 | 输入边界 | 预期结果 |
|---|---|---|
| `llm_only_schema_sample` | 用户请求、schema summary、sample projected rows | 对照组；因为没有 verified executed rules、未执行偏好状态和 trace summary，通常失败。 |
| `pipeline_template` | 只使用 verified evidence pack | 5/5 evidence alignment；不使用 LLM。 |
| `pipeline_deepseek_evidence` | 只使用 verified evidence pack | 追加确定性 evidence coverage 后达到 5/5 evidence alignment。 |

答案层 scoring 检查结果总数、已执行规则、top projected professional-group
results、未执行偏好，以及 unsupported claims。Unsupported 指没有 verified
evidence pack 支持，不等于 raw Excel workbook 中一定不存在。

目前最强的证据不是 LLM 没有用，而是：当 symbolic verification 控制执行时，LLM extraction 会更安全。

## 12. 当前局限性

当前系统仍然很窄。

局限性：

- 评估集规模较小。
- Regex extraction 针对当前 examples 人工整理。
- DeepSeek extraction 还没有大规模 stress test。
- Human confirmation 是模拟的。
- 系统只使用一个广东招生数据集；Workbench hard rules 通过 DuckDB executor 执行，pandas executor 仅保留为 MVP demo、评估对照和测试工具。
- Workbench 依赖 DuckDB metadata、schema/value index metadata 和源 Excel fingerprint 一致性校验，校验失败时阻断执行并返回 structured warning。
- 不生成完整志愿表。
- 不评价学校声誉。
- 不预测就业结果。
- 不从文本字段推断 `cooperation_type`。
- Direct Excel prompting 的 token 估算是近似值。

这些限制在当前研究阶段是可以接受的，因为目标是 rule verification methodology，不是完整 advisor 产品。

## 13. 下一步方法论工作

下一步应聚焦评估和安全性：

- 如果继续收集到新的真实表达，将 `eval_inputs.jsonl` 从当前 40 条继续扩展。
- 增加 safety、cost、major family、location、school quality、employment 等表达的 paraphrases。
- 将 deterministic over-promotion rate 作为主要安全指标。
- 单独统计 schema hallucination rate。
- 增加 per-rule trace completeness scoring。
- 增加 unsupported but tempting fields 的 adversarial inputs。
- 测试 DeepSeek extraction 在不完整、矛盾输入中的稳定性。
- 将 40-case benchmark 继续扩展到 50-100 条真实改写表达。
- 压测 `320/320` DeepSeek 结果在更长、更乱、矛盾输入下是否仍然稳定。
- 将 recommendation quality evaluation 和 rule verification evaluation 分开。

## 14. 泛化意义

该方法论可以泛化到其他用户用自然语言表达结构化偏好的决策系统：

- 选课；
- 租房筛选；
- 求职筛选；
- 商品推荐；
- 投资筛选；
- 奖学金或项目匹配。

可复用的不是广东高考的具体规则，而是这个边界：

```text
自然语言可以提出结构，但只有通过验证且基于 schema 接地的规则可以执行。
```
