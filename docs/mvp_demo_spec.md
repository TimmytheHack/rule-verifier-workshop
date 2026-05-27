# MVP Demo Spec: First End-to-End Preference-to-Rule Verification Demo

## Demo Goal

This demo shows one complete preference-to-rule verification flow for a single user input.

It is not a full college recommendation system. The purpose is to demonstrate how a natural-language preference is decomposed, classified, verified against the Excel schema, confirmed by a human when needed, executed only when safe, and explained through result traces.

## Demo Input

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

Known dataset constraints from the Excel inspection:

- Workbook has one sheet: `Sheet1`.
- Real header row is row 3.
- `科类` exists and contains values such as `物理` and `历史`.
- `生源地` exists.
- `专业名称` exists.
- `城市` exists and contains values such as `广州` and `深圳`.
- `学费` exists but is stored as text-like values.
- `专业组最低位次1` exists and can be used as a 2024 professional-group minimum rank proxy.
- `最低位次1` exists but has more missing values in the relevant subset.
- There is no dedicated `cooperation_type` column.
- There is no actual `min_rank_2025` field; `25年预估位次` is an estimate, not final admission data.

## 1. Expected Extracted Slots

```json
{
  "user_context": {
    "source_province": "广东",
    "subject_type": "物理",
    "user_rank": 32000
  },
  "preferences": {
    "major_keyword": "计算机",
    "preferred_cities": ["广州", "深圳"],
    "risk_preference_raw": "稳一点",
    "tuition_preference_raw": "太贵",
    "cooperation_preference_raw": "不想去中外合作"
  },
  "raw_phrases": [
    "广东物理类",
    "排位32000",
    "想学计算机",
    "最好在广州深圳",
    "学校稳一点",
    "不想去太贵的中外合作"
  ]
}
```

Extraction notes:

- `广东` should map to user source province, not school province.
- `物理类` should normalize to `物理`.
- `排位32000` is user context, not a dataset column.
- `计算机` is an exact keyword for the MVP.
- `广州深圳` should normalize to two city values: `广州`, `深圳`.
- `稳一点` and `太贵` are vague and must not become deterministic rules.
- `中外合作` cannot be executed unless a reliable schema field or approved classifier exists.

## 2. Deterministic Rules

Deterministic rules are only allowed when they are explicit, schema-grounded, and non-vague.

```json
[
  {
    "rule_id": "d_source_province",
    "source_text": "广东",
    "category": "deterministic",
    "status": "verified",
    "field": "生源地",
    "operator": "eq",
    "value": "广东",
    "requires_human_confirmation": false,
    "trace_reason": "The user explicitly states Guangdong source province and the Excel field 生源地 exists."
  },
  {
    "rule_id": "d_subject_type",
    "source_text": "物理类",
    "category": "deterministic",
    "status": "verified",
    "field": "科类",
    "operator": "eq",
    "value": "物理",
    "requires_human_confirmation": false,
    "trace_reason": "The user explicitly states 物理类 and the Excel field 科类 exists."
  },
  {
    "rule_id": "d_major_keyword",
    "source_text": "想学计算机",
    "category": "deterministic",
    "status": "verified",
    "field": "专业名称",
    "operator": "contains",
    "value": "计算机",
    "requires_human_confirmation": false,
    "trace_reason": "Exact keyword matching is allowed in the MVP."
  },
  {
    "rule_id": "d_city",
    "source_text": "最好在广州深圳",
    "category": "deterministic",
    "status": "verified",
    "field": "城市",
    "operator": "in_contains",
    "value": ["广州", "深圳"],
    "requires_human_confirmation": false,
    "trace_reason": "The Excel field 城市 exists and contains relevant values."
  }
]
```

User rank is deterministic context:

```json
{
  "rule_id": "ctx_user_rank",
  "source_text": "排位32000",
  "category": "context",
  "status": "verified",
  "field": "user_rank",
  "operator": "set_context",
  "value": 32000,
  "requires_human_confirmation": false,
  "trace_reason": "User rank is used to compute candidate risk rules after confirmation."
}
```

## 3. Candidate Rules

