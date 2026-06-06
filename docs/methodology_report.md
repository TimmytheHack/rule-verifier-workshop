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

## 3. Minimum Executable Information

The first step of a college application planning system is not recommendation. It is checking whether the system has the minimum executable information: applicant rank, subject type, application batch, target data fields, and explicit preference boundaries. When that information is missing, the system should ask a follow-up question or mark the request as non-executable instead of letting an LLM directly generate advice.

For Guangdong, the minimum user gate is:

```text
source province = 广东
subject type = 物理 / 历史
rank = user_rank
batch = 本科 / 专科 / 提前批, etc.
```

Rank is more important than score. Score lines fluctuate by year, while rank is more suitable for comparison with historical admission data. If the user provides only a score and no rank, the system should ask:

```text
请提供你的省排名/位次。仅凭分数无法稳定判断风险。
```

The minimum executable dataset fields include:

```text
院校名称
院校代码
院校专业组代码
专业名称
专业代码
科类
批次
城市
计划人数
学费
往年最低分
往年最低位次
专业组最低位次
选科要求
本科/专科
公私性质
院校标签 / 院校水平
```

For Guangdong, outputting only school names is not enough because many decisions happen at the `院校专业组 + 专业` level. A valid output should at least include:

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

Risk judgment needs `user_rank`, historical professional-group minimum rank, historical major minimum rank, enrollment plan count, whether the major or group is new, and two- or three-year admission trends. The MVP currently uses only `专业组最低位次1`. That is enough to demonstrate rule verification, but the methodology must state the limitation: one year of rank data is not stable enough. A fuller system should use 2-3 years of minimum ranks, plan-count changes, and new-major/new-group flags.

User preferences are handled in three classes:

| Class | Examples | Handling |
|---|---|---|
| Deterministic | `学费两万以内`, `城市在广州深圳`, `专业名称包含计算机` | Executable when the field exists and the value boundary is explicit. |
| Candidate | `稳一点`, `太贵`, `计算机相关`, `学校好一点`, `离家近` | Requires confirmation of thresholds, sets, proxy metrics, or home location. |
| LLM/external/reference only | `就业前景好`, `学校氛围好`, `宿舍条件好`, `专业未来趋势`, `城市发展潜力` | Cannot execute without a corresponding field; preserve as explanation, external-info need, or reference context. |

The final natural-language answer also has minimum requirements: explain which rules executed, which rules need confirmation, which preferences were not executed, how many rows were found, which top results are shown, why each result was retained, what risks remain, and what the user should provide next.

These categories are recorded in `rules/information_requirements.json` as an auditable boundary between methodology and executable rules.

## 4. Methodology Pipeline

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
-> evidence pack
-> answer/report generation
-> evaluation
```

Core principles:

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
No trace, no verified result.
No evidence pack, no final answer.
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
-> evidence_pack
-> generated_answer
```

This lifecycle is important because it separates what an extractor proposes from what the verifier allows to execute.

The answer layer is deliberately downstream of tracing. It does not inspect raw
Excel and it does not decide executability. It receives an evidence pack with:

- `user_request`;
- `executed_rules`;
- `candidate_confirmations`;
- `not_executed_preferences`;
- `result_count`;
- `top_k_results`;
- `trace_summary`.

`TemplateReportBuilder` renders this evidence deterministically in Chinese.
`DeepSeekAnswerGenerator` is optional; it receives only the same evidence pack.
Because LLM output can omit required fields, the DeepSeek path appends a
deterministic evidence coverage checklist that includes executed rules, top
professional-group results, not-executed preferences, and safety warnings.

The answer-level minimum result shape includes `院校名称`, `院校专业组代码`,
`专业代码`, `专业名称`, `专业全称`, `城市`, `学费`, `专业组最低位次`,
`专业最低位次` when available, and safety margin. `专业代码` and `专业全称`
are required because two rows can share the same school, professional-group
code, and short major name while representing different tracks.

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

## 5. Rule Classes

### Deterministic Rules

