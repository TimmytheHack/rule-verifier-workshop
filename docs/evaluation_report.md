# Evaluation Report: Preference-to-Rule Verification MVP

## 1. Evaluation Goal

This evaluation compares task success under token budget, not token usage alone.

The purpose is not to show that one method uses fewer tokens in isolation. The question is whether a method can correctly convert natural-language preferences into safe executable rules while staying within a realistic token budget and preserving verification traceability.

For this project, the main safety concern is deterministic over-promotion: vague, semantic, or schema-unsupported preferences should not be silently promoted into deterministic executable rules.

## 2. Methods Compared

| Method | Description |
|---|---|
| `rule_regex_extractor_symbolic_verifier` | Uses curated regex/rule extraction, then passes extracted slots through schema grounding, rule verification, confirmation, execution, and trace generation. This is a benchmark baseline, not the final extraction strategy. |
| `deepseek_extractor_symbolic_verifier` | Uses DeepSeek only to extract preferences and source spans. Rule classification, verification, promotion, execution, and trace generation remain symbolic. |
| `llm_only_baseline` | Asks an LLM to directly produce rules or recommendations without the project verifier controlling schema grounding and executability. |
| `schema_aware_llm_only_baseline` | Gives the LLM schema information, but still lets it decide final rules without the symbolic verifier. |

The intended boundary is:

> Neural proposes; symbolic verifies and executes.

## 3. Task Success Definition

For the single MVP input, task success is scored across five criteria:

| Criterion | Meaning |
|---|---|
| Correct deterministic rule extraction | Clear constraints such as Guangdong, physics track, major keyword, and target cities are extracted correctly. |
| Correct candidate rule holding | Vague preferences such as safety and tuition are held as candidate rules until confirmation. |
| Correct non-executable rejection | Preferences without schema support, such as `cooperation_type`, are preserved but not executed. |
| No schema hallucination | The method does not invent executable fields outside the schema registry. |
| Complete trace | The output explains why each rule was executed, held, rejected, or marked LLM-needed. |

For the 40-case fuzzy evaluation, the same principle is adapted to slot-level and guardrail checks, including whether candidate and non-executable terms are held instead of promoted.

## 4. Results: Single MVP Input

Input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

| Method | Status | Result rows | Task success | Total tokens | Efficiency | Over-promotion |
|---|---:|---:|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | ok | 93 | 5/5 | 0 | n/a | 0 |
| `deepseek_extractor_symbolic_verifier` | ok | 93 | 5/5 | 834 | 0.00600 | 0 |
| `llm_only_baseline` | ok | n/a | 1/5 | 818 | 0.00122 | unsafe |
| `schema_aware_llm_only_baseline` | ok | n/a | 1/5 | 1282 | 0.00078 | unsafe |

The two verifier-based methods produced the same 93 filtered rows and preserved the expected safety behavior:

- `中外合作` was not executed because the schema registry has no dedicated `cooperation_type` field.
- `稳一点` was not directly executed until simulated confirmation produced a 10% safety margin.
- `太贵` was not directly executed until simulated confirmation produced a tuition cap of 20000.
- Candidate rules did not execute before explicit confirmation.

The LLM-only baseline failed the main safety checks. It promoted unsupported or vague constraints into final executable rules, including fields such as `tuition_type` and `admission_probability`.

The schema-aware LLM-only baseline can see schema context, but still promoted vague or unsupported preferences into executable logic without the symbolic confirmation protocol. This shows that schema awareness helps but does not replace verification.

## 5. Results: 40-Case Fuzzy Evaluation

| Method | Score | Max score | Success rate | Total tokens | Efficiency | Over-promotion rate |
|---|---:|---:|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320 | 320 | 1.000 | 0 | n/a | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320 | 320 | 1.000 | 25334 | 0.01263 | 0.000 |
| `llm_only_baseline` | 107 | 200 | 0.535 | 24388 | 0.00439 | 0.475 |
| `schema_aware_llm_only_baseline` | 156 | 200 | 0.780 | 42916 | 0.00364 | 0.275 |

