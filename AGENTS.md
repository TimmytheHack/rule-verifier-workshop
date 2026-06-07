# AGENTS.md

## Project Mission

This repository is a research-engineering project for preference-to-rule
verification in Guangdong college application planning. It is not a generic
recommendation bot.

The core safety invariant is:

```text
Natural language may propose structure, but only verified schema-grounded rules may execute.
```

## Architecture Boundary

The runtime path is:

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

Keep these boundaries intact:

- Extractors may extract preferences and source spans, but must not decide final
  executability.
- `RegexExtractor` is a benchmark baseline, not the final extraction strategy.
- `DeepSeekExtractor` may extract preferences and source spans only.
- Attribute grounding audits extracted slots before rule construction.
- Rule verification controls schema existence, operator validity, ambiguity, and
  execution level.
- Candidate rules must not execute before confirmation or simulated confirmation.
- Missing-schema or external-info preferences must be preserved but not executed.
- LLM-only baselines are evaluation baselines, not production execution paths.
- `PandasExecutor` is only the MVP executor for Excel/CSV.
- `EvidencePack` is the only input to answer generation; raw Excel is not.
- `TemplateReportBuilder` is deterministic and uses no LLM.
- `DeepSeekAnswerGenerator` is optional and evidence-only.
- `SchemaProfiler` is an offline schema-review tool, not runtime.

## Domain Rules

For Guangdong application planning, rank is more important than score. If a user
gives only score and no rank, ask for province rank rather than estimating risk
from score alone.

Do not output school-only recommendations when professional-group data is
available. The minimum useful result shape is:

```text
院校名称
院校专业组代码
专业名称
城市
学费
专业组最低位次
专业最低位次 / if available
safety margin
```

Explicit field/value constraints can be deterministic when schema-grounded. For
example, `学费两万以内` can become `学费 <= 20000` if `学费` exists. Vague
preferences such as `太贵`, `稳一点`, `学校好一点`, `计算机相关`, or `离家近`
remain candidate or external-info needs until boundaries are confirmed.

## Answer Evaluation Guardrails

Answer-level evaluation checks:

- correct result count;
- correct executed rules;
- correct top results, including professional group code, major code, and full
  major name;
- mentions not-executed preferences;
- no claims unsupported by verified evidence.

`unsupported_claims` means unsupported by the verified evidence pack, not
necessarily absent from raw Excel. For example, `公私性质` exists as a candidate
column in the Excel profile, but `中外合作` exclusion remains unsupported until a
reviewed active schema field and verifier policy are added.

## Editing Policy

- Prefer small, reviewable changes that preserve the methodology boundary.
- Do not relax verifier checks to improve benchmark scores.
- Do not add regex special cases only to chase benchmark results unless the
  expected behavior is also documented and tested.
- Do not infer unsupported fields such as `cooperation_type`, employment
  outlook, dorm quality, school atmosphere, or city development potential from
  free text unless a reviewed structured field is added first.
- Keep generated evaluation artifacts consistent with reports when they are
  intentionally refreshed.
- Never print or inspect secrets from `.env`.

## Common Commands

Fast local safety checks:

```bash
python3 -m unittest discover -s tests
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

DeepSeek-backed checks read `.env` automatically:

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
python3 scripts/eval_fuzzy_inputs.py --methods all
```

Use the full DeepSeek comparison only when API latency and token usage are
acceptable. The fuzzy evaluator caches API responses in
`outputs/eval/deepseek_fuzzy_cache.json`, which is ignored by git.

## Tests And Artifacts

When changing runtime code, run targeted unit tests plus syntax checks. When
changing evaluation logic or expected scores, update:

- `outputs/eval/eval_modes.json`
- `outputs/eval/fuzzy_eval_results.json`
- `outputs/eval/pipeline_token_budget.json`
- `docs/evaluation_report*.md`
- `docs/methodology_report*.md`
- public docs that intentionally quote benchmark summaries

When changing schema or rule policy, update tests that assert the relevant
guardrail.
