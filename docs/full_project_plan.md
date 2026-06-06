# Full Project Roadmap

This roadmap keeps the project focused. The goal is not to build a full college recommendation product; the goal is to study how natural-language preferences become verified executable rules.

## Positioning

Working title:

```text
Preference-to-Rule Verification for Structured Decision Systems
```

Case study:

```text
Guangdong college application planning with one Excel dataset.
```

Main contribution:

```text
Prevent unsafe promotion of vague or unsupported natural-language preferences into deterministic executable rules.
```

## Runtime Core

The runtime path should stay small:

```text
Extractor
-> AttributeGrounder
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> Executor
-> TraceGenerator
```

Required boundaries:

- Regex extractor is only a benchmark baseline.
- DeepSeek extractor may extract preferences and source spans only.
- Attribute grounding audits extracted attributes before rule construction.
- Rule verifier is the authority for schema grounding and executability.
- Candidate rules require confirmation before promotion.
- Executor only receives verified executable rules.

## Offline Tools

These tools support research and schema review, but are not part of runtime:

| Tool | Role |
|---|---|
| `scripts/profile_excel_schema.py` | Profiles every Excel column and generates a field catalog. |
| `schemas/excel_schema_profile.json` | Machine-readable profile for schema review. |
| `docs/excel_schema_profile.md` | Human-readable schema profile. |
| `scripts/eval_modes.py` | Single-input method comparison. |
| `scripts/eval_fuzzy_inputs.py` | 40-case benchmark comparison. |
| `scripts/eval_pipeline_token_budget.py` | Token-budget comparison. |

## Main Documents

The project should maintain four main research documents:

| Document | Purpose |
|---|---|
| `docs/methodology_report.md` | Current methodology and safety boundary. |
| `docs/evaluation_report.md` | Current experimental results. |
| `docs/excel_schema_profile.md` | Field catalog generated from the Excel dataset. |
| `docs/end_to_end_demo_cases.md` | Demo case matrix and expected rule treatment. |

Chinese companion documents may be kept for user-facing readability.

## Current Evaluation Plan

Keep the benchmark layered:

- clear deterministic inputs;
- vague candidate-rule inputs;
- unsupported-schema inputs;
- mixed inputs;
- adversarial inputs;
- contradictory inputs;
- end-to-end demo inputs.

Compare:

1. `regex_extractor_symbolic_verifier`
2. `deepseek_extractor_symbolic_verifier`
3. `llm_only_baseline`
4. `schema_aware_llm_only_baseline`

Primary safety metric:

```text
deterministic over-promotion rate
```

Supporting metrics:

- schema hallucination rate;
- candidate holding accuracy;
- non-executable rejection accuracy;
- trace completeness;
- task success under token budget.

## Next Steps

1. Review `docs/excel_schema_profile.md`.
2. Promote only trusted candidate fields into `schemas/schema_registry.json`.
3. Add tests for each promoted field.
4. Expand the 40-case benchmark toward 50-100 realistic paraphrases.
5. Stress-test DeepSeek extraction on longer, noisier, incomplete, and contradictory inputs.
6. Keep recommendation quality evaluation separate from rule-verification evaluation.

Latest benchmark snapshot:

| Method | Score | Over-promotion |
|---|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.275 |

## What Not To Build Yet

- Full志愿表 generation.
- School reputation ranking logic without reviewed schema.
- Employment prediction.
- Web-search augmentation.
- Multi-turn advisor UI.
- Universal symbolic AI.
- More regex special cases solely to improve benchmark scores.
