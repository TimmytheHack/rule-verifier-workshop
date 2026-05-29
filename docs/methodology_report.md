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

The current MVP uses real Excel fields such as:

```text
生源地
科类
专业名称
城市
专业组最低位次1
学费
```

Missing but desired fields include:

```text
cooperation_type
school_reputation
employment_outlook
distance_from_home
major_family
```

These missing fields may be useful, but they are not executable until they are represented as structured, verified schema fields.

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

## 10. Evaluation Summary

The current evaluation compares task success under token budget.

Single MVP input:

| Method | Result rows | Task success | Total tokens |
|---|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | 93 | 5/5 | 0 |
| `deepseek_extractor_symbolic_verifier` | 93 | 5/5 | 762 |
| `llm_only_baseline` | n/a | 1/5 | 810 |

Fuzzy 10-input evaluation:

| Method | Score | Success rate | Total tokens |
|---|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 70/70 | 1.00 | 0 |
| `deepseek_extractor_symbolic_verifier` | 70/70 | 1.00 | 5075 |
| `llm_only_baseline` | 31/50 | 0.62 | 5329 |

Pipeline token budget comparison:

| Approach | Estimated/input tokens | Result |
|---|---:|---|
| Direct LLM with full Excel | 23,040,523 | Not executed; exceeds practical context budgets. |
| Direct LLM with MVP columns only | 483,922 | Still large and lacks deterministic verification. |
| DeepSeek extractor + symbolic verifier | 762 | 93 rows, 5/5. |
| Regex extractor + symbolic verifier | 0 | 93 rows, 5/5. |

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

- Expand `eval_inputs.jsonl` to 30-50 inputs.
- Add paraphrases for safety, cost, major family, location, school quality, and employment.
- Track deterministic over-promotion rate as the main safety metric.
- Track schema hallucination rate separately.
- Add per-rule trace completeness scoring.
- Add adversarial inputs for unsupported but tempting fields.
- Test whether DeepSeek extraction remains stable under incomplete or contradictory inputs.
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
