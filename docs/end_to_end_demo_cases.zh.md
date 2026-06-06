# 端到端 Demo Case Matrix

本文档记录新增到 `eval_inputs.jsonl` 的 10 条端到端 demo 输入。

这里的标注保持保守：只有能落到当前 schema 的偏好才可以执行；模糊偏好必须作为 candidate；缺少 schema 支持的偏好只能保留，不能执行。

当前可执行 schema 字段：

```text
生源地
科类
专业名称
城市
专业组最低位次1
学费
```

当前还没有进入 MVP active schema registry 的字段：

```text
cooperation_type
school_ownership
school_reputation
major_popularity
city_tier
distance/remoteness
```

自动生成的 Excel profile 显示，部分概念有候选列，例如 `公私性质`、`院校水平`、`城市水平标签`、`院校排名`。但它们仍需要 schema review，不能直接变成可执行规则。

## Case Matrix

| ID | 输入概括 | 可作为 deterministic 的部分 | 需要确认的部分 | 当前 schema 不能执行的部分 |
|---|---|---|---|---|
| E2E01 | 广东物理 32000，计算机，广州深圳，稳一点，排除中外合作 | 生源地、科类、专业名称 contains 计算机、城市 contains 广州/深圳 | 稳一点、太贵 | 中外合作 |
| E2E02 | 广东历史 12000，法学，广州，学费不要太贵，学校好一点 | 生源地、科类、专业名称 contains 法学、城市 contains 广州 | 学费不要太贵、学校尽量好一点 | 学校质量没有 verified schema |
| E2E03 | 广东物理 50000，电子信息或计算机相关，珠三角，稳妥 | 生源地、科类、确认后的 exact major keyword | 电子信息/计算机相关扩展、珠三角城市集合、稳妥一点 | 珠三角需要先确认成城市集合 |
| E2E04 | 广东物理 28000，冲好学校，不去偏远城市 | 生源地、科类、排位 context | 冲一冲 | 好学校、太偏远城市缺 verified schema |
| E2E05 | 广东历史 30000，公办本科，专业不冷门，费用低 | 生源地、科类、排位 context | 费用低一点 | 公办本科、专业冷门度 |
| E2E06 | 广东物理 70000，保底，计算机/电子/自动化相关 | 生源地、科类、确认后的 exact major keyword | 保底、相关专业扩展 | major family 需要确认扩展集合 |
| E2E07 | 广东物理 40000，深圳广州佛山，学费两万以内，优先公办 | 生源地、科类、城市 contains 深圳/广州/佛山、学费 <= 20000 | 无 | 公办 |
| E2E08 | 广东历史 18000，新闻传播或法学，学校名气重要 | 生源地、科类、确认后的 exact major keyword | 新闻传播/法学选择或扩展 | 学校名气 |
| E2E09 | 广东物理 35000，人工智能/软件工程/网络安全，稳一点 | 生源地、科类、确认后的 exact major keyword | 多专业选择/扩展、稳一点 | 暂无额外可执行字段 |
| E2E10 | 广东物理 60000，不冒险，学费低，城市不要太差 | 生源地、科类、排位 context | 不想太冒险、学费低、城市集合确认 | 城市质量 tier 缺失，除非确认成明确城市 |

## 评估作用

这些 case 还不是完整推荐质量测试，而是方法论测试，用来检查：

- deterministic rule extraction；
- candidate rule holding；
- non-executable preference preservation；
- schema hallucination prevention；
- deterministic over-promotion prevention。

这 10 条 case 已经包含在当前 40-case evaluation set 中。最新 API-backed evaluation 结果是：

- `rule_regex_extractor_symbolic_verifier`：`320/320`，over-promotion `0.000`；
- `deepseek_extractor_symbolic_verifier`：`320/320`，over-promotion `0.000`；
- `llm_only_baseline`：`107/200`，over-promotion `0.475`；
- `schema_aware_llm_only_baseline`：`156/200`，over-promotion `0.275`。

这个结果支持当前边界：LLM extraction 可以提高覆盖率，但 executability 必须由 symbolic verification 控制。
