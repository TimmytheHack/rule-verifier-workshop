# Full Project Plan: Preference-to-Rule Verification Methodology

## 1. Final Project Positioning

The final project should be positioned as a research-engineering methodology project, not as a college application recommendation product.

Working title:

```text
Preference-to-Rule Verification: Preventing Unsafe Promotion of Natural-Language Preferences into Deterministic Rules
```

Case study:

```text
Guangdong college application planning using a structured Excel dataset.
```

Main contribution:

```text
The project studies how to decide whether a natural-language preference can be safely compiled into an executable rule, must first become a human-confirmed candidate rule, or should remain semantic / LLM-needed.
```

The central safety problem is deterministic over-promotion:

```text
Vague natural-language preferences are incorrectly treated as deterministic executable filters.
```

The project should show that good recommendation behavior begins before recommendation: it begins with schema grounding, rule verification, and explicit traceability.

## 2. Methodology Overview

The methodology pipeline:

```text
Natural-language input
-> preference decomposition
-> rule class assignment
-> schema grounding
-> rule verification
-> candidate confirmation / rejection
-> executable rule set
-> query execution
-> result trace
-> evaluation
```

Three rule classes:

1. Deterministic rules
   - Explicit.
   - Schema-grounded.
   - Type-safe.
   - Operator-valid.
   - Non-vague.
   - Executable without additional confirmation.

2. Candidate rules
   - Plausible operational interpretations.
   - Triggered by vague or subjective phrases.
   - Require human confirmation before execution.
   - May become executable only after confirmation.

3. LLM-needed / non-executable parts
   - Not safely grounded in the current schema.
   - May require explanation, external evidence, or future derived fields.
   - Must not be executed as filters in the current system.

