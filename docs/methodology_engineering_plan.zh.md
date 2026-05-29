# 面向广东高考志愿填报的 Preference-to-Rule Verification 工程方案

## 1. 项目动机

本项目不是普通志愿推荐机器人，而是一个方法论项目：研究如何把自然语言偏好安全地转换为可验证规则。

在高考志愿填报场景中，LLM 不应该直接根据用户一句话给出志愿建议。用户输入通常混合了硬事实、软偏好、风险偏好、费用限制和模糊价值判断。如果系统悄悄把模糊表达变成确定性筛选规则，就会制造“看似精确”的错误。

例子：

- `广东物理类`：如果 Excel 中有对应字段，可以安全转换为 deterministic rule。
- `广州深圳`：如果有城市字段，可以转换为城市筛选。
- `稳一点`：不能自动转换为固定安全边际，必须让用户确认。
- `太贵`：不能自动发明学费阈值，必须让用户确认。
- `就业前景好`：通常不能从当前 Excel 直接验证，只能作为语义解释或外部信息需求。

最危险的错误是 **deterministic over-promotion**：把模糊或无字段支撑的偏好错误提升为 deterministic executable rule。

## 2. 方法论定义

方法论流程：

```text
自然语言偏好
-> 偏好分解
-> 规则类别分配
-> schema grounding
-> rule verification
-> human confirmation
-> executable rule or rejection
-> result trace
```

每一步的作用：

- 偏好分解：拆开事实、偏好、约束和模糊表达。
- 规则类别分配：判断每个偏好是 deterministic、candidate 还是 LLM-needed。
- schema grounding：检查偏好是否能映射到真实数据字段。
- rule verification：检查字段、类型、操作符、取值、歧义、覆盖率和 trace。
- human confirmation：防止模糊偏好被悄悄执行。
- result trace：解释每条结果为什么出现。

本项目刻意不做通用 symbolic AI，而是聚焦广东高考志愿填报这一具体结构化数据场景。

## 3. 案例范围

第一个 case study 使用“广东省2025年志愿填报大数据（24-25）”Excel 数据集。

本项目不解决全部志愿填报问题，不生成完整志愿表，不预测录取概率，不判断学校声誉，也不直接提供最终咨询建议。

当前研究范围：

- 检查 Excel schema。
- 定义哪些字段可以支撑 deterministic execution。
- 将一个自然语言输入拆成规则类别。
- 根据 schema 验证规则。
- 对模糊偏好生成确认问题。
- 只执行已验证、已确认的规则。
- 输出结果 trace。

研究目标是 preference-to-rule verification，而不是推荐效果最大化。

## 4. 输入示例

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

该输入覆盖三类规则：

- 明确事实：广东、物理类、排位 32000。
- 如果字段存在则可执行的偏好：计算机、广州深圳。
- 需要确认的模糊偏好：稳一点、太贵。
- 可能缺字段的偏好：中外合作。

## 5. 示例的预期输出

### deterministic_rules

```json
[
  {"source_text": "广东物理类", "field": "subject_type", "operator": "eq", "value": "物理"},
  {"source_text": "广东", "field": "source_province", "operator": "eq", "value": "广东"},
  {"source_text": "排位32000", "field": "user_rank", "operator": "set_context", "value": 32000},
  {"source_text": "想学计算机", "field": "major_name", "operator": "contains", "value": "计算机"},
  {"source_text": "最好在广州深圳", "field": "city", "operator": "in", "value": ["广州", "深圳"]}
]
```

精确关键词匹配可以是 deterministic。把 `计算机` 扩展为软件工程、人工智能、数据科学、网络安全等，必须是 candidate，除非已有人工维护并确认的专业词表。

### candidate_rules

```json
[
  {
    "source_text": "学校稳一点",
    "proposal": "使用历史位次安全边际，例如 min_rank_2024 >= user_rank * 1.10",
    "requires_human_confirmation": true
  },
  {
    "source_text": "太贵",
    "proposal": "询问用户最高可接受学费",
    "requires_human_confirmation": true
  },
  {
    "source_text": "计算机相关",
    "proposal": "询问是否扩展到软件工程、人工智能、数据科学、网络空间安全",
    "requires_human_confirmation": true
  }
]
```

