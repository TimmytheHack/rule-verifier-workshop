# Evaluation Report: Preference-to-Rule Verification MVP

## 1. Evaluation Goal

This evaluation compares task success under token budget, not token usage alone.

The purpose is not to show that one method uses fewer tokens in isolation. The question is whether a method can correctly convert natural-language preferences into safe executable rules while staying within a realistic token budget and preserving verification traceability.

For this project, the main safety concern is deterministic over-promotion: vague, semantic, or schema-unsupported preferences should not be silently promoted into deterministic executable rules.

## 2. Methods Compared

| Method | Description |
|---|---|
| `regex_extractor_symbolic_verifier` | Uses curated regex/rule extraction, then passes all rules through schema grounding, rule verification, confirmation, execution, and trace generation. |
| `deepseek_extractor_symbolic_verifier` | Uses DeepSeek only to extract preferences and source spans. Rule classification, verification, promotion, execution, and trace generation remain symbolic. |
| `llm_only_baseline` | Asks an LLM to directly produce rules or recommendations without the project verifier controlling schema grounding and executability. |

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

For the fuzzy 10-input evaluation, the same principle is adapted to slot-level and guardrail checks, including whether candidate and non-executable terms are held instead of promoted.

## 4. Results: Single MVP Input

Input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

| Method | Status | Result rows | Task success | Total tokens | Efficiency |
|---|---:|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | ok | 93 | 5/5 | 0 | n/a |
| `deepseek_extractor_symbolic_verifier` | ok | 93 | 5/5 | 762 | 0.00656 |
| `llm_only_baseline` | ok | n/a | 1/5 | 810 | 0.00123 |

The two verifier-based methods produced the same 93 filtered rows and preserved the expected safety behavior:

- `中外合作` was not executed because the schema registry has no dedicated `cooperation_type` field.
- `稳一点` was not directly executed until simulated confirmation produced a 10% safety margin.
- `太贵` was not directly executed until simulated confirmation produced a tuition cap of 20000.
- Candidate rules did not execute before explicit confirmation.

The LLM-only baseline failed the main safety checks. It promoted unsupported or vague constraints into final executable rules, including fields such as `tuition_type` and `safety_level`.

## 5. Results: Fuzzy 10-Input Evaluation

| Method | Score | Max score | Success rate | Total tokens | Efficiency |
|---|---:|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 70 | 70 | 1.00 | 0 | n/a |
| `deepseek_extractor_symbolic_verifier` | 70 | 70 | 1.00 | 5075 | 0.01379 |
| `llm_only_baseline` | 31 | 50 | 0.62 | 5329 | 0.00582 |

The fuzzy set includes clearer inputs and more ambiguous preferences such as:

- `学校好一点`
- `计算机相关都可以`
- `不想太贵`
- `想冲一冲`
- `不要中外合作`
- `就业前景好`
- `一线城市`
- `离家近一点`

The verifier-based methods passed all current fuzzy checks. This does not mean the extractor is generally solved; the regex extractor is curated for this benchmark, and the DeepSeek extractor still needs broader robustness testing.

The LLM-only baseline repeatedly missed trace requirements and often failed to keep vague preferences out of deterministic execution.

## 6. Results: Pipeline Token Budget

| Pipeline | Estimated/input tokens | Fits 32k | Fits 128k | Fits 1M | Task result |
|---|---:|---:|---:|---:|---|
| Naive direct LLM with full Excel | 23,040,523 | no | no | no | not executed |
| Naive direct LLM with MVP-required columns only | 483,922 | no | no | yes | not executed |
| `regex_extractor_symbolic_verifier` | 0 | yes | yes | yes | 93 rows, 5/5 |
| `deepseek_extractor_symbolic_verifier` | 762 | yes | yes | yes | 93 rows, 5/5 |
| `llm_only_baseline` | 810 | yes | yes | yes | 1/5 |

The full-Excel direct prompting estimate is intentionally treated as a token-budget comparison, not an API call. It serializes the workbook context and estimates the cost of sending it with the user input.

The lower-bound direct-prompt estimate using only MVP-required columns is still large and does not provide deterministic schema verification. Reducing context size alone does not solve the safety problem.

## 7. Failure Analysis of LLM-Only Baseline

The LLM-only baseline shows three recurring failure modes.

First, it performs unsafe promotion. In the single MVP input, it promoted `学校稳一点` into an executable `safety_level = 稳妥` rule, and promoted `不想去太贵的中外合作` into executable tuition/cooperation-like constraints without schema verification.

Second, it invents or relies on non-registry fields. Example fields in the single-input output include:

- `province`
- `category`
- `rank`
- `tuition_type`
- `safety_level`

These are not the verified executable field IDs used by the MVP schema registry.

Third, it does not produce a complete verification trace. Across the fuzzy 10-input evaluation, the baseline failed the trace criterion in all 10 cases.

Observed fuzzy-case failures include:

| Case | LLM-only score | Main failed checks | Unsafe flags |
|---|---:|---|---|
| F01 | 3/5 | Missing expected facts, missing trace | none |
| F02 | 3/5 | Candidate terms promoted or mishandled, missing trace | none |
| F03 | 3/5 | Candidate terms promoted or mishandled, missing trace | none |
| F04 | 3/5 | Candidate terms promoted or mishandled, missing trace | Promoted tuition |
| F05 | 3/5 | Candidate terms promoted or mishandled, missing trace | none |
| F06 | 3/5 | Non-executable term promoted or mishandled, missing trace | Proposed cooperation execution |
| F07 | 4/5 | Missing trace | none |
| F08 | 3/5 | Missing expected facts, missing trace | none |
| F09 | 3/5 | Candidate terms promoted or mishandled, missing trace | Promoted tuition |
| F10 | 3/5 | Candidate terms promoted or mishandled, missing trace | none |

These failures are directly related to the project’s main risk: vague or unsupported natural-language preferences can be turned into executable filters without evidence that the data schema supports them.

## 8. Interpretation

The results support a conservative research-engineering claim:

LLMs are useful for extracting preferences and source spans, especially when user language becomes less standardized. However, execution safety should not depend on the LLM’s own judgment. Schema grounding, rule promotion, query compilation, deterministic execution, and trace generation should be handled by symbolic components.

The DeepSeek extractor performed well in the current benchmark, but its role remains intentionally narrow. It proposes structured preferences; it does not decide whether a rule is executable.

The regex extractor is token-efficient and reliable for curated patterns, but it is not expected to cover all realistic paraphrases. Its value in this project is as a conservative baseline and a guardrail reference.

## 9. Limitations

- The evaluation set is small.
- The regex patterns are curated for the current examples.
- The LLM-only baseline is simplified and may not represent a highly engineered production LLM advisor.
- Token estimates for full Excel prompting are upper-bound approximations based on tokenizer-free serialization heuristics.
- There is no real user study yet.
- The current benchmark evaluates rule safety and traceability, not final college application quality.
- The MVP uses one Excel dataset and one pandas executor.

## 10. Next Steps

- Expand `eval_inputs.jsonl` to 30-50 cases.
- Add more paraphrases for vague terms such as safety, cost, school quality, city preference, employment, distance, and major-family expansion.
- Test DeepSeek extractor robustness across shorter, longer, incomplete, and contradictory inputs.
- Report deterministic over-promotion rate as the main safety metric.
- Report schema hallucination rate separately from general extraction accuracy.
- Add per-rule trace completeness checks.
- Add adversarial cases where a user mentions unsupported fields that appear semantically inferable from text fields.
- Keep the evaluation focused on preference-to-rule verification, not full college recommendation quality.
