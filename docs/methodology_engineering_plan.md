# Preference-to-Rule Verification Methodology for Guangdong College Application Planning

## 1. Project Motivation

This project is not a normal college recommendation bot. The goal is to study how natural-language preferences can be converted into verifiable rules when the decision context is backed by structured data.

In college application planning, an LLM should not directly recommend志愿 from a user's free-form description. The input often mixes hard facts, soft preferences, risk tolerance, financial constraints, and vague value judgments. If an LLM silently turns vague phrases into executable filters, it can create false precision.

For example:

- "广东物理类" can safely become a deterministic rule if the dataset has a subject-type field.
- "广州深圳" can become a city filter if the dataset has a city field.
- "稳一点" cannot safely become a fixed safety margin unless the user confirms what "stable" means.
- "太贵" cannot become a tuition rule until a tuition threshold is specified.
- "就业前景好" usually cannot be verified from the Excel dataset and should remain semantic or require external evidence.

The most dangerous failure mode is **deterministic over-promotion**: a vague or semantic preference is incorrectly promoted into a deterministic executable rule. This project treats that as the core safety risk.

## 2. Methodology Definition

The methodology is:

```text
Natural language preference
-> preference decomposition
-> rule class assignment
-> schema grounding
-> rule verification
-> human confirmation
-> executable rule or rejection
-> result trace
```

Each step has a safety purpose:

- Preference decomposition separates facts, preferences, constraints, and vague intentions.
- Rule class assignment decides whether each preference is deterministic, candidate, or LLM-needed.
- Schema grounding checks whether the preference can be mapped to an actual data field.
- Rule verification checks type, operator, value, ambiguity, data coverage, and traceability.
- Human confirmation prevents vague preferences from being silently executed.
- Result trace makes every filtered result explainable.

The methodology is intentionally narrow. It does not attempt to build a general symbolic AI system. It studies how to safely compile user preferences into rules for one structured decision dataset.

## 3. Case Study Scope

The first case study is Guangdong college application planning using the "广东省2025年志愿填报大数据（24-25）" Excel dataset.

The project does not try to solve all志愿填报 problems. It does not generate a complete志愿表, predict admissions, judge school reputation, or provide final counseling advice.

The scope is limited to:

- Inspecting the Excel schema.
- Defining which fields can support deterministic execution.
- Converting one natural-language input into rule classes.
- Verifying rules against the schema.
- Asking confirmation questions for ambiguous preferences.
- Executing only verified and confirmed rules.
- Producing a trace that explains why each result appears.

The research target is preference-to-rule verification, not recommendation quality alone.

## 4. Input Example

Example input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

This input is useful because it contains all three rule classes:

- Clear facts: 广东, 物理类, 排位32000.
- Executable preferences if fields exist: 计算机, 广州深圳.
- Vague preferences requiring confirmation: 稳一点, 太贵.
- Potentially missing-schema preference: 中外合作.

## 5. Expected Output for the Example

### deterministic_rules

```json
[
  {
    "source_text": "广东物理类",
    "field": "subject_type",
    "operator": "eq",
    "value": "物理"
  },
  {
    "source_text": "广东",
    "field": "source_province",
    "operator": "eq",
    "value": "广东"
  },
  {
    "source_text": "排位32000",
    "field": "user_rank",
    "operator": "set_context",
    "value": 32000
  },
  {
    "source_text": "想学计算机",
    "field": "major_name",
    "operator": "contains",
    "value": "计算机"
  },
  {
    "source_text": "最好在广州深圳",
    "field": "city",
    "operator": "in",
    "value": ["广州", "深圳"]
  }
]
```

Exact keyword match can be deterministic. Semantic expansion from "计算机" to software engineering, artificial intelligence, data science, or cybersecurity must be candidate unless a curated and approved major ontology is used.

### candidate_rules

```json
[
  {
    "source_text": "学校稳一点",
    "proposal": "Use a safety margin on historical rank, such as min_rank_2024 >= user_rank * 1.10",
    "requires_human_confirmation": true
  },
  {
    "source_text": "太贵",
    "proposal": "Ask the user for a maximum tuition threshold",
    "requires_human_confirmation": true
  },
  {
    "source_text": "计算机相关",
    "proposal": "Ask whether to include 软件工程, 人工智能, 数据科学, 网络空间安全",
    "requires_human_confirmation": true
  }
]
```