### llm_needed_parts

```json
[
  {
    "source_text": "不想去中外合作",
    "reason": "只有 schema 中存在可靠 cooperation_type 字段，或经过批准的派生规则时，才可执行。"
  }
]
```

### confirmation questions

```text
1. “稳一点”请选择安全边际：
   A. 5%: min_rank_2024 >= 32000 * 1.05
   B. 10%: min_rank_2024 >= 32000 * 1.10
   C. 15%: min_rank_2024 >= 32000 * 1.15

2. “太贵”请选择最高学费：
   A. <= 10000 元/年
   B. <= 20000 元/年
   C. <= 40000 元/年

3. “计算机”是否扩展相关专业：
   A. 只做精确关键词匹配
   B. 扩展到软件工程、人工智能、数据科学、网络空间安全
```

### executable rules after confirmation

假设用户确认：

- 稳一点 = 10% 安全边际。
- 太贵 = 学费 <= 20000 元/年。
- 计算机 = 不扩展，只做精确关键词。
- 中外合作 = 没有可靠字段，不执行。

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

```text
PASS source_province == 广东
PASS subject_type == 物理
PASS major_name contains 计算机
PASS city in 广州/深圳
PASS min_rank_2024 >= 35200
PASS tuition_yuan_per_year <= 20000
NOT EXECUTED cooperation_type exclusion: field missing or unverified
```

没有 trace 的结果不算完成验证。

## 6. 规则类别

### A. Deterministic rules

可以直接根据结构化字段执行，且已通过 schema grounding 和 verification。

例子：

- `广东物理类` -> `source_province == 广东`, `subject_type == 物理`
- `排位32000` -> `user_rank = 32000`
- `广州深圳` -> `city in [广州, 深圳]`
- `想学计算机` -> 精确匹配 `major_name contains 计算机`
- `不要中外合作` -> 只有存在可靠 `cooperation_type` 字段时才 deterministic

### B. Candidate rules

AI 可以提出候选解释，但必须由用户确认后才能执行。

例子：

- `计算机相关` -> 是否包括软件工程、人工智能、网络空间安全
- `稳一点` -> 安全边际 5%、10%、15%
- `太贵` -> 学费阈值
- `学校好一点` -> 是否使用学校标签、排名、双一流、985/211 等字段

### C. LLM-needed parts

当前 Excel schema 无法安全规则化的内容。

例子：

- `就业前景好`
- `学校氛围好`
- `老师负责`
- `城市发展潜力好`
- `专业未来趋势好`

这些内容不能被悄悄转换为 deterministic filters。

## 7. Schema Registry 设计

Schema registry 是系统边界。它定义系统允许执行什么。

如果偏好不能 grounding 到 registry，就不能成为 deterministic executable rule。Registry 防止 LLM 发明字段或过度解释用户输入。

示例字段：

```json
[
  {
    "field_id": "subject_type",
    "source_column": "科类",
    "type": "enum",
    "aliases": ["科类", "物理类", "历史类", "首选科目"],
    "allowed_ops": ["eq"],
    "nullable": false,
    "notes": "预期值包括物理、历史。"
  },
  {
    "field_id": "user_rank",
    "source_column": null,
    "type": "integer_context",
    "aliases": ["排位", "位次", "排名"],
    "allowed_ops": ["set_context"],
    "nullable": false,
    "notes": "用户输入上下文，不是 Excel 字段。"
  },
  {
    "field_id": "major_name",
    "source_column": "专业名称",
    "type": "string",
    "aliases": ["专业", "想学", "专业名称"],
    "allowed_ops": ["eq", "contains", "in"],
    "nullable": false,
    "notes": "精确关键词可 deterministic；语义扩展需确认。"
  },
  {
    "field_id": "city",
    "source_column": "城市",
    "type": "string",
    "aliases": ["城市", "地区", "广州", "深圳"],
    "allowed_ops": ["eq", "contains", "in"],
    "nullable": true,
    "notes": "城市值可能需要规范化。"
  },
  {
    "field_id": "tuition_yuan_per_year",
    "source_column": "学费",
    "type": "number_from_string",
    "aliases": ["学费", "费用", "太贵"],
    "allowed_ops": ["<=", ">=", "between"],
    "nullable": true,
    "notes": "需要从文本单元格中解析数字。"
  },
  {
    "field_id": "cooperation_type",
    "source_column": null,
    "type": "enum",
    "aliases": ["中外合作", "国际班", "合作办学"],
    "allowed_ops": ["eq", "neq", "in", "not_in"],
    "nullable": true,
    "notes": "缺少专门字段时不可执行。"
  }
]
```