Candidate rules are plausible translations that require confirmation before execution.

```json
[
  {
    "rule_id": "c_safety_margin",
    "source_text": "学校稳一点",
    "category": "candidate",
    "status": "pending_confirmation",
    "field": "专业组最低位次1",
    "operator": ">=",
    "value_expression_options": [
      "32000 * 1.05",
      "32000 * 1.10",
      "32000 * 1.15"
    ],
    "requires_human_confirmation": true,
    "trace_reason": "稳一点 is vague. The system may propose safety margins but cannot execute one silently."
  },
  {
    "rule_id": "c_tuition_cap",
    "source_text": "太贵",
    "category": "candidate",
    "status": "pending_confirmation",
    "field": "学费",
    "operator": "<=",
    "value_options": [10000, 20000, 40000],
    "requires_human_confirmation": true,
    "trace_reason": "太贵 is vague. The user must choose a tuition threshold."
  },
  {
    "rule_id": "c_major_expansion",
    "source_text": "想学计算机",
    "category": "candidate",
    "status": "pending_confirmation",
    "field": "专业名称",
    "operator": "contains_any",
    "value_options": ["软件工程", "人工智能", "数据科学", "网络空间安全"],
    "requires_human_confirmation": true,
    "trace_reason": "Semantic expansion beyond the exact keyword 计算机 requires confirmation."
  }
]
```

## 4. LLM-Needed Parts

```json
[
  {
    "part_id": "l_cooperation_type",
    "source_text": "不想去中外合作",
    "category": "llm_needed",
    "status": "not_executable_in_mvp",
    "field": "cooperation_type",
    "reason": "The inspected Excel schema does not contain a dedicated cooperation_type column.",
    "allowed_behavior": "Report as non-executable. Do not silently filter by text patterns such as 国际班 or 中外合作."
  }
]
```

Important rule:

```text
No dedicated field, no deterministic execution.
```

The MVP must not pretend that 中外合作 was filtered out.

## 5. Confirmation Questions

The demo should generate exactly these confirmation questions.

### Q1: Safety margin

```text
你说“学校稳一点”。请选择安全边际：

A. 轻微稳妥：专业组最低位次1 >= 32000 * 1.05 = 33600
B. 适中稳妥：专业组最低位次1 >= 32000 * 1.10 = 35200
C. 保守稳妥：专业组最低位次1 >= 32000 * 1.15 = 36800
D. 不使用这个规则
```

### Q2: Tuition threshold

```text
你说“不想太贵”。请选择最高可接受学费：

A. <= 10000 元/年
B. <= 20000 元/年
C. <= 40000 元/年
D. 不使用学费规则
```

### Q3: Major expansion

```text
你说“想学计算机”。是否扩展到相关专业？

A. 不扩展，只匹配“计算机”
B. 扩展到 软件工程、人工智能、数据科学、网络空间安全
C. 自定义相关专业词表
```

### Non-question warning

```text
“中外合作”偏好无法在当前 Excel schema 中可靠执行，因为缺少 cooperation_type 字段。
本次 demo 将保留该偏好为 LLM-needed / non-executable，并在结果 trace 中明确说明未执行。
```

## 6. Simulated User Confirmations

For the first demo, use fixed simulated confirmations:

```json
{
  "safety_margin": {
    "selected_option": "B",
    "label": "适中稳妥",
    "field": "专业组最低位次1",
    "operator": ">=",
    "value": 35200
  },
  "tuition_threshold": {
    "selected_option": "B",
    "label": "<= 20000 元/年",
    "field": "学费",
    "operator": "<=",
    "value": 20000
  },
  "major_expansion": {
    "selected_option": "A",
    "label": "不扩展，只匹配“计算机”",
    "expanded_terms": []
  },
  "cooperation_type": {
    "selected_option": null,
    "status": "not_executable",
    "reason": "Missing dedicated cooperation_type field."
  }
}
```

## 7. Final Executable Rules

Only verified deterministic rules and confirmed candidate rules become executable.