Core principles:

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate promotion.
No trace, no verified result.
Neural proposes; symbolic verifies and executes.
```

## 3. Core Algorithms

### Preference Decomposition

Goal:

```text
Split a user input into atomic facts, preferences, vague phrases, and semantic parts.
```

Inputs:

- Raw user text.
- Domain vocabulary.
- Known vague terms.
- Optional examples.

Outputs:

- User context slots.
- Preference slots.
- Raw phrase spans.
- Unresolved semantic parts.

Example:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

Decomposes into:

- `source_province = 广东`
- `subject_type = 物理`
- `user_rank = 32000`
- `major_keyword = 计算机`
- `preferred_cities = [广州, 深圳]`
- `risk_preference_raw = 稳一点`
- `tuition_preference_raw = 太贵`
- `cooperation_preference_raw = 中外合作`

Conservative rule:

```text
Decomposition should preserve source text. It should not decide executability by itself.
```

LLM boundary:

```text
An LLM may extract preferences and preserve source spans.
It must not decide that a rule is executable.
```

### Rule Class Assignment

Goal:

```text
Assign each extracted preference to deterministic, candidate, or LLM-needed.
```

Decision logic:

1. If the phrase is explicit, maps to an existing field, uses an allowed operator, and is not vague, classify as deterministic.
2. If the phrase is vague but has plausible operational translations, classify as candidate.
3. If the phrase cannot be grounded in the current schema, classify as LLM-needed / non-executable.

LLM boundary:

```text
An LLM may propose a class label.
The final class assignment must be checked by deterministic policy, schema registry, and vague-term rules.
```

Examples:

| Phrase | Class | Reason |
|---|---|---|
| 广东物理类 | deterministic | Explicit and schema-grounded. |
| 广州深圳 | deterministic | City field exists. |
| 想学计算机 | deterministic for exact keyword only | Exact keyword match is safe. |
| 计算机相关 | candidate | Semantic expansion requires confirmation. |
| 稳一点 | candidate | Risk tolerance is vague. |
| 太贵 | candidate | Needs a threshold. |
| 中外合作 | non-executable if field missing | Cannot infer without a reliable field. |
| 就业前景好 | LLM-needed | Not represented in Excel schema. |

### Schema Grounding

Goal:

```text
Map rule fields to actual dataset fields and reject unsupported fields.
```

Inputs:

- Candidate rule object.
- `schema_registry.json`.

Checks:

- Field exists.
- Source column exists.
- Field type is declared.
- Allowed operators include the proposed operator.
- Nullable behavior is defined.
- Field notes do not prohibit use.

Output:

- Grounded rule.
- Blocked rule.
- Warning if coverage or semantics are weak.

Key guardrail:

```text
The system cannot invent fields such as cooperation_type if the dataset does not contain them.
The LLM cannot verify schema existence; schema grounding is symbolic and data-backed.
```

### Rule Verification

Goal:

```text
Determine whether a grounded rule is executable.
```

Required checks:

- Field existence check.
- Type check.
- Operator check.
- Value normalization check.
- Ambiguity check.
- Data coverage check.
- Conflict check.
- Dry-run check.
- Traceability check.

The verifier is deterministic code, not an LLM judgment. The LLM can provide a proposed rule object, but it cannot mark that rule as verified.

Verification output should include:

```json
{
  "field_exists": true,
  "operator_allowed": true,
  "type_valid": true,
  "value_normalized": true,
  "ambiguity_detected": false,
  "coverage_warning": false,
  "dry_run_passed": true,
  "executable": true
}
```

### Candidate Promotion

Goal:

```text
Promote a candidate rule into an executable rule only after explicit confirmation.
```

Examples:

```text
稳一点 -> choose safety margin 5%, 10%, or 15%.
太贵 -> choose tuition threshold.
计算机相关 -> choose expansion terms.
学校好一点 -> choose whether to use rankings, school tags, or no filter.
```

Promotion record should preserve:

- Original source text.
- Candidate proposal.
- Confirmation question.
- Selected option.
- Final rule.
- Trace reason.

Guardrail:

```text
Candidate rules must not execute with default values unless the project explicitly labels the run as simulated confirmation.
The LLM cannot promote a candidate rule. Promotion requires human confirmation or an explicitly labeled simulated-confirmation protocol.
```

### Trace Generation

Goal:

```text
Make every output row auditable.
```

Trace should show:

- Which deterministic rules passed.
- Which confirmed candidate rules passed.
- Which preferences were not executed.
- Why they were not executed.
- Key threshold values used.
- Source text for each rule.

Example:

```text
PASS 生源地 == 广东
PASS 科类 == 物理
PASS 专业名称 contains 计算机
PASS 城市 matches 深圳
PASS 专业组最低位次1 38998 >= 35200
PASS 学费 6853 <= 20000
NOT EXECUTED 中外合作: missing cooperation_type field
```

## 4. Backend Abstraction

Excel is only the first case study. The methodology should be backend-agnostic at the rule-verification level, while query compilation and execution remain backend-specific.

The backend abstraction should have five layers:

```text
Data Adapter
-> Schema Registry
-> Backend-specific Query Compiler
-> Executor
-> Result Trace
```

### Data Adapter

Purpose:

```text
Loads a concrete data source and exposes its fields, types, sample values, and coverage statistics.
```

Examples:

- Excel adapter.
- CSV adapter.
- SQL / DuckDB adapter.
- MongoDB adapter.
- API-backed adapter.

For the current MVP, the adapter is effectively:

```text
Excel workbook -> detected header row -> rows and column metadata
```

The adapter should not interpret vague preferences. It only reports what the data source actually contains.

### Schema Registry

Purpose:

```text
Defines the executable boundary independent of backend.
```

The registry should describe logical fields:

- `field_id`
- source column / source path
- type
- aliases
- allowed operators
- nullable behavior
- notes and restrictions

The same logical field may compile differently across backends. For example, `tuition_yuan_per_year <= 20000` may become a pandas boolean mask, a SQL WHERE clause, a Mongo filter, or an API parameter.

### Backend-Specific Query Compiler

Purpose:

```text
Translates verified executable rules into backend-specific query plans.
```

Compiler examples:

- pandas compiler for Excel / CSV tables.
- SQL compiler for SQL databases or DuckDB.
- Mongo compiler for MongoDB collections.
- API query compiler for tool-backed or parameterized data sources.

The compiler only accepts verified executable rules. It must reject candidate, LLM-needed, ungrounded, or unverified rules.

### Executor

Purpose:

```text
Runs a compiled query plan against a concrete backend.
```

Executor clarification:

- pandas is only the MVP executor for Excel / CSV-style tabular data.
- SQL compiler and executor can be used for SQL databases or DuckDB.
- Mongo compiler and executor can be used for MongoDB.
- API executor can be used for tool-backed data if the API exposes structured parameters.
- Non-structured text and PDF content cannot be deterministically executed until a structured schema is extracted, validated, and entered into the schema registry.

The executor must not decide rule validity. It should only run compiled plans produced after verification.

### Result Trace

Purpose:

```text
Explains how each returned result relates to the verified rule set.
```

Trace generation should be backend-independent in concept, but may depend on backend-specific row identifiers or result IDs.

Every trace should show:

- Executed rules.
- Rule pass / fail status when available.
- Non-executed preferences.
- Missing-field reasons.
- Confirmation-derived thresholds.
- Backend source identifier.

## 5. Data Artifacts

### schema_registry.json

Purpose:

```text
Defines the executable boundary of the system.
```

Recommended structure:

```json
{
  "field_id": "tuition_yuan_per_year",
  "source_column": "学费",
  "type": "number_from_string",
  "aliases": ["学费", "费用", "太贵"],
  "allowed_ops": ["<=", ">=", "between"],
  "nullable": true,
  "notes": "Requires numeric parsing from Excel cell value."
}
```

The registry should include missing-but-desired fields explicitly:

```json
{
  "field_id": "cooperation_type",
  "source_column": null,
  "status": "missing",
  "notes": "Cannot execute 中外合作 exclusion until a reliable field or approved derived classifier exists."
}
```

### rule_taxonomy.json

Purpose:

```text
Defines rule classes, allowed examples, candidate triggers, and rejection reasons.
```

Recommended categories:

- deterministic
- candidate
- confirmed_candidate
- llm_needed
- rejected_not_executable
- context

It should encode examples and policy:

```json
{
  "term": "稳一点",
  "default_class": "candidate",
  "allowed_promotions": ["safety_margin_5", "safety_margin_10", "safety_margin_15"],
  "requires_human_confirmation": true
}
```

### vague_terms.json

Purpose:

```text
Lists terms that should block deterministic execution unless confirmed.
```

Examples:

```json
[
  {"term": "稳一点", "class": "risk_vague", "candidate_action": "ask_safety_margin"},
  {"term": "太贵", "class": "threshold_vague", "candidate_action": "ask_tuition_cap"},
  {"term": "相关", "class": "semantic_expansion", "candidate_action": "ask_expansion_terms"},
  {"term": "好一点", "class": "quality_vague", "candidate_action": "ask_quality_proxy"},
  {"term": "就业前景好", "class": "external_semantic", "candidate_action": "llm_needed"}
]
```

### eval_inputs.jsonl

Purpose:

```text
Benchmark inputs for evaluating extraction, classification, verification, and over-promotion.
```

Each row should contain:

```json
{
  "id": "T01",
  "input": "广东物理，排位32000，想学计算机，稳一点。",
  "expected_slots": {},
  "expected_rule_classes": {},
  "must_not_execute": ["稳一点_without_confirmation"],
  "notes": "Tests candidate rule handling."
}
```

## 6. Engineering Phases

### Phase 1: Stabilize MVP

Goal:

```text
Make the current single-input demo reproducible and clearly documented.
```

Tasks:

- Keep the current pipeline narrow.
- Ensure outputs are deterministic.
- Add basic tests around current behavior.
- Keep Chinese documentation aligned with the English version.
- Confirm generated outputs do not hide non-executed preferences.

Exit criteria:

- Demo runs from README instructions.
- Result count and rule behavior are reproducible.
- `cooperation_type` remains non-executable unless schema changes.

### Phase 2: Rule Taxonomy

Goal:

```text
Formalize what counts as deterministic, candidate, or LLM-needed.
```

Tasks:

- Create `rule_taxonomy.json`.
- Create `vague_terms.json`.
- Define promotion policies.
- Define rejection reasons.
- Add examples from Guangdong志愿填报 language.

Exit criteria:

- Rule class assignment is policy-driven rather than scattered in code.
- Vague terms reliably trigger candidate or LLM-needed status.

### Phase 3: Evaluation Benchmark

Goal:

```text
Measure whether the methodology prevents unsafe rule promotion.
```

Tasks:

- Create `eval_inputs.jsonl`.
- Include positive, candidate, and negative cases.
- Add expected rule classes.
- Add expected non-executable preferences.
- Implement evaluation script later, after the benchmark is stable.

Exit criteria:

- At least 30 curated test inputs.
- Covers risk, cost, major expansion, location, school quality, and missing fields.
- Reports deterministic over-promotion rate.

### Phase 4: Optional LLM Extractor

Goal:

```text
Replace hardcoded slots with an extractor while keeping the verifier as the safety authority.
```

Tasks:

- Add an optional extractor interface.
- Require JSON output with source spans.
- Run extractor output through the same verifier.
- Compare LLM extraction with gold labels.

Guardrail:

```text
The LLM may propose rules, but it must not decide executability.
Neural proposes; symbolic verifies and executes.
```

LLM boundary:

- The LLM can extract preferences.
- The LLM can preserve source spans.
- The LLM can propose candidate rules.
- The LLM cannot promote candidate rules.
- The LLM cannot verify schema existence.
- The LLM cannot compile backend queries.
- The LLM cannot execute deterministic filters.

Exit criteria:

- LLM extraction improves coverage without increasing deterministic over-promotion.
- Verifier remains deterministic and testable.

### Phase 5: Generalization Demo

Goal:

```text
Show the methodology can transfer to another structured decision domain.
```

Candidate domains:

- Course selection.
- Rental filtering.
- Job filtering.
- Product recommendation.

Tasks:

- Choose one small structured dataset.
- Build a domain-specific schema registry.
- Create 5 to 10 test inputs.
- Demonstrate the same three-class rule behavior.

Exit criteria:

- Shows that the contribution is not tied only to college applications.
- Does not overbuild a second full product.

## 7. Evaluation Metrics

Primary metric:

```text
deterministic over-promotion rate
```

Definition:

```text
Number of vague or unsupported preferences incorrectly classified as deterministic
/ total vague or unsupported preferences
```

This should be near zero.

Supporting metrics:

- Slot extraction precision.
- Slot extraction recall.
- Field mapping accuracy.
- Rule class accuracy.
- Candidate recall.
- Schema violation rate.
- Invalid rule rejection rate.
- Confirmation question accuracy.
- Executable rule success rate.
- Trace completeness.
- Non-executed preference visibility.

Recommended reporting:

| Metric | Why it matters |
|---|---|
| Deterministic over-promotion rate | Main safety metric. |
| Candidate recall | Ensures vague terms are caught. |
| Schema violation rate | Detects invented or unsupported fields. |
| Trace completeness | Ensures outputs are auditable. |
| Invalid rule rejection rate | Measures verifier strictness. |

## 8. Expected Final Outputs

Final project artifacts:

- Methodology paper or report.
- Reproducible MVP demo.
- `schema_registry.json`.
- `rule_taxonomy.json`.
- `vague_terms.json`.
- `eval_inputs.jsonl`.
- Evaluation summary.
- Rule verification protocol.
- Backend abstraction specification.
- Example result traces.
- Discussion of failures and limitations.

Final report structure:

1. Motivation.
2. Problem definition.
3. Methodology.
4. Case study dataset.
5. Rule taxonomy.
6. Verification protocol.
7. MVP implementation.
8. Evaluation benchmark.
9. Results.
10. Limitations.
11. Generalization.

## 9. Risks And Guardrails

### Risk: Vague preference over-promotion

Guardrail:

```text
Terms such as 稳一点, 太贵, 相关, 好一点 must trigger candidate handling.
```

### Risk: Schema hallucination

Guardrail:

```text
Fields absent from schema_registry.json cannot be executed.
```

### Risk: Hidden derived fields

Guardrail:

```text
Derived fields require documented derivation logic, evaluation, and explicit approval.
```

### Risk: LLM authority creep

Guardrail:

```text
The LLM can extract or propose; the verifier decides executability.
Neural proposes; symbolic verifies and executes.
```

The LLM must not:

- Promote candidate rules.
- Verify schema grounding.
- Compile backend queries.
- Execute deterministic filters.
- Invent missing fields.

### Risk: Misleading recommendation framing

Guardrail:

```text
Outputs should be described as verified rule results, not final志愿建议.
```

### Risk: Overfitting to one Excel file

Guardrail:

```text
Separate schema registry, rule taxonomy, and evaluation inputs from the code.
Treat Excel as the first backend, not the whole methodology.
```

### Risk: Treating unstructured documents as executable data

Guardrail:

```text
PDFs, free text, and documents cannot be deterministically queried until structured fields are extracted, validated, and registered in schema_registry.json.
```

## 10. What Not To Build

Do not build these until the methodology is evaluated:

- A full志愿填报 advisor bot.
- A multi-turn counseling system.
- A final志愿表 generator.
- Admission probability prediction.
- School reputation scoring.
- Employment outcome prediction.
- External web-search based recommendation.
- Automatic 中外合作 classifier.
- Automatic semantic major expansion without confirmation.
- A universal symbolic reasoning engine.
- A generic backend framework before the methodology is evaluated.
- Deterministic execution over unstructured text or PDF without verified schema extraction.

The project should remain focused:

```text
preference -> rule class -> schema grounding -> verification -> trace
```

## 11. Professor-Facing Summary

This project studies a safety problem in LLM-assisted structured decision systems: natural-language preferences often contain a mixture of explicit constraints, vague preferences, and unsupported semantic desires. A system that directly converts all of them into filters can produce misleading deterministic outputs.

Using Guangdong college application planning as a case study, the project proposes a preference-to-rule verification methodology. The system decomposes user input, assigns each preference to one of three classes, grounds executable rules in an Excel schema, verifies field and operator validity, requires human confirmation for vague candidate rules, rejects unsupported fields, and produces row-level traces.

The first MVP demonstrates this approach on one realistic input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

The system safely executes explicit rules such as `科类 == 物理`, `专业名称 contains 计算机`, and `城市 contains 广州 or 深圳`. It promotes `稳一点` and `太贵` only through simulated confirmation. It refuses to execute `中外合作` because the dataset lacks a reliable `cooperation_type` field.

The main contribution is not recommendation quality. The main contribution is a conservative verification framework that prevents unsafe promotion of vague natural-language preferences into deterministic executable rules. This methodology can generalize to other structured decision domains such as course selection, rental filtering, job search, product recommendation, and investment screening.

Excel is only the first backend used to demonstrate the method. In a larger system, verified rules could compile to pandas, SQL / DuckDB, MongoDB, or structured API calls. The boundary remains the same across backends: neural components may extract and propose, but symbolic schema grounding, verification, compilation, execution, and trace generation control what is actually run.
