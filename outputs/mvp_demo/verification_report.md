# MVP Demo Verification Report

## Input

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

## Workbook

- Sheet: `Sheet1`
- Detected header row: `3`
- Required demo columns found: `生源地, 科类, 专业名称, 城市, 专业组最低位次1, 学费`

## Schema Boundary

The schema registry was built only from real Excel fields needed for this demo.

Missing field:

- `cooperation_type`: not present. The 中外合作 preference is not executable in this MVP.

## Data Coverage

| Column | Non-null | Total rows | Coverage |
|---|---:|---:|---:|
| `生源地` | 30855 | 30855 | 100.00% |
| `科类` | 30855 | 30855 | 100.00% |
| `专业名称` | 30855 | 30855 | 100.00% |
| `城市` | 30848 | 30855 | 99.98% |
| `专业组最低位次1` | 30490 | 30855 | 98.82% |
| `学费` | 30855 | 30855 | 100.00% |

## Deterministic Rule Verification

| Rule | Field | Operator | Value | Executable | Reason |
|---|---|---|---|---:|---|
| `d_source_province` | `生源地` | `eq` | `广东` | True | The user explicitly states 广东 and the Excel field 生源地 exists. |
| `d_subject_type` | `科类` | `eq` | `物理` | True | The user explicitly states 物理类 and the Excel field 科类 exists. |
| `d_major_keyword` | `专业名称` | `contains` | `计算机` | True | Exact keyword matching is allowed in the MVP. |
| `d_city` | `城市` | `in_contains` | `['广州', '深圳']` | True | The Excel field 城市 exists and contains relevant values. |

## Candidate Rules

| Rule | Source text | Status | Requires confirmation | Reason |
|---|---|---|---:|---|
| `c_safety_margin` | 学校稳一点 | pending_confirmation | True | 稳一点 is vague and must not execute without a confirmed safety margin. |
| `c_tuition_cap` | 太贵 | pending_confirmation | True | 太贵 is vague and requires a user-selected tuition cap. |
| `c_major_expansion` | 计算机相关扩展 | pending_confirmation | True | Semantic expansion beyond exact 计算机 matching requires confirmation. |

## Simulated Confirmations

- Safety margin: 10%, so `专业组最低位次1 >= 35200`.
- Tuition cap: `学费 <= 20000`.
- Major expansion: false; only exact keyword `计算机` is used.
- Cooperation type exclusion: not executed because `cooperation_type` is missing.

## Final Query Behavior

The query applies six executable rules with AND logic:

1. `生源地 == 广东`
2. `科类 == 物理`
3. `专业名称 contains 计算机`
4. `城市 contains 广州 or 深圳`
5. `专业组最低位次1 >= 35200`
6. `学费 <= 20000`

The query does not infer or filter 中外合作 from text fields.

## Result Summary

- Filtered row count: `93`
- Ranking: closest safe professional-group rank first, using `专业组最低位次1 - 35200`.

## Safety Checks

- No LLM is used in code.
- No semantic major expansion is applied.
- No `cooperation_type` field is invented.
- Candidate rules are promoted only through simulated confirmation.