```json
[
  {
    "rule_id": "e_source_province",
    "field": "生源地",
    "operator": "eq",
    "value": "广东"
  },
  {
    "rule_id": "e_subject_type",
    "field": "科类",
    "operator": "eq",
    "value": "物理"
  },
  {
    "rule_id": "e_major_keyword",
    "field": "专业名称",
    "operator": "contains",
    "value": "计算机"
  },
  {
    "rule_id": "e_city",
    "field": "城市",
    "operator": "in_contains",
    "value": ["广州", "深圳"]
  },
  {
    "rule_id": "e_safety_margin",
    "field": "专业组最低位次1",
    "operator": ">=",
    "value": 35200
  },
  {
    "rule_id": "e_tuition_cap",
    "field": "学费",
    "operator": "<=",
    "value": 20000,
    "normalization": "parse numeric value from cell text"
  }
]
```

Non-executable preserved preference:

```json
{
  "source_text": "不想去中外合作",
  "status": "not_executed",
  "reason": "Missing dedicated cooperation_type field."
}
```

## 8. Expected Query Behavior

The query engine should:

1. Read `Sheet1` using row 3 as the header.
2. Iterate rows starting from row 4.
3. Apply all final executable rules with AND logic.
4. Treat `学费` as numeric after parsing.
5. Treat `城市` using contains matching against `广州` and `深圳`.
6. Treat `专业名称 contains 计算机` as exact substring matching.
7. Use `专业组最低位次1 >= 35200` as the confirmed safety rule.
8. Do not apply any 中外合作 exclusion rule.
9. Return filtered rows.
10. Rank rows by closest safe rank first:

```text
ranking_key = 专业组最低位次1 - 35200
sort ascending by ranking_key
```

Tie-breakers may use:

```text
院校排名 ascending when numeric
ID ascending
```

Expected high-level output:

```json
{
  "query_status": "success",
  "filters_applied": 6,
  "filters_not_executed": 1,
  "not_executed_reasons": [
    "cooperation_type missing from schema"
  ],
  "result_count": "data-dependent",
  "ranking": "closest safe group rank first"
}
```

For the inspected workbook, the same rule set produced 93 filtered rows during planning inspection. This number should be treated as an expected demo reference, not a hard-coded value.

## 9. Result Trace Format

Each returned row must include a compact trace.

### Row-level result format

```json
{
  "row_id": 8947,
  "school_name": "深圳大学",
  "major_group_code": "10590251",
  "major_group_name": "251组(地方专项)",
  "major_name": "计算机类",
  "city": "深圳",
  "tuition": 6853,
  "group_min_rank_2024": 38998,
  "ranking_key": 3798,
  "trace": [
    {
      "rule_id": "e_source_province",
      "status": "pass",
      "reason": "生源地 == 广东"
    },
    {
      "rule_id": "e_subject_type",
      "status": "pass",
      "reason": "科类 == 物理"
    },
    {
      "rule_id": "e_major_keyword",
      "status": "pass",
      "reason": "专业名称 contains 计算机"
    },
    {
      "rule_id": "e_city",
      "status": "pass",
      "reason": "城市 matches 深圳"
    },
    {
      "rule_id": "e_safety_margin",
      "status": "pass",
      "reason": "专业组最低位次1 38998 >= 35200"
    },
    {
      "rule_id": "e_tuition_cap",
      "status": "pass",
      "reason": "学费 6853 <= 20000"
    },
    {
      "rule_id": "l_cooperation_type",
      "status": "not_executed",
      "reason": "Missing dedicated cooperation_type field"
    }
  ]
}
```

### Trace requirements

Every returned row must show:

- Which executable rules passed.
- Which user preference was not executed.
- Why the non-executed preference was not executed.
- The rank threshold used for the safety rule.
- The parsed tuition value used for the tuition rule.

## 10. Unit Tests for This Demo

### Slot extraction tests

