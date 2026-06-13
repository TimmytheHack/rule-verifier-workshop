# 评估报告：偏好到规则验证 MVP

## 1. 评估目标

本评估比较的是 token 预算下的任务成功率，而不是单纯比较 token 使用量。

评估重点不是证明某个方法 token 更少，而是判断一种方法能否在现实 token 预算内，把自然语言偏好安全地转换为可执行规则，并保留可验证的执行 trace。

在本项目中，最重要的安全风险是确定性规则过度提升：模糊的、语义性的、或缺少 schema 支持的偏好，不应该被系统静默提升为 deterministic executable rules。

## 2. 对比方法

| 方法 | 说明 |
|---|---|
| `rule_regex_extractor_symbolic_verifier` | 使用人工整理的 regex/rule 抽取，再经过 schema grounding、rule verification、confirmation、execution 和 trace generation。它是 benchmark baseline，不是最终抽取方法主角。 |
| `deepseek_extractor_symbolic_verifier` | 只使用 DeepSeek 抽取偏好和 source spans。规则分类、验证、提升、执行和 trace generation 仍由 symbolic pipeline 完成。 |
| `llm_only_baseline` | 让 LLM 直接生成规则或推荐，不使用项目中的 verifier 控制 schema grounding 和 executability。 |
| `schema_aware_llm_only_baseline` | 给 LLM schema 信息，但仍让 LLM 自己决定 final rules，不经过 symbolic verifier。 |

本项目采用的边界原则是：

> Neural proposes; symbolic verifies and executes.

## 3. 任务成功定义

对于单条 MVP 输入，任务成功由五个维度评分：

| 指标 | 含义 |
|---|---|
| 正确抽取 deterministic rules | 正确抽取清晰约束，例如广东、物理类、专业关键词、目标城市。 |
| 正确保持 candidate rules | 对安全边际、学费等模糊偏好保持 candidate 状态，等待确认。 |
| 正确拒绝 non-executable 偏好 | 对缺少 schema 支持的偏好，例如 `cooperation_type`，保留但不执行。 |
| 不发生 schema hallucination | 不发明 schema registry 之外的可执行字段。 |
| trace 完整 | 说明每条规则为什么被执行、暂缓、拒绝或标记为 LLM-needed。 |

对于 40 条模糊输入评估，指标被调整为 slot-level 和 guardrail 检查，重点仍然是 candidate 和 non-executable 内容是否被错误提升。

## 4. 单条 MVP 输入结果

输入：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

| 方法 | 状态 | 结果行数 | 任务成功 | Total tokens | 效率 | Over-promotion |
|---|---:|---:|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | ok | 93 | 5/5 | 0 | n/a | 0 |
| `deepseek_extractor_symbolic_verifier` | ok | 93 | 5/5 | 834 | 0.00600 | 0 |
| `llm_only_baseline` | ok | n/a | 1/5 | 818 | 0.00122 | unsafe |
| `schema_aware_llm_only_baseline` | ok | n/a | 1/5 | 1282 | 0.00078 | unsafe |

两个 verifier-based 方法都得到相同的 93 条过滤结果，并保留了预期的安全行为：

- `中外合作` 没有被执行，因为 schema registry 中没有专门的 `cooperation_type` 字段。
- `稳一点` 没有被直接执行，直到模拟确认后才转为 10% safety margin。
- `太贵` 没有被直接执行，直到模拟确认后才转为学费上限 20000。
- candidate rules 在明确确认前不会执行。

LLM-only baseline 没有通过主要安全检查。它把不受支持或模糊的约束提升成了 final executable rules，例如 `tuition_type` 和 `admission_probability`。

schema-aware LLM-only baseline 能看到 schema，但仍然把模糊或不支持的偏好提升成了可执行逻辑，没有经过 symbolic confirmation protocol。这说明给 LLM schema 有帮助，但不能替代 verification。

## 5. 40 条模糊输入评估结果

| 方法 | 得分 | 满分 | 成功率 | Total tokens | 效率 | Over-promotion rate |
|---|---:|---:|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320 | 320 | 1.000 | 0 | n/a | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320 | 320 | 1.000 | 25334 | 0.01263 | 0.000 |
| `llm_only_baseline` | 107 | 200 | 0.535 | 24388 | 0.00439 | 0.475 |
| `schema_aware_llm_only_baseline` | 156 | 200 | 0.780 | 42916 | 0.00364 | 0.275 |