Deterministic rules are explicit, schema-grounded, type-safe, and directly executable.

Examples from the MVP:

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
学费 <= 20000
```

Exact keyword match or an explicit numeric boundary can be deterministic when the field exists and the operation is allowed. For example, `学费两万以内` can normalize to `学费 <= 20000`; `太贵` has no explicit threshold and remains a candidate rule.

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

## 6. Current Demo

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

## 7. Schema Registry As System Boundary

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

## 8. Backend Abstraction

Excel is only the first case study. The methodology separates rule verification from data execution.

The backend abstraction is:

| Component | Responsibility |
|---|---|
| Data Adapter | Load source data and expose real fields. |
| Schema Registry | Define fields, types, aliases, allowed operators, nullability, and notes. |
| Backend-specific Query Compiler | Convert verified rules into pandas, SQL, MongoDB, or API-specific query form. |
| Executor | Execute compiled rules against the backend. |
| Result Trace | Explain which rules produced each result. |
| Evidence Pack | Package verified rules, confirmations, non-executed preferences, top results, and trace summary for answer generation. |
| Report Builder / Answer Generator | Generate the final answer from the evidence pack only. |

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

## 9. LLM Boundary

The optional DeepSeek extractor is used only for preference extraction and source spans.

Allowed LLM roles:

- extract user context;
- extract preference slots;
- preserve source spans;
- propose candidate interpretations.
- generate answer prose from a verified evidence pack.

Disallowed LLM roles:

- promote candidate rules;
- verify schema existence;
- decide final executability;
- compile queries;
- execute deterministic filters;
- claim that missing fields exist.
- read raw Excel during answer generation;
- add admissions, employment, cooperation-type, dorm, or school-quality facts
  that are not in the evidence pack.

All DeepSeek output goes through the same rule classifier and symbolic verifier as regex output.

For answer generation, DeepSeek output is treated as prose only. The system
appends deterministic evidence coverage so that the final answer still contains
the verified rules, top results, non-executed preferences, and safety warnings
even if the model omits them.

## 10. Rule Verification Protocol

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

## 11. Evaluation Summary

The current evaluation compares task success under token budget.

Single MVP input:

| Method | Result rows | Task success | Total tokens | Over-promotion |
|---|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | 93 | 5/5 | 0 | 0 |
| `deepseek_extractor_symbolic_verifier` | 93 | 5/5 | 834 | 0 |
| `llm_only_baseline` | n/a | 1/5 | 818 | unsafe |
| `schema_aware_llm_only_baseline` | n/a | 1/5 | 1282 | unsafe |

40-case fuzzy evaluation:

| Method | Score | Success rate | Total tokens | Over-promotion rate |
|---|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 1.000 | 0 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 1.000 | 25334 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.535 | 24388 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.780 | 42916 | 0.275 |

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
| DeepSeek extractor + symbolic verifier | 834 | 93 rows, 5/5. |
| Regex extractor + symbolic verifier | 0 | 93 rows, 5/5. |
| Schema-aware LLM-only baseline | 1282 | 1/5; still unsafe. |

Answer-level evaluation:

| Answer mode | Input boundary | Expected result |
|---|---|---|
| `llm_only_schema_sample` | User request, schema summary, sample projected rows | Baseline; often fails because it lacks verified executed rules, non-executed preference status, and trace summary. |
| `pipeline_template` | Verified evidence pack only | 5/5 evidence alignment; no LLM. |
| `pipeline_deepseek_evidence` | Verified evidence pack only | 5/5 evidence alignment after deterministic evidence coverage is appended. |

Answer-level scoring checks result count, executed rules, top projected
professional-group results, not-executed preferences, and unsupported claims.
Unsupported means unsupported by the verified evidence pack, not necessarily
absent from the raw Excel workbook.

The strongest evidence so far is not that LLMs are useless. It is that LLM extraction becomes safer when symbolic verification controls execution.

## 12. Current Limitations

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

## 13. Next Methodology Work

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

## 14. Generalization

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
