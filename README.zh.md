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
```

边界：

- `RegexExtractor` 只是 benchmark baseline，不是最终抽取策略。
- `DeepSeekExtractor` 只能抽取 preferences 和 source spans。
- `AttributeGrounder` 在 rule construction 前审计 extracted attributes。
- `RuleVerifier` 控制 schema grounding 和 executability。
- `PandasExecutor` 只是 Excel/CSV 的 MVP executor。
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

离线 regex baseline：

```bash
python3 scripts/eval_fuzzy_inputs.py
```

当前 40-case evaluation 摘要：

| 方法 | 得分 | Over-promotion |
|---|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.450 |
| `schema_aware_llm_only_baseline` | 157/200 | 0.300 |

DeepSeek 对比需要 `.env`：

```bash
set -a
source .env
set +a
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py
```

## Tests

```bash
python3 -m unittest discover -s tests
```
