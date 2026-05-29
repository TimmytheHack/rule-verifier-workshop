# 方法论报告：当前 MVP

## 1. 当前 MVP 证明了什么

当前 MVP 证明：在一个结构化 Excel 数据集上，系统可以把一条自然语言志愿偏好转换为一个可审计的规则执行流程，并且不会假装所有偏好都可以执行。

对于固定输入，系统已经展示了：

- 读取 Excel 并检测真实表头行。
- 只根据真实字段构建 schema registry。
- 区分 deterministic rules、candidate rules 和 LLM-needed / non-executable parts。
- 在执行前进行规则验证。
- 对模糊偏好进行确认后再提升为可执行规则。
- 只执行已验证、已确认的规则。
- 为每条返回结果生成 rule trace。

关键证明不是“推荐结果很多”，而是系统能够在数据不支持时明确说：这个偏好不能执行。

## 2. 为什么它不是普通推荐机器人

普通推荐机器人会直接给用户推荐学校和专业。这个 MVP 研究的问题更窄：

```text
自然语言偏好中的哪些部分可以安全编译为可执行规则？
```

当前系统不做以下事情：

- 不按综合匹配度推荐学校。
- 不预测录取概率。
- 不评价学校声誉。
- 不判断就业质量。
- 不生成完整志愿表。

它输出的不只是结果列表，而是：

```text
结果列表 + 执行了哪些规则 + 哪些偏好没有执行 + 为什么没有执行
```

这对高风险决策很重要。一个看起来客观、但其实来自模糊偏好的规则，可能比明确的不确定性提示更危险。

## 3. 三类规则

### Deterministic Rules

Deterministic rules 是明确、可 schema grounding、可直接执行的规则。