其他建议字段包括：

- `school_name`
- `min_score_2024`
- `min_rank_2024`
- `min_score_2025`
- `min_rank_2025`
- `batch`
- `plan_count`

每个字段都应声明：

- `field_id`
- `source_column`
- `type`
- `aliases`
- `allowed_ops`
- `nullable`
- `notes`

## 8. Rule JSON 格式

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
  "trace_reason": "用户明确表达物理类，schema 中存在 subject_type。"
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
  "trace_reason": "稳一点是模糊偏好，必须确认安全边际。"
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
  "trace_reason": "用户确认对 32000 排位使用 10% 安全边际。"
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
  "verification": {
    "field_exists": false,
    "executable": false
  },
  "trace_reason": "schema 中没有可靠 cooperation_type 字段。"
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
  "verification": {
    "schema_grounded": false,
    "executable": false
  },
  "trace_reason": "就业前景无法由当前 Excel schema 直接表示。"
}
```

## 9. Rule Verification Protocol

每条可执行规则都必须通过：

1. Field existence check：字段必须存在于 schema registry。
2. Type check：规则值必须匹配字段类型。
3. Operator check：操作符必须被该字段允许。
4. Value normalization check：别名、城市名、科类、数字文本必须规范化。
5. Ambiguity check：`稳一点`、`太贵`、`好一点`、`相关` 等触发 candidate。
6. Data coverage check：高缺失率字段应警告或阻止执行。
7. Conflict check：规则之间不能互相矛盾。
8. Dry-run check：在样本数据上执行，检查空结果、类型错误和不可能过滤。
9. Traceability check：每条规则必须保留来源文本和解释。

原则：

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
```

中文解释：

```text
没有 schema grounding，就不能 deterministic execution。
没有人工确认，就不能把 candidate rule 提升为 executable rule。
```

## 10. Human Confirmation 设计

Human confirmation 应把模糊偏好转换为明确选择。

`稳一点` 示例：

```text
5%: min_rank_2024 >= user_rank * 1.05
10%: min_rank_2024 >= user_rank * 1.10
15%: min_rank_2024 >= user_rank * 1.15
```

`太贵` 示例：

```text
<= 10000 元/年
<= 20000 元/年
<= 40000 元/年
自定义
```

`计算机相关` 示例：

```text
只匹配计算机
包括软件工程
包括人工智能
包括数据科学
包括网络空间安全
```

UI 应明确显示哪些规则会执行，哪些仍不可执行。确认决策也应写入 trace。

## 11. Flowchart

```text
用户输入
  |
  v
偏好分解
  |
  v
提取 slots 和原始短语
  |
  v
Schema registry lookup
  |
  v
规则分类
  |----------------------|----------------------|
  v                      v                      v
Deterministic        Candidate              LLM-needed
rules                rules                  parts
  |                      |                      |
  v                      v                      v
规则验证              确认问题               语义说明
  |                      |
  v                      v
可执行？              用户确认？
  |                      |
  v                      v
执行规则 <------------ confirmed candidate rule
  |
  v
筛选 / 排序结果
  |
  v
Result trace
  |
  v
研究报告 / demo 输出
```

## 12. MVP 范围

MVP 只支持：

- 一个 Excel 数据集。
- 一个单轮用户输入。
- schema loading。
- preference decomposition。
- rule classification。
- rule verification。
- confirmation question generation。
- simulated confirmation。
- query execution。
- result trace。

明确不做：

- 完整志愿表生成。
- 学校声誉判断。
- 就业预测。
- 外部 web search。
- 多轮 advisor bot。
- 通用 symbolic AI。

