# 评估报告：偏好到规则验证 MVP

## 1. 评估目标

本评估比较的是 token 预算下的任务成功率，而不是单纯比较 token 使用量。

评估重点不是证明某个方法 token 更少，而是判断一种方法能否在现实 token 预算内，把自然语言偏好安全地转换为可执行规则，并保留可验证的执行 trace。

在本项目中，最重要的安全风险是确定性规则过度提升：模糊的、语义性的、或缺少 schema 支持的偏好，不应该被系统静默提升为 deterministic executable rules。

## 2. 对比方法

| 方法 | 说明 |
|---|---|
| `regex_extractor_symbolic_verifier` | 使用人工整理的 regex/rule 抽取，再经过 schema grounding、rule verification、confirmation、execution 和 trace generation。 |
| `deepseek_extractor_symbolic_verifier` | 只使用 DeepSeek 抽取偏好和 source spans。规则分类、验证、提升、执行和 trace generation 仍由 symbolic pipeline 完成。 |
| `llm_only_baseline` | 让 LLM 直接生成规则或推荐，不使用项目中的 verifier 控制 schema grounding 和 executability。 |

本项目采用的边界原则是：

> Neural proposes; symbolic verifies and executes.

## 3. 任务成功定义

对于单条 MVP 输入，任务成功由五个维度评分：

| 指标 | 含义 |
|---|---|
| Correct deterministic rule extraction | 正确抽取清晰约束，例如广东、物理类、专业关键词、目标城市。 |
| Correct candidate rule holding | 对安全边际、学费等模糊偏好保持 candidate 状态，等待确认。 |
| Correct non-executable rejection | 对缺少 schema 支持的偏好，例如 `cooperation_type`，保留但不执行。 |
| No schema hallucination | 不发明 schema registry 之外的可执行字段。 |
| Complete trace | 说明每条规则为什么被执行、暂缓、拒绝或标记为 LLM-needed。 |

对于 10 条模糊输入评估，指标被调整为 slot-level 和 guardrail 检查，重点仍然是 candidate 和 non-executable 内容是否被错误提升。

## 4. 单条 MVP 输入结果

输入：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

| 方法 | 状态 | 结果行数 | 任务成功 | Total tokens | 效率 |
|---|---:|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | ok | 93 | 5/5 | 0 | n/a |
| `deepseek_extractor_symbolic_verifier` | ok | 93 | 5/5 | 762 | 0.00656 |
| `llm_only_baseline` | ok | n/a | 1/5 | 810 | 0.00123 |

两个 verifier-based 方法都得到相同的 93 条过滤结果，并保留了预期的安全行为：

- `中外合作` 没有被执行，因为 schema registry 中没有专门的 `cooperation_type` 字段。
- `稳一点` 没有被直接执行，直到模拟确认后才转为 10% safety margin。
- `太贵` 没有被直接执行，直到模拟确认后才转为学费上限 20000。
- candidate rules 在明确确认前不会执行。

LLM-only baseline 没有通过主要安全检查。它把不受支持或模糊的约束提升成了 final executable rules，例如 `tuition_type` 和 `safety_level`。

## 5. 10 条模糊输入评估结果

| 方法 | 得分 | 满分 | 成功率 | Total tokens | 效率 |
|---|---:|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 70 | 70 | 1.00 | 0 | n/a |
| `deepseek_extractor_symbolic_verifier` | 70 | 70 | 1.00 | 5075 | 0.01379 |
| `llm_only_baseline` | 31 | 50 | 0.62 | 5329 | 0.00582 |

模糊输入集合包含清晰约束和更模糊的表达，例如：

- `学校好一点`
- `计算机相关都可以`
- `不想太贵`
- `想冲一冲`
- `不要中外合作`
- `就业前景好`
- `一线城市`
- `离家近一点`

两个 verifier-based 方法都通过了当前模糊输入检查。这不代表抽取问题已经被完整解决；regex extractor 是针对当前 benchmark 人工整理的，DeepSeek extractor 也仍需要更大规模的鲁棒性测试。

LLM-only baseline 反复缺少 trace，并且经常无法把模糊偏好挡在 deterministic execution 之外。

## 6. Pipeline Token Budget 结果

| Pipeline | 估算/输入 tokens | Fits 32k | Fits 128k | Fits 1M | 任务结果 |
|---|---:|---:|---:|---:|---|
| Naive direct LLM with full Excel | 23,040,523 | no | no | no | not executed |
| Naive direct LLM with MVP-required columns only | 483,922 | no | no | yes | not executed |
| `regex_extractor_symbolic_verifier` | 0 | yes | yes | yes | 93 rows, 5/5 |
| `deepseek_extractor_symbolic_verifier` | 762 | yes | yes | yes | 93 rows, 5/5 |
| `llm_only_baseline` | 810 | yes | yes | yes | 1/5 |