### llm_needed_parts

```json
[
  {
    "source_text": "不想去中外合作",
    "reason": "Only executable if the Excel schema has a reliable cooperation_type field or an approved derived rule. Otherwise it remains non-executable."
  }
]
```

### confirmation questions

```text
1. 你说“稳一点”。请选择安全边际：
   A. 5%: min_rank_2024 >= 32000 * 1.05
   B. 10%: min_rank_2024 >= 32000 * 1.10
   C. 15%: min_rank_2024 >= 32000 * 1.15

2. 你说“不想太贵”。请选择最高可接受学费：
   A. <= 10000 元/年
   B. <= 20000 元/年
   C. <= 40000 元/年
   D. 自定义

3. 你说“想学计算机”。是否只匹配“计算机”关键词？
   A. 只做精确关键词匹配
   B. 扩展到软件工程、人工智能、数据科学、网络空间安全
```

### executable rules after confirmation

Assume simulated confirmation:

- 稳一点 = 10% safety margin.
- 太贵 = tuition <= 20000 元/年.
- 计算机 = exact keyword only.
- 中外合作 = not executable unless a reliable field exists.

```json
[
  {"field": "source_province", "operator": "eq", "value": "广东"},
  {"field": "subject_type", "operator": "eq", "value": "物理"},
  {"field": "major_name", "operator": "contains", "value": "计算机"},
  {"field": "city", "operator": "in", "value": ["广州", "深圳"]},
  {"field": "min_rank_2024", "operator": ">=", "value_expression": "32000 * 1.10"},
  {"field": "tuition_yuan_per_year", "operator": "<=", "value": 20000}
]
```

### result trace

Each result row should include a rule trace:

```text
PASS source_province == 广东
PASS subject_type == 物理
PASS major_name contains 计算机
PASS city in 广州/深圳
PASS min_rank_2024 >= 35200
PASS tuition_yuan_per_year <= 20000
NOT EXECUTED cooperation_type exclusion: field missing or unverified
```

The trace is part of the methodology. A result without a trace is not considered verified.

## 6. Rule Categories

### A. Deterministic rules

Deterministic rules can be executed directly against structured fields after schema grounding and verification.

Examples:

- "广东物理类" -> `source_province == 广东`, `subject_type == 物理`
- "排位32000" -> `user_rank = 32000` as user context
- "广州深圳" -> `city in [广州, 深圳]`
- "想学计算机" -> `major_name contains 计算机`, if exact keyword match only
- "不要中外合作" -> deterministic only if `cooperation_type` exists and has reliable values

### B. Candidate rules

Candidate rules are plausible translations, but they require human confirmation before execution.

Examples:

- "计算机相关" -> ask whether to include 软件工程, 人工智能, 数据科学, 网络空间安全
- "稳一点" -> ask whether safety margin should be 5%, 10%, or 15%
- "太贵" -> ask for a tuition threshold
- "学校好一点" -> ask whether to use school tags, ranking, 双一流, 985/211, or no structured filter

Candidate rules are not executable until confirmed.

### C. LLM-needed parts

LLM-needed parts cannot be safely compiled into rules using the current dataset. They may require explanation, external evidence, or a warning that the dataset cannot support the claim.

Examples:

- "就业前景好"
- "学校氛围好"
- "老师负责"
- "城市发展潜力好"
- "专业未来趋势好"

These should not be silently converted into deterministic filters.

## 7. Schema Registry Design

The schema registry is the system boundary. It defines what the system is allowed to execute.

If a preference cannot be grounded in the registry, it cannot become a deterministic executable rule. The registry prevents the LLM from inventing fields or overinterpreting text.

Example schema fields:

```json
[
  {
    "field_id": "subject_type",
    "source_column": "科类",
    "type": "enum",
    "aliases": ["科类", "物理类", "历史类", "首选科目"],
    "allowed_ops": ["eq"],
    "nullable": false,
    "notes": "Expected values may include 物理 and 历史."
  },
  {
    "field_id": "user_rank",
    "source_column": null,
    "type": "integer_context",
    "aliases": ["排位", "位次", "排名"],
    "allowed_ops": ["set_context"],
    "nullable": false,
    "notes": "User-provided context, not an Excel column."
  },
  {
    "field_id": "school_name",
    "source_column": "院校名称",
    "type": "string",
    "aliases": ["学校", "院校", "大学"],
    "allowed_ops": ["eq", "contains"],
    "nullable": false,
    "notes": "Used for display, grouping, and optional school filters."
  },
  {
    "field_id": "major_name",
    "source_column": "专业名称",
    "type": "string",
    "aliases": ["专业", "想学", "专业名称"],
    "allowed_ops": ["eq", "contains", "in"],
    "nullable": false,
    "notes": "Exact keyword matching may be deterministic; semantic expansion requires confirmation."
  },
  {
    "field_id": "city",
    "source_column": "城市",
    "type": "string",
    "aliases": ["城市", "地区", "广州", "深圳"],
    "allowed_ops": ["eq", "contains", "in"],
    "nullable": true,
    "notes": "City normalization may be needed if values use districts or campus locations."
  },
  {
    "field_id": "min_score_2024",
    "source_column": "最低分1",
    "type": "number",
    "aliases": ["去年最低分", "2024最低分"],
    "allowed_ops": ["<=", ">=", "between", "sort"],
    "nullable": true,
    "notes": "May be major-level depending on dataset semantics."
  },
  {
    "field_id": "min_rank_2024",
    "source_column": "最低位次1",
    "type": "number",
    "aliases": ["去年最低位次", "2024最低排位", "最低位次"],
    "allowed_ops": ["<=", ">=", "between", "sort"],
    "nullable": true,
    "notes": "Need to distinguish major-level rank from professional-group rank."
  },
  {
    "field_id": "min_score_2025",
    "source_column": null,
    "type": "number",
    "aliases": ["2025最低分", "今年最低分"],
    "allowed_ops": ["<=", ">=", "between", "sort"],
    "nullable": true,
    "notes": "Missing if the workbook only contains estimates or 2024 records."
  },
  {
    "field_id": "min_rank_2025",
    "source_column": null,
    "type": "number",
    "aliases": ["2025最低位次", "今年最低排位"],
    "allowed_ops": ["<=", ">=", "between", "sort"],
    "nullable": true,
    "notes": "Missing unless actual 2025 admission outcomes exist."
  },
  {
    "field_id": "tuition_yuan_per_year",
    "source_column": "学费",
    "type": "number_from_string",
    "aliases": ["学费", "费用", "太贵"],
    "allowed_ops": ["<=", ">=", "between"],
    "nullable": true,
    "notes": "May need numeric extraction from text."
  },
  {
    "field_id": "cooperation_type",
    "source_column": null,
    "type": "enum",
    "aliases": ["中外合作", "国际班", "合作办学"],
    "allowed_ops": ["eq", "neq", "in", "not_in"],
    "nullable": true,
    "notes": "Missing unless a reliable dedicated column or approved derived classifier exists."
  },
  {
    "field_id": "batch",
    "source_column": "批次",
    "type": "string",
    "aliases": ["批次", "本科批", "提前批"],
    "allowed_ops": ["eq", "contains", "in"],
    "nullable": false,
    "notes": "Useful for limiting scope to undergraduate regular batch."
  },
  {
    "field_id": "plan_count",
    "source_column": "计划人数",
    "type": "number",
    "aliases": ["计划人数", "招生人数"],
    "allowed_ops": ["<=", ">=", "between", "sort"],
    "nullable": true,
    "notes": "May be used as a candidate stability signal, not automatically deterministic."
  }
]
```

## 8. Rule JSON Format

### deterministic rule

```json
{
  "rule_id": "r_subject_001",
  "source_text": "广东物理类",
  "category": "deterministic",
  "status": "verified",
  "field": "subject_type",
  "operator": "eq",
  "value": "物理",
  "confidence": 0.98,
  "requires_human_confirmation": false,
  "verification": {
    "field_exists": true,
    "type_valid": true,
    "operator_allowed": true,
    "value_normalized": true,
    "ambiguity_detected": false,
    "executable": true
  },
  "trace_reason": "The phrase explicitly states 物理类 and the schema contains subject_type."
}
```

### candidate rule