MVP 是 verification demo，不是完整产品。

## 13. 工程模块

```text
schema_loader
  读取 sheet、列名、样例行、类型、缺失率，生成 schema registry。

slot_extractor
  将用户输入拆成事实、偏好、模糊短语和语义部分。

rule_classifier
  将偏好分为 deterministic、candidate、LLM-needed。

candidate_rule_generator
  为模糊偏好提出候选操作解释，但不执行。

rule_verifier
  执行字段、类型、操作符、取值、歧义、覆盖率、冲突、dry-run 和 traceability 检查。

human_confirmation
  将 candidate rules 转为 confirmed、edited 或 rejected。

query_engine
  只执行 verified deterministic 和 confirmed rules。

trace_generator
  生成 rule-level 和 row-level 解释。

report_builder
  输出规则、验证、确认、结果和 trace。

evaluation
  评估抽取质量、规则安全、schema violation 和 trace completeness。
```

## 14. 测试用例

测试重点是防止 vague preference over-promotion。

### 正向 deterministic cases

| 输入短语 | 期望 |
|---|---|
| 广东物理类 | deterministic |
| 排位32000 | deterministic context |
| 广州深圳 | 如果 city 字段存在，则 deterministic |
| 专业名称包含计算机 | deterministic |
| 不要中外合作 | 只有 cooperation_type 存在才 deterministic |

### Candidate cases

| 输入短语 | 期望 |
|---|---|
| 稳一点 | candidate |
| 太贵 | candidate |
| 计算机相关 | candidate |
| 学校好一点 | candidate 或 LLM-needed |
| 不想风险太大 | candidate |

### 安全负例

| 输入短语 | 必须防止的错误 |
|---|---|
| 稳一点 | 未确认就自动编译为 10% |
| 太贵 | 自动发明学费阈值 |
| 就业前景好 | 没有字段支撑却执行 |
| 中外合作 | 缺字段时仍过滤 |
| 学校好一点 | 未确认就自动使用排名 |

## 15. 评估指标

核心指标：

- Slot extraction precision / recall
- Field mapping accuracy
- Deterministic over-promotion rate
- Candidate recall
- Schema violation rate
- Invalid rule rejection rate
- Trace completeness
- Execution success rate

最重要指标：

```text
deterministic over-promotion rate
= 被错误分类为 deterministic 的模糊或无字段偏好数量
  / 所有模糊或无字段偏好数量
```

目标应接近 0。宁可少执行规则，也不要错误执行模糊规则。

## 16. 两周实现路线图

### Week 1

- 检查 Excel sheets 和 columns。
- 根据真实列构建第一版 schema registry。
- 标注 missing-but-desired fields。
- 定义 rule taxonomy。
- 定义 rule JSON schema。
- 实现 verifier 设计。
- 创建重点防止 over-promotion 的测试。

### Week 2

- 实现 query engine。
- 实现 confirmation flow。
- 生成 rule trace 和 row trace。
- 跑通单条 demo case。
- 评估 rule classification 和 verification 行为。
- 写方法论报告。

实现必须保持窄范围。目标是可信研究工程 demo，而不是完整产品。

## 17. 研究贡献

本项目贡献的是一种实用方法：如何把自然语言偏好安全转换为结构化数据上的可验证规则。

广东高考志愿填报适合作为首个领域，因为它具有：

- 高风险决策。
- 结构化 Excel 数据。
- 大量模糊用户偏好。

同一方法可以泛化到：

- 选课：难度、时间、老师、毕业要求。
- 租房：预算、通勤、区域、安全感。
- 求职筛选：地点、薪资、岗位、行业、文化。
- 商品推荐：价格、功能、品牌、可靠性。
- 投资筛选：行业、估值、风险、流动性。

通用贡献不是一个万能推荐器，而是 verification-centered workflow：

```text
Only execute what is schema-grounded, type-safe, operator-valid,
ambiguity-checked, and traceable.
```

中文原则：

```text
只执行已经 schema grounding、类型安全、操作符合法、歧义已处理、并且可 trace 的规则。
其他内容必须确认、拒绝，或保留为语义上下文。
```
