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

## 3. 方法论 Pipeline

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
-> evaluation
```

核心原则：

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
No trace, no verified result.
Neural proposes; symbolic verifies and executes.
```

## 4. 规则分类

### Deterministic Rules

Deterministic rules 是明确的、schema-grounded、类型安全、可直接执行的规则。

MVP 示例：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
```

当字段存在、操作符允许，并且用户表达足够明确时，exact keyword match 可以作为 deterministic rule。

### Candidate Rules

Candidate rules 是对模糊偏好的可能操作化解释。它们必须在用户确认后才能执行。

示例：

```text
稳一点 -> 选择 safety margin：5%、10% 或 15%
太贵 -> 选择学费上限
计算机相关 -> 确认是否包含 软件工程、人工智能、数据科学、网络安全
学校好一点 -> 确认是否使用某个排名/标签来源，或不执行
```

Candidate rules 在 promotion 之前必须被阻止执行。

### LLM-Needed Or Non-Executable Parts

LLM-needed 或 non-executable parts 是当前 schema 无法安全支持的偏好。

示例：

```text
不要中外合作
```

当前 Excel schema 没有专门的 `cooperation_type` 字段。因此系统会保留这个偏好，但不会执行它。

MVP 也不会从自由文本字段中推断 `cooperation_type`。未来可以考虑这种派生字段，但前提是先建立并验证结构化字段。

## 5. 当前 Demo

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

## 6. Schema Registry 是系统边界

Schema registry 定义系统可以执行什么。一个规则只有在字段存在于 registry 且通过 verification 后，才能成为 deterministic rule。

当前 MVP 使用的真实 Excel 字段包括：

```text
生源地
科类
专业名称
城市
专业组最低位次1
学费
```

缺失但希望未来支持的字段包括：

```text
cooperation_type
school_reputation
employment_outlook
distance_from_home
major_family
```

这些字段可能有价值，但在它们成为结构化、可验证 schema 字段之前，不能被执行。

## 7. Backend Abstraction

Excel 只是第一个 case study。方法论将 rule verification 和 data execution 分离。

Backend abstraction 是：

| 组件 | 职责 |
|---|---|
| Data Adapter | 加载数据源，并暴露真实字段。 |
| Schema Registry | 定义字段、类型、别名、允许操作符、nullable 和 notes。 |
| Backend-specific Query Compiler | 将 verified rules 编译成 pandas、SQL、MongoDB 或 API 查询形式。 |
| Executor | 在对应 backend 上执行规则。 |
| Result Trace | 解释每条结果由哪些规则产生。 |

当前 executor：

```text
pandas executor for Excel/CSV
```

未来 executor 可以包括：

```text
SQL / DuckDB compiler
MongoDB compiler
API executor for tool-backed data
```

非结构化文本和 PDF 不能被确定性执行，除非先抽取并验证结构化 schema。

## 8. LLM 边界

可选 DeepSeek extractor 只用于 preference extraction 和 source spans。

允许的 LLM 角色：

- 抽取 user context；
- 抽取 preference slots；
- 保留 source spans；
- 提出 candidate interpretations。

不允许的 LLM 角色：

- 提升 candidate rules；
- 验证 schema 是否存在；
- 决定最终 executability；
- 编译查询；
- 执行 deterministic filters；
- 声称缺失字段存在。

所有 DeepSeek 输出都必须经过和 regex 输出相同的 rule classifier 和 symbolic verifier。

## 9. Rule Verification Protocol

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

## 10. 评估摘要

当前评估比较的是 token budget 下的 task success。

单条 MVP 输入：

| 方法 | 结果行数 | Task success | Total tokens |
|---|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | 93 | 5/5 | 0 |
| `deepseek_extractor_symbolic_verifier` | 93 | 5/5 | 762 |
| `llm_only_baseline` | n/a | 1/5 | 810 |

10 条模糊输入评估：

| 方法 | 得分 | 成功率 | Total tokens |
|---|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 70/70 | 1.00 | 0 |
| `deepseek_extractor_symbolic_verifier` | 70/70 | 1.00 | 5075 |
| `llm_only_baseline` | 31/50 | 0.62 | 5329 |

Pipeline token budget 对比：

| 方案 | 估算/输入 tokens | 结果 |
|---|---:|---|
| Direct LLM with full Excel | 23,040,523 | 未执行；超过现实上下文预算。 |
| Direct LLM with MVP columns only | 483,922 | 仍然很大，并且缺少 deterministic verification。 |
| DeepSeek extractor + symbolic verifier | 762 | 93 rows, 5/5。 |
| Regex extractor + symbolic verifier | 0 | 93 rows, 5/5。 |

目前最强的证据不是 LLM 没有用，而是：当 symbolic verification 控制执行时，LLM extraction 会更安全。

## 11. 当前局限性

当前系统仍然很窄。

局限性：

- 评估集规模较小。
- Regex extraction 针对当前 examples 人工整理。
- DeepSeek extraction 还没有大规模 stress test。
- Human confirmation 是模拟的。
- 系统只使用一个 Excel dataset 和 pandas executor。
- 不生成完整志愿表。
- 不评价学校声誉。
- 不预测就业结果。
- 不从文本字段推断 `cooperation_type`。
- Direct Excel prompting 的 token 估算是近似值。

这些限制在当前研究阶段是可以接受的，因为目标是 rule verification methodology，不是完整 advisor 产品。

## 12. 下一步方法论工作

下一步应聚焦评估和安全性：

- 将 `eval_inputs.jsonl` 扩展到 30-50 条输入。
- 增加 safety、cost、major family、location、school quality、employment 等表达的 paraphrases。
- 将 deterministic over-promotion rate 作为主要安全指标。
- 单独统计 schema hallucination rate。
- 增加 per-rule trace completeness scoring。
- 增加 unsupported but tempting fields 的 adversarial inputs。
- 测试 DeepSeek extraction 在不完整、矛盾输入中的稳定性。
- 将 recommendation quality evaluation 和 rule verification evaluation 分开。

## 13. 泛化意义

该方法论可以泛化到其他用户用自然语言表达结构化偏好的决策系统：

- 选课；
- 租房筛选；
- 求职筛选；
- 商品推荐；
- 投资筛选；
- 奖学金或项目匹配。

可复用的不是广东高考的具体规则，而是这个边界：

```text
Natural language may propose structure, but only verified schema-grounded rules may execute.
```