```json
{
  "rule_id": "r_safety_001",
  "source_text": "学校稳一点",
  "category": "candidate",
  "status": "pending_confirmation",
  "field": "min_rank_2024",
  "operator": ">=",
  "value_expression": "user_rank * 1.10",
  "confidence": 0.72,
  "requires_human_confirmation": true,
  "verification": {
    "field_exists": true,
    "type_valid": true,
    "operator_allowed": true,
    "ambiguity_detected": true,
    "executable": false
  },
  "trace_reason": "稳一点 is vague and must not be executed until the user confirms a safety margin."
}
```

### confirmed rule

```json
{
  "rule_id": "r_safety_001_confirmed",
  "source_text": "学校稳一点",
  "category": "confirmed_candidate",
  "status": "verified",
  "field": "min_rank_2024",
  "operator": ">=",
  "value": 35200,
  "confidence": 1.0,
  "requires_human_confirmation": false,
  "verification": {
    "field_exists": true,
    "type_valid": true,
    "operator_allowed": true,
    "value_normalized": true,
    "dry_run_passed": true,
    "executable": true
  },
  "trace_reason": "User confirmed a 10% safety margin for rank 32000."
}
```

### rejected rule

```json
{
  "rule_id": "r_coop_001",
  "source_text": "不想去中外合作",
  "category": "candidate",
  "status": "rejected_not_executable",
  "field": "cooperation_type",
  "operator": "neq",
  "value": "中外合作",
  "confidence": 0.6,
  "requires_human_confirmation": false,
  "verification": {
    "field_exists": false,
    "executable": false
  },
  "trace_reason": "The schema does not contain a reliable cooperation_type field."
}
```

### llm-needed part

```json
{
  "rule_id": "l_employment_001",
  "source_text": "就业前景好",
  "category": "llm_needed",
  "status": "not_rule",
  "field": null,
  "operator": null,
  "value": null,
  "confidence": 0.9,
  "requires_human_confirmation": false,
  "verification": {
    "schema_grounded": false,
    "executable": false
  },
  "trace_reason": "Employment prospects are not directly represented by the Excel schema."
}
```

## 9. Rule Verification Protocol

Each executable rule must pass:

1. Field existence check: the field must exist in the schema registry.
2. Type check: the rule value must match the field type.
3. Operator check: the operator must be allowed for that field.
4. Value normalization check: aliases, city names, subject labels, and numeric strings must be normalized.
5. Ambiguity check: vague words such as 稳一点, 太贵, 好一点, 相关 must trigger candidate status.
6. Data coverage check: fields with high null rates should produce warnings or block execution.
7. Conflict check: rules should not contradict each other.
8. Dry-run check: execute on sample data to detect empty results, type failures, or impossible filters.
9. Traceability check: every rule must preserve source text and explanation.

Principles:

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
```

## 10. Human Confirmation Design

Human confirmation should convert vague preferences into explicit operational choices.

Examples:

```text
“稳一点” -> choose safety margin:
- 5%: min_rank_2024 >= user_rank * 1.05
- 10%: min_rank_2024 >= user_rank * 1.10
- 15%: min_rank_2024 >= user_rank * 1.15
```

```text
“太贵” -> choose tuition threshold:
- <= 10000 元/年
- <= 20000 元/年
- <= 40000 元/年
- custom
```

```text
“计算机相关” -> choose semantic expansion:
- exact keyword only: 计算机
- include 软件工程
- include 人工智能
- include 数据科学
- include 网络空间安全
```

The UI should show what will become executable and what will remain non-executable. A confirmation decision should be saved as part of the rule trace.

## 11. Flowchart

```text
User input
  |
  v
Preference decomposition
  |
  v
Extract slots and phrases
  |
  v
Schema registry lookup
  |
  v
Rule classification
  |----------------------|----------------------|
  v                      v                      v
Deterministic        Candidate              LLM-needed
rules                rules                  parts
  |                      |                      |
  v                      v                      v
Rule verification    Confirmation Qs        Semantic note
  |                      |
  v                      v
Executable?          User confirms?
  |                      |
  v                      v
Execute rules <------ Confirmed candidate rule
  |
  v
Filtered / ranked rows
  |
  v
Result trace
  |
  v