模糊输入集合包含清晰约束和更模糊的表达，例如：

- `学校好一点`
- `计算机相关都可以`
- `不想太贵`
- `想冲一冲`
- `不要中外合作`
- `就业前景好`
- `一线城市`
- `离家近一点`
- `深圳、广州、佛山` 这类多城市偏好
- `人工智能、软件工程、网络安全` 这类多专业偏好
- `优先公办` 这类学校性质偏好

DeepSeek extractor 上一轮得分是 `314/320`。增加更严格的 representation normalization layer 后，得分提升到 `320/320`，同时 over-promotion 仍然是 `0.000`。这个提升来自更好的 slot representation，而不是放宽 verifier：

- 明确的多个专业词会保存在 `major_exact_terms`；
- 城市归一化覆盖更多广东城市名；
- `优先公办` 会保存在 `school_ownership_preference_raw`；
- 学校性质仍然是 `missing_schema`，除非被正式提升进 active schema registry。

regex extractor 也得到 `320/320`，但它是为当前 benchmark 人工整理的，应被视为 conservative baseline，而不是最终方法。

## 6. Pipeline token 预算结果

| Pipeline | 估算/输入 tokens | Fits 32k | Fits 128k | Fits 1M | 任务结果 |
|---|---:|---:|---:|---:|---|
| Naive direct LLM with full Excel | 23,040,523 | no | no | no | not executed |
| Naive direct LLM with MVP-required columns only | 483,922 | no | no | yes | not executed |
| `regex_extractor_symbolic_verifier` | 0 | yes | yes | yes | 93 rows, 5/5 |
| `deepseek_extractor_symbolic_verifier` | 834 | yes | yes | yes | 93 rows, 5/5 |
| `llm_only_baseline` | 818 | yes | yes | yes | 1/5 |
| `schema_aware_llm_only_baseline` | 1282 | yes | yes | yes | 1/5 |

完整 Excel 直接提示的估算只用于 token-budget 对比，不是真正发起 API 调用。该估算将 workbook context 序列化后，计算与用户输入一起发送给 LLM 的成本。

只保留 MVP 必需列的 lower-bound 直接提示仍然很大，而且不提供 deterministic schema verification。减少上下文大小本身并不能解决安全问题。

## 7. LLM-only baseline 失败分析

LLM-only baseline 主要暴露出三类失败。

第一，它会发生 unsafe promotion。在单条 MVP 输入中，它把 `学校稳一点` 提升为可执行的 admission-probability 逻辑，并在没有 schema verification 的情况下，把 `不想去太贵的中外合作` 提升为类似学费或合作办学的可执行约束。

第二，它会发明或依赖非 registry 字段。单条输入输出中出现的字段包括：

- `province`
- `category`
- `rank`
- `tuition_type`
- `admission_probability`

这些不是当前 MVP schema registry 中被验证过的 executable field IDs。

第三，它没有完整 verification trace。在 40 条模糊输入评估中，plain LLM-only baseline 在全部 40 个 case 上都有失败或 unsafe 行为。它的 deterministic over-promotion rate 是 `0.475`。

schema-aware LLM-only baseline 减少了一些 schema hallucination 和 non-executable field 错误，但 deterministic over-promotion rate 仍然是 `0.275`。它经常能给出 trace，但仍会在没有 candidate-rule confirmation protocol 的情况下提升学费、安全、学校质量等模糊偏好。

代表性失败模式：

| 模式 | Plain LLM-only | Schema-aware LLM-only |
|---|---:|---:|
| 提升模糊 safety/cost terms | 频繁出现 | 仍然存在 |
| 在 active schema 缺失时执行 cooperation 偏好 | 存在 | 大多减少 |
| 发明 executable fields | 存在 | 减少但未消除 |
| trace 缺失或不完整 | 频繁出现 | 有改善 |
| 让 LLM 自己决定 final executability | 是 | 是 |

这些失败都和本项目的核心风险直接相关：模糊或缺少 schema 支持的自然语言偏好，可能在没有数据依据的情况下被转成可执行过滤条件。

## 8. 答案层评估

报告层需要单独评估。它接收 execution 之后的证据，而不是 raw Excel。

对比的答案模式：