当前 MVP 示例：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
```

这些规则允许执行，因为字段真实存在，且用户表达足够明确。

### Candidate Rules

Candidate rules 是对模糊偏好的可能解释。它们不能在用户确认前执行。

当前 MVP 示例：

```text
稳一点 -> 可能转为安全边际
太贵 -> 可能转为学费阈值
计算机相关扩展 -> 可能扩展到软件工程、人工智能等
```

当前 demo 模拟确认了前两项：

```text
稳一点 -> 10% 安全边际
太贵 -> 学费 <= 20000
```

同时拒绝了专业语义扩展：

```text
计算机相关扩展 -> false
```

### LLM-Needed / Non-Executable Parts

LLM-needed 或 non-executable parts 是当前 schema 无法支撑执行的偏好。

当前 MVP 中：

```text
不想去太贵的中外合作
```

其中“太贵”可以变成 candidate rule，因为有 `学费` 字段；但“中外合作”不能执行，因为没有可靠的 `cooperation_type` 字段。

## 4. 第一个 demo 输入

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

硬编码抽取结果：

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

这个阶段先硬编码抽取结果，是为了优先验证 rule verifier 和 trace 机制，而不是先做通用自然语言理解。

## 5. 最终可执行规则

模拟确认后，最终可执行规则为：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

其中 `35200` 来自：

```text
user_rank * 1.10 = 32000 * 1.10 = 35200
```

查询采用 AND 逻辑。结果必须同时满足全部 6 条规则。

当前 Excel 数据运行后返回 93 条结果。

## 6. 为什么没有执行“中外合作”

当前 Excel schema 中没有专门的 `cooperation_type` 字段。

系统理论上可以尝试从以下文本字段推断：

- `专业全称`
- `专业备注`
- `专业组名称`
- `组内专业`

但 MVP 刻意不这么做。文本推断容易混淆国际班、交换项目、联合培养、高收费项目和正式中外合作办学。这样会制造一个未经验证的派生字段，破坏 schema boundary。

因此该规则被阻止：

```text
No schema grounding, no deterministic execution.
没有 schema grounding，就不能 deterministic execution。
```

结果 trace 中也明确写明：

```text
Missing dedicated cooperation_type field; no text inference applied.
```

## 7. 为什么这对 rule verification 很重要

Preference-to-rule 系统最大的风险不是返回结果太少，而是悄悄执行了用户没有确认、数据也无法支撑的规则。

当前 MVP 展示了三种安全行为：

1. 模糊偏好不会自动提升为 deterministic rule。
2. 缺失字段会阻止执行。
3. 每条结果都有 trace。

这让系统可以被审计。用户或研究者可以看到：

- 哪些规则执行了。
- 哪些规则来自确认。
- 哪些偏好没有执行。
- 为什么没有执行。

核心研究贡献是：推荐结果应该建立在可验证规则构造之后。

## 8. 当前限制

当前 MVP 是刻意收窄的。

限制包括：

- 只支持一个输入。
- slot extraction 是硬编码的。
- 用户确认是模拟的。
- 没有 UI。
- 代码中不使用 LLM。
- 不做外部搜索。
- 不生成完整志愿表。
- 不估计录取概率。
- 不评价学校声誉。
- 不预测就业结果。
- 不从文本推断 `cooperation_type`。
- 不扩展 `计算机` 到相关专业。
- 使用 `专业组最低位次1` 作为安全边际字段，这是 MVP 的工程选择，后续需要领域评估。

这些限制是可接受的，因为当前目标是验证 rule verification 机制，而不是构建完整咨询产品。

## 9. 下一步评估计划：10 条测试输入

下一步评估重点是：系统是否能避免 deterministic over-promotion。

| ID | 输入 | 主要期望 |
|---|---|---|
| T01 | 我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。 | 与当前 demo 一致；中外合作不可执行。 |
| T02 | 广东物理，排位50000，只看广州，计算机。 | 只产生 deterministic rules，无模糊风险规则。 |
| T03 | 广东历史类，排位20000，想读法学，学校好一点。 | “学校好一点”必须是 candidate 或 LLM-needed，不能自动用排名过滤。 |
| T04 | 物理类，排位45000，计算机相关都可以。 | “计算机相关”必须要求确认扩展词表。 |
| T05 | 广东物理，排位60000，不想太贵。 | 必须询问学费阈值，不能发明上限。 |
| T06 | 广东物理，排位35000，想冲一冲计算机。 | “冲一冲”必须是 candidate，并要求明确风险解释。 |
| T07 | 广东物理，排位32000，不要中外合作。 | 如果没有 `cooperation_type`，必须不可执行。 |
| T08 | 广东物理，排位40000，想要就业前景好。 | “就业前景好”必须是 LLM-needed 或外部证据需求。 |
| T09 | 广东物理，排位30000，深圳，软件工程。 | “软件工程”作为精确关键词可 deterministic。 |
| T10 | 广东物理，排位32000，想去一线城市，费用别太高。 | “一线城市”依赖字段；“费用别太高”需要确认阈值。 |

评估指标：

- slot extraction precision / recall
- field mapping accuracy
- candidate recall
- schema violation rate
- invalid rule rejection rate
- trace completeness
- execution success rate
- deterministic over-promotion rate

最重要指标：

```text
deterministic over-promotion rate
```

目标应接近 0。宁可少执行规则，也不要错误执行模糊规则。

## 10. 如何泛化到其他结构化决策系统

同样的方法可以迁移到其他“自然语言偏好 + 结构化数据”的场景。

示例：

- 选课：时间、先修课、难度、老师、毕业要求。
- 租房：预算、通勤、区域、户型、安全感。
- 求职筛选：地点、薪资、岗位、行业、文化、成长空间。
- 商品推荐：价格、品牌、参数、主观质量、可靠性。
- 投资筛选：行业、市值、估值、流动性、风险偏好。

可迁移流程是：

```text
natural-language preference
-> rule class assignment
-> schema grounding
-> verification
-> confirmation
-> execution
-> trace
```

领域相关的是 schema registry 和 candidate-rule policy。安全原则保持不变：

```text
只执行已经 grounding、已经验证、必要时已经确认、并且可 trace 的规则。
```