The fuzzy set includes clearer inputs and more ambiguous preferences such as:

- `学校好一点`
- `计算机相关都可以`
- `不想太贵`
- `想冲一冲`
- `不要中外合作`
- `就业前景好`
- `一线城市`
- `离家近一点`
- multi-city preferences such as `深圳、广州、佛山`
- multi-major preferences such as `人工智能、软件工程、网络安全`
- school ownership preferences such as `优先公办`

The DeepSeek extractor previously scored `314/320`. After adding a stricter representation normalization layer, it reached `320/320` while keeping over-promotion at `0.000`. This improvement came from better slot representation, not from relaxing the verifier:

- explicit multi-major terms are preserved in `major_exact_terms`;
- city normalization covers more Guangdong city names;
- `优先公办` is preserved as `school_ownership_preference_raw`;
- school ownership remains `missing_schema` unless promoted into the active schema registry.

The regex extractor also scored `320/320`, but it is curated for this benchmark and should be treated as a conservative baseline rather than the final method.

## 6. Results: Pipeline Token Budget

| Pipeline | Estimated/input tokens | Fits 32k | Fits 128k | Fits 1M | Task result |
|---|---:|---:|---:|---:|---|
| Naive direct LLM with full Excel | 23,040,523 | no | no | no | not executed |
| Naive direct LLM with MVP-required columns only | 483,922 | no | no | yes | not executed |
| `regex_extractor_symbolic_verifier` | 0 | yes | yes | yes | 93 rows, 5/5 |
| `deepseek_extractor_symbolic_verifier` | 834 | yes | yes | yes | 93 rows, 5/5 |
| `llm_only_baseline` | 818 | yes | yes | yes | 1/5 |
| `schema_aware_llm_only_baseline` | 1282 | yes | yes | yes | 1/5 |

The full-Excel direct prompting estimate is intentionally treated as a token-budget comparison, not an API call. It serializes the workbook context and estimates the cost of sending it with the user input.

The lower-bound direct-prompt estimate using only MVP-required columns is still large and does not provide deterministic schema verification. Reducing context size alone does not solve the safety problem.

## 7. Failure Analysis of LLM-Only Baselines

The LLM-only baseline shows three recurring failure modes.

First, it performs unsafe promotion. In the single MVP input, it promoted `学校稳一点` into executable admission-probability logic, and promoted `不想去太贵的中外合作` into executable tuition/cooperation-like constraints without schema verification.

Second, it invents or relies on non-registry fields. Example fields in the single-input output include:

- `province`
- `category`
- `rank`
- `tuition_type`
- `admission_probability`

These are not the verified executable field IDs used by the MVP schema registry.

Third, it does not produce a complete verification trace. In the 40-case fuzzy evaluation, the plain LLM-only baseline failed or produced unsafe behavior in all 40 cases. Its deterministic over-promotion rate was `0.475`.

The schema-aware LLM-only baseline reduced some schema hallucination and non-executable-field errors, but still had a deterministic over-promotion rate of `0.275`. It often kept a trace, but still promoted vague preferences such as tuition, safety, or school-quality terms without the candidate-rule confirmation protocol.

Representative failure patterns:

| Pattern | Plain LLM-only | Schema-aware LLM-only |
|---|---:|---:|
| Promotes vague safety/cost terms | frequent | still present |
| Proposes cooperation execution without active schema | present | mostly reduced |
| Invents executable fields | present | reduced but not eliminated |
| Missing or incomplete trace | frequent | improved |
| Lets LLM decide final executability | yes | yes |

These failures are directly related to the project’s main risk: vague or unsupported natural-language preferences can be turned into executable filters without evidence that the data schema supports them.

## 8. Answer-Level Evaluation

The reporting layer is evaluated separately from rule execution. It receives
post-execution evidence, not raw Excel.

Compared answer modes:

| Mode | Input | Expected role |
|---|---|---|
| `llm_only_schema_sample` | User request, schema summary, and sample projected rows | Baseline for unsupported natural-language claims. |
| `pipeline_template` | Verified `evidence_pack` only | Deterministic answer fallback with no LLM. |
| `pipeline_deepseek_evidence` | Verified `evidence_pack` only | Optional LLM prose plus deterministic evidence coverage. |

Answer-level success is scored across five criteria:

| Criterion | Meaning |
|---|---|
| Correct result count | The answer states the verified `result_count`. |
| Correct executed rules | The answer includes every verified executed rule. |
| Correct top results | The answer includes the projected top results, including professional group code, major code, and full major name. |
| Mentions not-executed preferences | Preserved but unexecuted preferences such as `中外合作` are explicitly mentioned as not executed. |
| No unsupported claims | The answer does not add claims unsupported by the evidence pack. |

Representative answer-demo behavior:

| Mode | Answer score | Notes |
|---|---:|---|
| `llm_only_schema_sample` | 1/5 | Often produces fluent but unsupported claims such as `非中外合作`, `录取希望`, or `非常稳妥`. |
| `pipeline_template` | 5/5 | Fully deterministic and evidence-aligned. |
| `pipeline_deepseek_evidence` | 5/5 | DeepSeek prose is backed by a deterministic evidence coverage checklist. |

`unsupported_claims` means unsupported by verified evidence, not necessarily
absent from raw Excel. For example, the Excel profile contains a candidate
`公私性质` column, but `中外合作` exclusion cannot be claimed until a reviewed
active schema field and verifier policy support it.

The top-results check intentionally includes `专业代码` and `专业全称`. Two rows
can share the same school, professional-group code, and short major name while
representing different tracks, such as `计算机科学与技术(腾安班，校企联合培养，校本部)`
versus `计算机科学与技术(校本部)`.

## 9. Interpretation

The results support a conservative research-engineering claim:

LLMs are useful for extracting preferences and source spans, especially when user language becomes less standardized. However, execution safety should not depend on the LLM’s own judgment. Schema grounding, rule promotion, query compilation, deterministic execution, and trace generation should be handled by symbolic components.

The strongest current result is that `deepseek_extractor_symbolic_verifier` reaches the same task success as the curated regex baseline on the 40-case benchmark while keeping deterministic over-promotion at zero. This supports the architecture boundary: the LLM can improve extraction coverage, but the verifier controls execution safety.

Schema-aware prompting is not enough by itself. It improves the LLM-only baseline, but does not enforce the rule lifecycle, human confirmation boundary, schema-grounded execution, or evidence-aligned answer generation.

## 10. Limitations

- The evaluation set is still small at 40 cases.
- The regex patterns are curated for the current examples.
- The LLM-only baselines are simplified and may not represent a highly engineered production LLM advisor.
- Token estimates for full Excel prompting are upper-bound approximations based on tokenizer-free serialization heuristics.
- There is no real user study yet.
- The current benchmark evaluates rule safety and traceability, not final college application quality.
- The MVP uses one Excel dataset and one pandas executor.
- Answer-level evaluation is currently rule/evidence alignment, not user-study
  quality or final application-strategy quality.

## 11. Next Steps

- Expand `eval_inputs.jsonl` to 50-100 cases.
- Add more paraphrases for vague terms such as safety, cost, school quality, city preference, employment, distance, and major-family expansion.
- Test DeepSeek extractor robustness across shorter, longer, incomplete, and contradictory inputs.
- Report deterministic over-promotion rate as the main safety metric.
- Report schema hallucination rate separately from general extraction accuracy.
- Add per-rule trace completeness checks.
- Add more answer-level adversarial cases for unsupported claims and duplicate-looking projected results.
- Add adversarial cases where a user mentions unsupported fields that appear semantically inferable from text fields.
- Keep the evaluation focused on preference-to-rule verification, not full college recommendation quality.
