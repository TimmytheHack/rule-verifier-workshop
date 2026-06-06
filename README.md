# Preference-to-Rule Verification

Chinese version: [README.zh.md](/Users/tz/Desktop/Projects/SZU/README.zh.md)

This repository is a research-engineering project for:

```text
Preference-to-Rule Verification for Guangdong College Application Planning
```

It is not a normal recommendation bot. The project studies how natural-language preferences become:

- deterministic executable rules;
- candidate rules requiring confirmation;
- non-executable or LLM-needed semantic parts.

The key safety goal is preventing vague or unsupported preferences from being silently promoted into deterministic filters.

## Runtime Core

The runtime path is intentionally small:

```text
Extractor
-> AttributeGrounder
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> Executor
-> TraceGenerator
```

Important boundaries:

- `RegexExtractor` is a benchmark baseline, not the final extraction strategy.
- `DeepSeekExtractor` may extract preferences and source spans only.
- `AttributeGrounder` audits extracted attributes before rule construction.
- `RuleVerifier` controls schema grounding and executability.
- `PandasExecutor` is only the MVP executor for Excel/CSV.
- `SchemaProfiler` is an offline schema-review tool, not runtime.

## Main Documents

- [docs/methodology_report.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.md)
- [docs/evaluation_report.md](/Users/tz/Desktop/Projects/SZU/docs/evaluation_report.md)
- [docs/excel_schema_profile.md](/Users/tz/Desktop/Projects/SZU/docs/excel_schema_profile.md)
- [docs/end_to_end_demo_cases.md](/Users/tz/Desktop/Projects/SZU/docs/end_to_end_demo_cases.md)
- [docs/full_project_plan.md](/Users/tz/Desktop/Projects/SZU/docs/full_project_plan.md)

## Run MVP Demo

```bash
python3 scripts/run_mvp_demo.py
```

Expected current output:

```text
Wrote outputs/mvp_demo/rules.json
Wrote outputs/mvp_demo/verification_report.md
Wrote outputs/mvp_demo/filtered_results.csv
Wrote outputs/mvp_demo/result_trace.md
Filtered rows: 93
```

## Offline Schema Profile

```bash
python3 scripts/profile_excel_schema.py
```

This scans all Excel columns and writes:

- [schemas/excel_schema_profile.json](/Users/tz/Desktop/Projects/SZU/schemas/excel_schema_profile.json)
- [docs/excel_schema_profile.md](/Users/tz/Desktop/Projects/SZU/docs/excel_schema_profile.md)

The profile is a review artifact. Columns are not executable until promoted into `schemas/schema_registry.json`.

## Evaluation

Fast local regex-only evaluation:

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

Faster DeepSeek extractor-only evaluation:

```bash
python3 scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
```

Full comparison:

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --methods all
```

Current 40-case evaluation summary:

| Method | Score | Over-promotion |
|---|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.275 |

DeepSeek comparison reads `.env` automatically:

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --methods all
```

## Tests

```bash
python3 -m unittest discover -s tests
```
