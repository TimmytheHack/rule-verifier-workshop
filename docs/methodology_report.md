# Methodology Report: Preference-to-Rule Verification

## 1. Project Positioning

This project is a research-engineering methodology project, not a normal college recommendation bot.

The case study is Guangdong college application planning using a structured Excel dataset. The research question is:

```text
When a user expresses preferences in natural language, which parts can be safely compiled into deterministic executable rules, which parts require human confirmation, and which parts should remain semantic or LLM-handled?
```

The main contribution is preventing unsafe promotion of vague natural-language preferences into deterministic executable rules.

The system should not directly answer with a final recommendation list unless it can explain:

- which user preferences became executable rules;
- which preferences required confirmation;
- which preferences could not be executed because the schema does not support them;
- why each returned row satisfies the verified rules.

## 2. Why This Is Not A Recommendation Bot

A normal recommendation bot tries to produce useful suggestions directly. This project studies the step before recommendation:

```text
natural-language preference -> verified executable rule set
```

The current system does not generate a full志愿表, rank schools by reputation, predict employment outcomes, or make broad admission judgments. It focuses on whether a preference can be grounded in actual data fields and executed safely.

This distinction matters because a vague phrase can become misleading when it is silently turned into a precise filter. For example:

```text
学校稳一点
```

should not automatically become:

```text
录取概率 = 高
```

or:

```text
safety_level = 稳妥
```

unless the system has a schema-grounded rule and the user confirms the interpretation.

## 3. Methodology Pipeline

The current methodology is:

```text
Natural-language input
-> preference decomposition
-> rule class assignment
-> schema grounding
-> rule verification
-> human confirmation
-> candidate promotion or rejection
-> executable rule set
-> backend-specific query execution
-> result trace
-> evaluation
```

Core principles:

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
No trace, no verified result.
Neural proposes; symbolic verifies and executes.
```

The upgraded implementation also records a rule lifecycle boundary in
`rules/rule_lifecycle_schema.json`:

```text
extracted_preference
-> proposed_rule
-> schema_grounded_rule
-> verified_rule
-> confirmed_rule
-> executable_rule
-> executed_rule
-> traced_result
```

This lifecycle is important because it separates what an extractor proposes from what the verifier allows to execute.

The implementation also adds an attribute-level grounding audit before rule construction:

```text
extracted attributes
-> attribute grounding audit
-> rule construction
-> rule verification
```

This means extracted attributes do not need to be executable by default. They must first be labeled as one of:

| Attribute status | Meaning |
|---|---|
| `schema_grounded` | Maps to an active Excel schema field, but still needs rule verification. |
| `confirmable` | Maps to an active field but is vague or semantic, so user confirmation is required. |
| `context_only` | Useful for formulas or context, but not an Excel filter. |
| `missing_schema` | No active Excel field exists; cannot execute. |
| `ignored_not_schema_mapped` | Extractor emitted an unknown attribute; rule construction ignores it. |

This closes an important gap: an extractor may mention attributes such as `公办`, `学校名气`, or `偏远城市`, but those attributes cannot become executable rules unless they are grounded in the Excel schema.

## 4. Rule Classes

### Deterministic Rules

Deterministic rules are explicit, schema-grounded, type-safe, and directly executable.

Examples from the MVP:

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
```

Exact keyword match can be deterministic when the field exists and the operation is allowed.

### Candidate Rules

Candidate rules are plausible operational interpretations of vague preferences. They must not execute until the user confirms the interpretation.

Examples:

```text
稳一点 -> choose safety margin: 5%, 10%, or 15%
太贵 -> choose tuition cap
计算机相关 -> choose whether to include 软件工程, 人工智能, 数据科学, 网络安全
学校好一点 -> choose an explicit ranking/tag source, or do not execute
```

Candidate rules are intentionally blocked until promotion.

### LLM-Needed Or Non-Executable Parts

LLM-needed or non-executable parts are preferences that cannot be safely grounded in the current schema.

Example:

```text
不要中外合作
```

In the current Excel schema, there is no dedicated `cooperation_type` field. Therefore the system preserves this preference but does not execute it.

