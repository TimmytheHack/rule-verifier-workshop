# Methodology Report: Current MVP

## 1. What The MVP Proves

The current MVP proves that a natural-language college application preference can be converted into a small, auditable rule pipeline without pretending that every preference is executable.

For one fixed input, the system demonstrates:

- Excel schema inspection and real header-row detection.
- Schema registry construction from actual fields only.
- Separation of deterministic rules, candidate rules, and LLM-needed parts.
- Verification before execution.
- Confirmation-gated promotion of vague preferences.
- Query execution using only verified and confirmed rules.
- Row-level traces explaining why each result was returned.

The key proof is conservative behavior: the system can say "this preference is not executable" when the dataset does not support it.

## 2. Why This Is Not A Normal Recommendation Bot

A normal recommendation bot tries to produce useful recommendations directly. This MVP studies a narrower and more safety-critical question:

```text
Which parts of a natural-language preference can be safely compiled into executable rules?
```

The system does not rank schools by overall fit, predict admission probability, evaluate reputation, infer employment quality, or generate a complete志愿表.

Instead, it treats recommendation as downstream of rule verification. The output is not just a list of rows; it is a list of rows plus the rules that produced them and the preferences that were not executed.

This distinction matters because high-stakes planning can be harmed by false precision. A rule that looks objective but was derived from a vague phrase can mislead users more than an explicit uncertainty warning.

## 3. The Three Rule Classes

### Deterministic Rules

Deterministic rules are explicit, schema-grounded, and directly executable.

Examples from the MVP:

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
```

These rules are allowed because the required fields exist in the Excel schema and the user phrases are explicit enough.

### Candidate Rules

Candidate rules are plausible interpretations of vague preferences. They must not execute until confirmed.

Examples from the MVP:

```text
稳一点 -> possible safety margin
太贵 -> possible tuition threshold
计算机相关扩展 -> possible semantic expansion
```

The MVP simulates confirmation for two of them:

```text
稳一点 -> 10% safety margin
太贵 -> 学费 <= 20000
```

It rejects major expansion for the first demo:

```text
计算机相关扩展 -> false
```

### LLM-Needed Or Non-Executable Parts

LLM-needed parts are preferences that cannot be grounded in the current schema.

In the MVP:

```text
不想去太贵的中外合作
```

The tuition part becomes a candidate rule because `学费` exists. The 中外合作 part remains non-executable because no reliable `cooperation_type` field exists.

## 4. First Demo Input

The first demo input is:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

Hardcoded extracted slots:

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

The hardcoding is intentional for this stage. The MVP tests the verifier and trace behavior before expanding into general extraction.

## 5. Final Executable Rules

After simulated confirmation, the final executable rules are:

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

The threshold `35200` comes from:

```text
user_rank * 1.10 = 32000 * 1.10 = 35200
```

The query uses AND logic. A row must satisfy all six executable rules to appear in `filtered_results.csv`.

In the current workbook run, this produced 93 filtered rows.

## 6. Why 中外合作 Was Not Executed

The Excel schema has no dedicated `cooperation_type` field.

The system could try to infer 中外合作 from text fields such as:

- `专业全称`
- `专业备注`
- `专业组名称`
- `组内专业`

The MVP deliberately does not do this. Text-pattern inference could confuse international classes, exchange programs, joint training, high tuition, and formal 中外合作办学. That would create an unverified derived field and violate the schema boundary.

The rule is therefore blocked:

```text
No schema grounding, no deterministic execution.
```

The result trace explicitly states:

```text
Missing dedicated cooperation_type field; no text inference applied.
```

## 7. Why This Matters For Rule Verification

The most important risk in preference-to-rule systems is not that the system returns too few results. The greater risk is that it returns results after silently applying rules the user never confirmed or the data cannot support.

This MVP shows three safety behaviors:

1. Vague preferences are not automatically promoted.
2. Missing fields block execution.
3. Every returned row carries a trace.

These behaviors make the system auditable. A user or researcher can inspect what was executed, what was confirmed, and what remained non-executable.

This is the central research contribution of the MVP: recommendation outputs should be downstream of verifiable rule construction.

## 8. Current Limitations

The current MVP is intentionally narrow.

Limitations:

- It supports only one input.
- Slot extraction is hardcoded.
- User confirmation is simulated.
- It does not implement a UI.
- It does not use an LLM.
- It does not perform external web search.
- It does not generate a full志愿表.
- It does not estimate admission probability.
- It does not evaluate school reputation.
- It does not predict employment outcomes.
- It does not infer `cooperation_type` from text.
- It does not expand `计算机` to related majors.
- It uses `专业组最低位次1` as the safety field, which is a pragmatic MVP choice and should be evaluated against domain expectations.

These limits are acceptable because the current objective is to validate rule verification mechanics, not build a complete advising product.

## 9. Next Evaluation Plan With 10 Test Inputs

The next evaluation should test whether the system avoids deterministic over-promotion.

Proposed test inputs:

| ID | Input | Main expected behavior |
|---|---|---|
| T01 | 我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。 | Same as current demo. 中外合作 not executable. |
| T02 | 广东物理，排位50000，只看广州，计算机。 | Deterministic rules only, no vague risk rule. |
| T03 | 广东历史类，排位20000，想读法学，学校好一点。 | 学校好一点 must be candidate or LLM-needed, not automatic ranking filter. |
| T04 | 物理类，排位45000，计算机相关都可以。 | 计算机相关 must require confirmation for expansion. |
| T05 | 广东物理，排位60000，不想太贵。 | Tuition threshold must be requested; no invented cap. |
| T06 | 广东物理，排位35000，想冲一冲计算机。 | 冲一冲 must be candidate with explicit risk interpretation. |
| T07 | 广东物理，排位32000，不要中外合作。 | Must be non-executable unless `cooperation_type` is available. |
| T08 | 广东物理，排位40000，想要就业前景好。 | 就业前景好 must be LLM-needed or external-evidence-needed. |
| T09 | 广东物理，排位30000，深圳，软件工程。 | 软件工程 exact keyword can be deterministic if no semantic expansion is needed. |
| T10 | 广东物理，排位32000，想去一线城市，费用别太高。 | 一线城市 depends on schema field; 费用别太高 requires confirmation. |

Evaluation metrics:

- Slot extraction precision and recall.
- Field mapping accuracy.
- Candidate recall.
- Schema violation rate.
- Invalid rule rejection rate.
- Trace completeness.
- Execution success rate.
- Deterministic over-promotion rate.

The most important metric is:

```text
deterministic over-promotion rate
```

The target should be near zero, even if that means fewer rules execute automatically.

## 10. Generalization To Other Structured Decision Systems

The same methodology can generalize beyond college applications wherever users express preferences over structured data.

Examples:

- Course selection: schedule, prerequisites, difficulty, instructor, graduation requirements.
- Rental recommendation: budget, commute, district, room type, vague safety preferences.
- Job filtering: location, salary, role title, industry, culture, growth potential.
- Product recommendation: price, brand, specifications, subjective quality, reliability.
- Investment screening: sector, market cap, valuation, liquidity, risk tolerance.

The transferable pattern is:

```text
natural-language preference
-> rule class assignment
-> schema grounding
-> verification
-> confirmation
-> execution
-> trace
```

The domain-specific part is the schema registry and candidate-rule policy. The safety principle remains the same:

```text
Only execute what is grounded, verified, confirmed when needed, and traceable.
```
