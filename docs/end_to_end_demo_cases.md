# End-to-End Demo Case Matrix

This document records the 10 end-to-end demo inputs added to `eval_inputs.jsonl`.

The matrix is intentionally conservative. A preference is executable only if it can be grounded in the current schema. Vague preferences are candidate rules. Missing-schema preferences are preserved but not executed.

Current executable schema fields:

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
major_popularity
city_tier
distance/remoteness
```

The generated Excel profile shows that some concepts have candidate columns, for example `公私性质`, `院校水平`, `城市水平标签`, and `院校排名`. They still require schema review before becoming executable rules.

## Case Matrix

| ID | Input summary | Deterministic candidates | Confirmation-needed | Not executable in current schema |
|---|---|---|---|---|
| E2E01 | 广东物理 32000，计算机，广州深圳，稳一点，排除中外合作 | 生源地、科类、专业名称 contains 计算机、城市 contains 广州/深圳 | 稳一点、太贵 | 中外合作 |
| E2E02 | 广东历史 12000，法学，广州，学费不要太贵，学校好一点 | 生源地、科类、专业名称 contains 法学、城市 contains 广州 | 学费不要太贵、学校尽量好一点 | 学校质量无 verified schema |
| E2E03 | 广东物理 50000，电子信息或计算机相关，珠三角，稳妥 | 生源地、科类、exact major keyword if selected | 电子信息/计算机相关扩展、珠三角城市集合、稳妥一点 | 珠三角不是当前 city value rule unless confirmed to city set |
| E2E04 | 广东物理 28000，冲好学校，不去偏远城市 | 生源地、科类、排位 context | 冲一冲 | 好学校、太偏远城市缺 verified schema |
| E2E05 | 广东历史 30000，公办本科，专业不冷门，费用低 | 生源地、科类、排位 context | 费用低一点 | 公办本科、专业冷门度 |
| E2E06 | 广东物理 70000，保底，计算机/电子/自动化相关 | 生源地、科类、exact major keyword if selected | 保底、相关专业扩展 | major family requires confirmed expansion |
| E2E07 | 广东物理 40000，深圳广州佛山，学费两万以内，优先公办 | 生源地、科类、城市 contains 深圳/广州/佛山 | 学费两万以内 | 公办 |
| E2E08 | 广东历史 18000，新闻传播或法学，学校名气重要 | 生源地、科类、exact major keyword if selected | 新闻传播/法学 choice or expansion | 学校名气 |
| E2E09 | 广东物理 35000，人工智能/软件工程/网络安全，稳一点 | 生源地、科类、exact major keyword if selected | 多专业选择/扩展、稳一点 | none beyond current candidate handling |
| E2E10 | 广东物理 60000，不冒险，学费低，城市不要太差 | 生源地、科类、排位 context | 不想太冒险、学费低、城市集合确认 | 城市质量 tier missing unless confirmed to explicit cities |

## Evaluation Role

These cases are not yet full recommendation-quality tests. They are methodology tests for:

- deterministic rule extraction;
- candidate rule holding;
- non-executable preference preservation;
- schema hallucination prevention;
- deterministic over-promotion prevention.

These 10 cases are included in the current 40-case evaluation set. The latest API-backed evaluation shows:

- `rule_regex_extractor_symbolic_verifier`: `320/320`, over-promotion `0.000`;
- `deepseek_extractor_symbolic_verifier`: `320/320`, over-promotion `0.000`;
- `llm_only_baseline`: `107/200`, over-promotion `0.450`;
- `schema_aware_llm_only_baseline`: `157/200`, over-promotion `0.300`.

The result supports the intended boundary: LLM extraction can improve coverage, but symbolic verification must control executability.