The system also avoids deriving `cooperation_type` from free-text fields in the MVP. That inference may be possible later, but only after creating and verifying a derived structured field.

## 5. Current Demo

Input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

Extracted preferences:

```json
{
  "source_province": "广东",
  "subject_type": "物理",
  "user_rank": 32000,
  "major_keyword": "计算机",
  "preferred_cities": ["广州", "深圳"],
  "risk_preference_raw": "稳一点",
  "tuition_preference_raw": "太贵",
  "cooperation_preference_raw": "不想去太贵的中外合作"
}
```

Simulated confirmations:

```text
稳一点 -> safety margin = 10%
太贵 -> tuition cap = 20000
计算机相关扩展 -> false
```

Final executable rules:

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

The threshold `35200` is derived from:

```text
32000 * 1.10 = 35200
```

The current workbook run produces 93 filtered rows.

## 6. Schema Registry As System Boundary

The schema registry defines what the system may execute. A rule cannot become deterministic unless its field is present in the registry and passes verification.

Attribute extraction is allowed to be broader than the executable schema, but execution is not. Every extracted slot must be audited against the schema boundary before rule construction.

The current MVP uses real Excel fields such as:

```text
生源地
科类
专业名称
城市
专业组最低位次1
学费
```

Fields not yet active in the MVP schema registry include:

```text
cooperation_type
school_ownership
school_reputation
employment_outlook
distance_from_home
major_family
major_popularity
city_remoteness
```

Some of these concepts now have candidate Excel columns discovered by the schema profile:

- `school_ownership` may map to `公私性质`.
- `school_reputation` may partially map to `院校水平`, `院校标签`, `院校排名`, or `软科排名`.
- `city_remoteness` or city quality may partially map to `城市水平标签`.
- `major_popularity` may require a policy decision; current Excel fields such as `专业类` or `专业水平` are not the same as popularity.

These fields are not automatically executable. They need human schema review, allowed operators, semantic notes, and tests before promotion into the active schema registry.

## 7. Backend Abstraction

Excel is only the first case study. The methodology separates rule verification from data execution.

The backend abstraction is:

| Component | Responsibility |
|---|---|
| Data Adapter | Load source data and expose real fields. |
| Schema Registry | Define fields, types, aliases, allowed operators, nullability, and notes. |
| Backend-specific Query Compiler | Convert verified rules into pandas, SQL, MongoDB, or API-specific query form. |
| Executor | Execute compiled rules against the backend. |
| Result Trace | Explain which rules produced each result. |

Current executor:

```text
pandas executor for Excel/CSV
```

Future executors can include:

```text
SQL / DuckDB compiler
MongoDB compiler
API executor for tool-backed data
```

Non-structured text and PDF cannot be deterministically executed until structured schema has been extracted and verified.

## 8. LLM Boundary

The optional DeepSeek extractor is used only for preference extraction and source spans.

Allowed LLM roles:

- extract user context;
- extract preference slots;
- preserve source spans;
- propose candidate interpretations.

Disallowed LLM roles:

- promote candidate rules;
- verify schema existence;
- decide final executability;
- compile queries;
- execute deterministic filters;
- claim that missing fields exist.

All DeepSeek output goes through the same rule classifier and symbolic verifier as regex output.

## 9. Rule Verification Protocol

Each executable rule must pass:

- field existence check;
- source column existence check;
- type check;
- operator check;
- value normalization check;
- ambiguity check;
- data coverage check;
- conflict check;
- dry-run check;
- traceability check.

Verification output must explain why a rule is executable, blocked, or waiting for confirmation.

The verifier now produces a verification profile rather than only a pass/fail result:

```json
{
  "schema_grounded": true,
  "field_exists": true,
  "source_column_exists": true,
  "operator_allowed": true,
  "type_valid": true,
  "value_present": true,
  "value_normalized": true,
  "ambiguity_level": "none",
  "requires_human_confirmation": false,
  "execution_level": "executable",
  "executable": true
}
```

The key execution levels are:

| Execution level | Meaning |
|---|---|
| `executable` | Deterministic, schema-grounded, and ready to execute. |
| `confirmable` | Schema-grounded but vague or confirmation-gated. |
| `context_only` | Useful context, not a dataset filter. |
| `blocked` | Grounded but not currently executable. |
| `rejected` | Not schema-grounded. |