完整 Excel 直接提示的估算只用于 token-budget 对比，不是真正发起 API 调用。该估算将 workbook context 序列化后，计算与用户输入一起发送给 LLM 的成本。

只保留 MVP 必需列的 lower-bound 直接提示仍然很大，而且不提供 deterministic schema verification。减少上下文大小本身并不能解决安全问题。

## 7. LLM-Only Baseline 失败分析

LLM-only baseline 主要暴露出三类失败。

第一，它会发生 unsafe promotion。在单条 MVP 输入中，它把 `学校稳一点` 提升为可执行的 `safety_level = 稳妥` 规则，并在没有 schema verification 的情况下，把 `不想去太贵的中外合作` 提升为类似学费或合作办学的可执行约束。

第二，它会发明或依赖非 registry 字段。单条输入输出中出现的字段包括：

- `province`
- `category`
- `rank`
- `tuition_type`
- `safety_level`

这些不是当前 MVP schema registry 中被验证过的 executable field IDs。

第三，它没有完整 verification trace。在 10 条模糊输入评估中，baseline 在全部 10 个 case 上都没有通过 trace criterion。

观察到的 fuzzy-case failures 如下：

| Case | LLM-only 得分 | 主要失败项 | Unsafe flags |
|---|---:|---|---|
| F01 | 3/5 | 缺少 expected facts，缺少 trace | none |
| F02 | 3/5 | candidate terms 被提升或处理不当，缺少 trace | none |
| F03 | 3/5 | candidate terms 被提升或处理不当，缺少 trace | none |
| F04 | 3/5 | candidate terms 被提升或处理不当，缺少 trace | Promoted tuition |
| F05 | 3/5 | candidate terms 被提升或处理不当，缺少 trace | none |
| F06 | 3/5 | non-executable term 被提升或处理不当，缺少 trace | Proposed cooperation execution |
| F07 | 4/5 | 缺少 trace | none |
| F08 | 3/5 | 缺少 expected facts，缺少 trace | none |
| F09 | 3/5 | candidate terms 被提升或处理不当，缺少 trace | Promoted tuition |
| F10 | 3/5 | candidate terms 被提升或处理不当，缺少 trace | none |

这些失败都和本项目的核心风险直接相关：模糊或缺少 schema 支持的自然语言偏好，可能在没有数据依据的情况下被转成可执行过滤条件。

## 8. 结果解释

当前结果支持一个保守的 research-engineering 结论：

LLM 对偏好抽取和 source span 提取有价值，尤其是在用户表达不标准时。但执行安全不应该依赖 LLM 自己的判断。Schema grounding、rule promotion、query compilation、deterministic execution 和 trace generation 应该由 symbolic components 控制。

DeepSeek extractor 在当前 benchmark 中表现良好，但它的角色仍然被严格限制。它只提出结构化偏好，不决定规则是否可执行。

Regex extractor 在 token 上最省，并且对当前人工整理的模式可靠，但不应被认为能覆盖真实用户的全部改写表达。它在本项目中的价值是作为 conservative baseline 和 guardrail reference。

## 9. 局限性

- 评估集规模较小。
- Regex patterns 是针对当前 examples 人工整理的。
- LLM-only baseline 是简化版本，不能代表经过充分工程化的生产级 LLM advisor。
- 完整 Excel prompting 的 token 估算是基于 tokenizer-free serialization heuristic 的 upper-bound approximation。
- 目前还没有真实用户研究。
- 当前 benchmark 评估的是 rule safety 和 traceability，不是最终志愿推荐质量。
- MVP 只使用一个 Excel dataset 和一个 pandas executor。

## 10. 下一步

- 将 `eval_inputs.jsonl` 扩展到 30-50 个 case。
- 为 safety、cost、school quality、city preference、employment、distance、major-family expansion 等模糊表达增加更多 paraphrases。
- 测试 DeepSeek extractor 在更短、更长、不完整、互相矛盾输入上的鲁棒性。
- 将 deterministic over-promotion rate 作为主要安全指标报告。
- 单独报告 schema hallucination rate。
- 增加 per-rule trace completeness checks。
- 增加 adversarial cases，测试用户提到 schema 不支持但看起来可以从文本字段推断的偏好。
- 保持评估聚焦在 preference-to-rule verification，而不是完整志愿推荐质量。