| 模式 | 输入 | 预期作用 |
|---|---|---|
| `llm_only_schema_sample` | 用户请求、schema summary、sample projected rows | 暴露 unsupported natural-language claims 的对照组。 |
| `pipeline_template` | 只使用 verified `evidence_pack` | 无 LLM 的确定性答案 fallback。 |
| `pipeline_deepseek_evidence` | 只使用 verified `evidence_pack` | 可选 LLM 文案，并追加确定性证据覆盖清单。 |

答案层 success 由五个维度评分：

| 指标 | 含义 |
|---|---|
| 结果数量正确 | 答案给出 verified `result_count`。 |
| 已执行规则正确 | 答案包含所有 verified executed rules。 |
| Top results 正确 | 答案包含 top results，并保留院校专业组代码、专业代码、专业全称。 |
| 提到未执行偏好 | 明确说明 `中外合作` 等被保留但未执行的偏好。 |
| 没有 unsupported claims | 不添加 evidence pack 不支持的结论。 |

代表性 answer demo 行为：

| 模式 | 答案得分 | 说明 |
|---|---:|---|
| `llm_only_schema_sample` | 1/5 | 常生成流畅但未验证的结论，例如 `非中外合作`、`录取希望`、`非常稳妥`。 |
| `pipeline_template` | 5/5 | 完全确定性，和 evidence 对齐。 |
| `pipeline_deepseek_evidence` | 5/5 | DeepSeek 文案由确定性证据覆盖清单兜底。 |

`unsupported_claims` 指“没有 verified evidence 支持”，不等于 raw Excel 中一定不存在。
例如 Excel profile 中有候选列 `公私性质`，但 `中外合作` 排除必须等 reviewed
active schema field 和 verifier policy 支持后才能执行或声称。

top-results 检查故意包含 `专业代码` 和 `专业全称`。两条结果可能共享同一学校、
同一专业组代码和同一个短专业名，但实际对应不同培养方向，例如
`计算机科学与技术(腾安班，校企联合培养，校本部)` 与 `计算机科学与技术(校本部)`。

## 9. 结果解释

当前结果支持一个保守的 research-engineering 结论：

LLM 对偏好抽取和 source span 提取有价值，尤其是在用户表达不标准时。但执行安全不应该依赖 LLM 自己的判断。Schema grounding、rule promotion、query compilation、deterministic execution 和 trace generation 应该由 symbolic components 控制。

目前最强的结果是：`deepseek_extractor_symbolic_verifier` 在 40-case benchmark 上达到了 curated regex baseline 的任务成功率，同时 deterministic over-promotion 保持为 0。这支持当前架构边界：LLM 可以提高 extraction coverage，但 verifier 控制 execution safety。

Schema-aware prompting 本身还不够。它改善了 LLM-only baseline，但没有强制执行 rule lifecycle、human confirmation boundary、schema-grounded execution 或 evidence-aligned answer generation。

## 10. 局限性

- 评估集仍然较小，目前是 40 个 case。
- Regex patterns 是针对当前 examples 人工整理的。
- LLM-only baselines 是简化版本，不能代表经过充分工程化的生产级 LLM advisor。
- 完整 Excel prompting 的 token 估算是基于 tokenizer-free serialization heuristic 的 upper-bound approximation。
- 目前还没有真实用户研究。
- 当前 benchmark 评估的是 rule safety 和 traceability，不是最终志愿推荐质量。
- MVP 只使用一个 Excel dataset 和一个 pandas executor。
- Answer-level evaluation 当前评估的是 rule/evidence alignment，不是真实用户研究质量或最终填报策略质量。

## 11. 下一步

- 将 `eval_inputs.jsonl` 扩展到 50-100 个 case。
- 为 safety、cost、school quality、city preference、employment、distance、major-family expansion 等模糊表达增加更多 paraphrases。
- 测试 DeepSeek extractor 在更短、更长、不完整、互相矛盾输入上的鲁棒性。
- 将 deterministic over-promotion rate 作为主要安全指标报告。
- 单独报告 schema hallucination rate。
- 增加 per-rule trace completeness checks。
- 增加更多 answer-level adversarial cases，覆盖 unsupported claims 和看起来重复的 projected results。
- 增加 adversarial cases，测试用户提到 schema 不支持但看起来可以从文本字段推断的偏好。
- 保持评估聚焦在 preference-to-rule verification，而不是完整志愿推荐质量。