Research report / demo output
```

## 12. MVP Scope

The MVP should only support:

- One Excel dataset.
- One single-turn user input.
- Schema loading.
- Preference decomposition.
- Rule classification.
- Rule verification.
- Confirmation question generation.
- Simulated confirmation.
- Query execution.
- Result trace.

Explicitly excluded:

- Full志愿表 generation.
- School reputation judgment.
- Employment prediction.
- External web search.
- Multi-turn advisor bot.
- Universal symbolic AI.

The MVP is a verification demo, not a complete advising product.

## 13. Engineering Modules

```text
schema_loader
  Reads Excel sheet names, columns, sample rows, data types, null rates, and builds schema registry candidates.

slot_extractor
  Decomposes user input into raw facts, preferences, vague phrases, and semantic parts.

rule_classifier
  Assigns each extracted preference to deterministic, candidate, or LLM-needed.

candidate_rule_generator
  Proposes possible operational translations for vague preferences without executing them.

rule_verifier
  Applies field, type, operator, value, ambiguity, coverage, conflict, dry-run, and traceability checks.

human_confirmation
  Converts candidate rules into confirmed, edited, or rejected rules.

query_engine
  Executes only verified deterministic and confirmed rules against the dataset.

trace_generator
  Produces row-level and rule-level explanations.

report_builder
  Creates the final demo report with rules, verification results, confirmations, results, and traces.

evaluation
  Measures extraction quality, rule safety, schema violations, and trace completeness.
```

## 14. Test Cases

Tests should focus on preventing vague preference over-promotion.

### Positive deterministic cases

| Input phrase | Expected classification |
|---|---|
| 广东物理类 | deterministic |
| 排位32000 | deterministic context |
| 广州深圳 | deterministic if city field exists |
| 专业名称包含计算机 | deterministic |
| 不要中外合作 | deterministic only if cooperation_type exists |

### Candidate cases

| Input phrase | Expected classification |
|---|---|
| 稳一点 | candidate |
| 太贵 | candidate |
| 计算机相关 | candidate |
| 学校好一点 | candidate or LLM-needed |
| 不想风险太大 | candidate |

### Negative / safety cases

| Input phrase | Failure to prevent |
|---|---|
| 稳一点 | Must not auto-compile to 10% without confirmation |
| 太贵 | Must not invent a tuition threshold |
| 就业前景好 | Must not execute without supported field |
| 中外合作 | Must not filter if cooperation_type is missing |
| 学校好一点 | Must not silently use ranking unless confirmed |

## 15. Evaluation Metrics

Core metrics:

- Slot extraction precision and recall.
- Field mapping accuracy.
- Deterministic over-promotion rate.
- Candidate recall.
- Schema violation rate.
- Invalid rule rejection rate.
- Trace completeness.
- Execution success rate.

Most important metric:

```text
deterministic over-promotion rate
= vague or unsupported preferences incorrectly classified as deterministic
  / all vague or unsupported preferences
```

This metric should be close to zero. It is more important than maximizing the number of executable rules.

## 16. Two-Week Implementation Roadmap

### Week 1

- Inspect Excel sheets and columns.
- Build the first schema registry from real columns.
- Mark missing-but-desired fields.
- Define rule taxonomy.
- Define rule JSON schema.
- Implement verifier design.
- Create test cases focused on over-promotion prevention.

### Week 2

- Implement query engine.
- Implement confirmation flow.
- Generate rule and row traces.
- Run the single demo case.
- Evaluate rule classification and verification behavior.
- Write methodology report.

The implementation should stay narrow. The goal is to produce a credible research-engineering demo, not a full product.

## 17. Research Contribution

This project contributes a practical methodology for safely converting natural-language preferences into verifiable rules over structured data.

The Guangdong college application case is the first domain because it has high-stakes decisions, structured Excel data, and many ambiguous user preferences. The same methodology can generalize to other structured decision systems:

- Course selection: preferences about difficulty, schedule, instructor, and requirements.
- Rental recommendation: budget, commute, neighborhood, safety, and vague lifestyle preferences.
- Job filtering: location, salary, title, industry, growth, and culture.
- Product recommendation: price, features, brand preference, reliability, and subjective quality.
- Investment screening: sector, valuation, risk, liquidity, and qualitative concerns.

The general contribution is not a universal recommender. It is a verification-centered workflow:

```text
Only execute what is schema-grounded, type-safe, operator-valid, ambiguity-checked, and traceable.
Everything else must be confirmed, rejected, or left as semantic context.
```
