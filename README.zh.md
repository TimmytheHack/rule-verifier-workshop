# 偏好到规则验证

英文版：[README.md](/Users/tz/Desktop/Projects/SZU/README.md)

本仓库是一个 research-engineering 项目，主题是：

```text
面向广东高考志愿填报的 Preference-to-Rule Verification
```

它不是普通志愿推荐 bot。项目研究的是：自然语言偏好如何被转换为：

- deterministic executable rules；
- 需要确认的 candidate rules；
- non-executable 或 LLM-needed semantic parts。

核心安全目标是：防止模糊或缺少 schema 支持的偏好被静默提升为确定性过滤条件。

## Runtime Core

运行时主路径保持小而清楚：

```text
Extractor
-> AttributeGrounder
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> Executor
-> TraceGenerator
-> EvidencePack
-> ReportBuilder / AnswerGenerator
```

边界：

- `RegexExtractor` 只是 benchmark baseline，不是最终抽取策略。
- `DeepSeekExtractor` 只能抽取 preferences 和 source spans。
- `AttributeGrounder` 在 rule construction 前审计 extracted attributes。
- `RuleVerifier` 控制 schema grounding 和 executability。
- `PandasExecutor` 只是 Excel/CSV 的 MVP executor。
- `EvidencePack` 是答案生成的唯一输入；答案层不能读 raw Excel。
- `TemplateReportBuilder` 是确定性模板，不使用 LLM。
- `DeepSeekAnswerGenerator` 是可选 evidence-only 答案生成器。
- `SchemaProfiler` 是离线 schema-review 工具，不进入 runtime。

## 主文档

- [docs/methodology_report.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.md)
- [docs/methodology_report.zh.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.zh.md)
- [docs/evaluation_report.md](/Users/tz/Desktop/Projects/SZU/docs/evaluation_report.md)
- [docs/evaluation_report.zh.md](/Users/tz/Desktop/Projects/SZU/docs/evaluation_report.zh.md)
- [docs/excel_schema_profile.md](/Users/tz/Desktop/Projects/SZU/docs/excel_schema_profile.md)
- [docs/end_to_end_demo_cases.md](/Users/tz/Desktop/Projects/SZU/docs/end_to_end_demo_cases.md)
- [docs/end_to_end_demo_cases.zh.md](/Users/tz/Desktop/Projects/SZU/docs/end_to_end_demo_cases.zh.md)
- [docs/full_project_plan.md](/Users/tz/Desktop/Projects/SZU/docs/full_project_plan.md)

## 运行 MVP Demo

```bash
python3 scripts/run_mvp_demo.py
```

当前预期输出：

```text
Wrote outputs/mvp_demo/rules.json
Wrote outputs/mvp_demo/verification_report.md
Wrote outputs/mvp_demo/filtered_results.csv
Wrote outputs/mvp_demo/result_trace.md
Filtered rows: 93
```

## 离线 Schema Profile

```bash
python3 scripts/profile_excel_schema.py
```

输出：

- [schemas/excel_schema_profile.json](/Users/tz/Desktop/Projects/SZU/schemas/excel_schema_profile.json)
- [docs/excel_schema_profile.md](/Users/tz/Desktop/Projects/SZU/docs/excel_schema_profile.md)

这个 profile 只是 review artifact。字段只有被提升到 `schemas/schema_registry.json` 后才能执行。

## Evaluation

快速本地 regex-only 评估：

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

较快的 DeepSeek extractor-only 评估：

```bash
python3 scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
```

完整对比：

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --methods all
```

当前 40-case evaluation 摘要：

| 方法 | 得分 | Over-promotion |
|---|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.275 |

DeepSeek 对比会自动读取 `.env`：

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --methods all
```

## 答案 Demo

答案层比较三种模式：

| 模式 | 输入 | 目的 |
|---|---|---|
| `llm_only_schema_sample` | 用户请求、schema summary、sample projected rows | 对照组，用来暴露 unsupported claims 和 trace 缺失。 |
| `pipeline_template` | 只使用 verified `evidence_pack` | 确定性的生产安全 fallback。 |
| `pipeline_deepseek_evidence` | 只使用 verified `evidence_pack` | 可选 LLM 答案，并追加确定性证据覆盖清单。 |

运行：

```bash
python3 scripts/run_answer_demo.py
```

输出：

- `outputs/answer_demo/evidence_pack.json`
- `outputs/answer_demo/template_answer.md`
- `outputs/answer_demo/llm_only_answer.md`
- `outputs/answer_demo/deepseek_evidence_answer.md`
- `outputs/answer_demo/answer_comparison.json`

Answer-level evaluation 检查：

- 结果总数是否正确；
- 已执行规则是否正确；
- top results 是否正确，包括院校专业组代码、专业代码、专业全称；
- 是否提到未执行偏好；
- 是否没有 unsupported-by-verified-evidence claims。

`unsupported_claims` 指“没有被 verified evidence pack 支持”，不是指 raw Excel
里一定没有。例如 Excel profile 里有候选列 `公私性质`，但 `中外合作` 排除
仍要等 reviewed active schema field 和 verifier policy 加入后才能执行或声称。

## Tests

```bash
python3 -m unittest discover -s tests
```