| Test ID | Input | Expected |
|---|---|---|
| `test_extract_source_province` | 广东物理类 | `source_province = 广东` |
| `test_extract_subject_type` | 广东物理类 | `subject_type = 物理` |
| `test_extract_user_rank` | 排位32000 | `user_rank = 32000` |
| `test_extract_major_keyword` | 想学计算机 | `major_keyword = 计算机` |
| `test_extract_cities` | 广州深圳 | `preferred_cities = [广州, 深圳]` |
| `test_extract_vague_safety` | 稳一点 | `risk_preference_raw = 稳一点` |
| `test_extract_vague_tuition` | 太贵 | `tuition_preference_raw = 太贵` |
| `test_extract_cooperation` | 中外合作 | `cooperation_preference_raw = 中外合作` |

### Rule classification tests

| Test ID | Preference | Expected category |
|---|---|---|
| `test_classify_subject` | 物理类 | deterministic |
| `test_classify_city` | 广州深圳 | deterministic if `城市` exists |
| `test_classify_exact_major` | 计算机 | deterministic exact keyword |
| `test_classify_major_expansion` | 计算机相关 | candidate |
| `test_classify_safety` | 稳一点 | candidate |
| `test_classify_tuition` | 太贵 | candidate |
| `test_classify_cooperation_missing_field` | 中外合作 | llm_needed / not executable |

### Verification tests

| Test ID | Rule | Expected |
|---|---|---|
| `test_verify_field_exists_subject` | `科类 == 物理` | pass |
| `test_verify_field_exists_city` | `城市 in [广州, 深圳]` | pass |
| `test_verify_tuition_numeric_parse` | `学费 <= 20000` | pass if numeric parse succeeds |
| `test_verify_rank_numeric` | `专业组最低位次1 >= 35200` | pass |
| `test_reject_missing_cooperation_type` | `cooperation_type != 中外合作` | fail |
| `test_block_unconfirmed_safety` | `稳一点 -> >= 35200` without confirmation | fail |
| `test_block_unconfirmed_tuition` | `太贵 -> <= 20000` without confirmation | fail |

### Query behavior tests

| Test ID | Assertion |
|---|---|
| `test_query_uses_and_logic` | A row must satisfy all executable rules. |
| `test_query_does_not_filter_cooperation` | No cooperation exclusion is applied in the MVP. |
| `test_query_city_contains` | Rows with `城市 = 广州` or `城市 = 深圳` pass city rule. |
| `test_query_major_exact_keyword_only` | `软件工程` alone does not pass unless major expansion is confirmed. |
| `test_query_safety_threshold` | Returned rows have `专业组最低位次1 >= 35200`. |
| `test_query_tuition_threshold` | Returned rows have parsed `学费 <= 20000`. |
| `test_query_ranking` | Rows are sorted by `专业组最低位次1 - 35200` ascending. |

### Trace tests

| Test ID | Assertion |
|---|---|
| `test_trace_contains_all_executed_rules` | Every returned row has trace entries for all 6 executable rules. |
| `test_trace_contains_non_executed_cooperation` | Every returned row notes 中外合作 was not executed. |
| `test_trace_includes_safety_value` | Trace includes actual rank and threshold 35200. |
| `test_trace_includes_tuition_value` | Trace includes parsed tuition and threshold 20000. |
| `test_trace_is_row_specific` | Trace values match the row values, not generic template text. |

### Safety regression tests

| Test ID | Forbidden behavior |
|---|---|
| `test_no_silent_safety_promotion` | Do not execute 稳一点 before confirmation. |
| `test_no_silent_tuition_threshold` | Do not invent a tuition cap before confirmation. |
| `test_no_semantic_major_expansion_by_default` | Do not include 软件工程/人工智能 unless confirmed. |
| `test_no_fake_cooperation_filter` | Do not filter 中外合作 without a grounded field. |
| `test_no_schema_hallucination` | Do not create fields absent from schema during execution. |

## Demo Acceptance Criteria

The demo is successful if:

1. The input is decomposed into slots.
2. Deterministic, candidate, and LLM-needed parts are separated.
3. Candidate rules are not executed before confirmation.
4. Missing fields block execution.
5. Simulated confirmations produce final executable rules.
6. Query behavior uses only executable rules.
7. Every result row includes a trace.
8. The output explicitly states that 中外合作 was not filtered in the MVP.