## 10. Evaluation Summary

The current evaluation compares task success under token budget.

Single MVP input:

| Method | Result rows | Task success | Total tokens | Over-promotion |
|---|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | 93 | 5/5 | 0 | 0 |
| `deepseek_extractor_symbolic_verifier` | 93 | 5/5 | 689 | 0 |
| `llm_only_baseline` | n/a | 1/5 | 824 | unsafe |
| `schema_aware_llm_only_baseline` | n/a | 2/5 | 1212 | unsafe |

40-case fuzzy evaluation:

| Method | Score | Success rate | Total tokens | Over-promotion rate |
|---|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 1.000 | 0 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 1.000 | 23528 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.535 | 23955 | 0.450 |
| `schema_aware_llm_only_baseline` | 157/200 | 0.785 | 43069 | 0.300 |

The benchmark now contains 40 layered inputs covering clear, vague, unsupported, mixed, adversarial, contradictory, and end-to-end demo cases. The DeepSeek extractor previously scored `314/320`; after representation normalization for multi-major terms, broader city normalization, and school-ownership preference preservation, it reached `320/320`. This improvement came from better slot representation, not from relaxing the verifier.

The baseline comparison includes:

| Method | Purpose |
|---|---|
| `llm_only_baseline` | Naive LLM-only rule proposal. |
| `schema_aware_llm_only_baseline` | Stronger LLM-only baseline that receives schema context but still has no symbolic verifier. |
| `deepseek_extractor_symbolic_verifier` | LLM extraction with symbolic verification. |
| `regex_extractor_symbolic_verifier` | Conservative symbolic extraction baseline. |

Pipeline token budget comparison:

| Approach | Estimated/input tokens | Result |
|---|---:|---|
| Direct LLM with full Excel | 23,040,523 | Not executed; exceeds practical context budgets. |
| Direct LLM with MVP columns only | 483,922 | Still large and lacks deterministic verification. |
| DeepSeek extractor + symbolic verifier | 689 | 93 rows, 5/5. |
| Regex extractor + symbolic verifier | 0 | 93 rows, 5/5. |
| Schema-aware LLM-only baseline | 1212 | 2/5; still unsafe. |

The strongest evidence so far is not that LLMs are useless. It is that LLM extraction becomes safer when symbolic verification controls execution.

## 11. Current Limitations

The current system is still narrow.

Limitations:

- The evaluation set is small.
- Regex extraction is curated for current examples.
- DeepSeek extraction has not been stress-tested at scale.
- Human confirmation is simulated.
- The system uses one Excel dataset and a pandas executor.
- It does not generate a full志愿表.
- It does not evaluate school reputation.
- It does not predict employment outcomes.
- It does not infer `cooperation_type` from text fields.
- Token estimates for direct Excel prompting are approximate.

These limitations are acceptable for the current research stage because the goal is rule verification methodology, not a complete advising product.

## 12. Next Methodology Work

Next steps should focus on evaluation and safety:

- Expand `eval_inputs.jsonl` beyond the current 40 inputs if additional user phrasings are collected.
- Add paraphrases for safety, cost, major family, location, school quality, and employment.
- Track deterministic over-promotion rate as the main safety metric.
- Track schema hallucination rate separately.
- Add per-rule trace completeness scoring.
- Add adversarial inputs for unsupported but tempting fields.
- Test whether DeepSeek extraction remains stable under incomplete or contradictory inputs.
- Expand the 40-case benchmark toward 50-100 cases with more real paraphrases.
- Stress-test whether the `320/320` DeepSeek result holds when inputs become longer, noisier, or contradictory.
- Keep recommendation quality evaluation separate from rule verification evaluation.

## 13. Generalization

The methodology can generalize to other structured decision systems where users express natural-language preferences over structured data:

- course selection;
- rental filtering;
- job filtering;
- product recommendation;
- investment screening;
- scholarship or program matching.

The reusable idea is not the Guangdong-specific rules. The reusable idea is the boundary:

```text
Natural language may propose structure, but only verified schema-grounded rules may execute.
```
