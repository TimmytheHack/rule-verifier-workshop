# MVP Demo 规格：第一个端到端 Preference-to-Rule 验证 Demo

## Demo 目标

本 demo 只展示一个固定输入的完整流程：

```text
自然语言偏好 -> 抽取 slots -> 分类规则 -> schema 验证 -> 模拟确认 -> 执行规则 -> 输出 trace
```

它不是完整志愿填报系统，也不是通用推荐机器人。它只验证第一条 demo 输入能否被保守地转换为可执行规则。

## Demo 输入

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

已知 Excel 约束：

- 工作簿只有一个 sheet：`Sheet1`。
- 真实表头在第 3 行。
- `生源地`、`科类`、`专业名称`、`城市`、`学费`、`专业组最低位次1` 都真实存在。
- `学费` 是文本形态，需要解析为数字。
- `专业组最低位次1` 可作为 MVP 的 2024 专业组最低位次 proxy。
- 没有专门的 `cooperation_type` 字段。
- 没有真实 `min_rank_2025` 字段；`25年预估位次` 是估计值，不是实际录取结果。

## 1. 预期抽取 slots

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
  }
}
```

注意：

- `广东` 表示考生生源地，不是院校所在省。
- `物理类` 规范化为 `物理`。
- `排位32000` 是用户上下文，不是 Excel 字段。
- `计算机` 在 MVP 中只做精确关键词匹配。
- `稳一点` 和 `太贵` 都是模糊偏好，不能直接执行。
- `中外合作` 缺少可靠字段，不能执行。

## 2. Deterministic Rules

```json
[
  {"field": "生源地", "operator": "eq", "value": "广东"},
  {"field": "科类", "operator": "eq", "value": "物理"},
  {"field": "专业名称", "operator": "contains", "value": "计算机"},
  {"field": "城市", "operator": "in_contains", "value": ["广州", "深圳"]}
]
```

这些规则都来自明确表达，并且字段真实存在。

## 3. Candidate Rules

```json
[
  {
    "source_text": "学校稳一点",
    "proposal": "专业组最低位次1 >= user_rank * safety_margin",
    "requires_human_confirmation": true
  },
  {
    "source_text": "太贵",
    "proposal": "学费 <= user_selected_cap",
    "requires_human_confirmation": true
  },
  {
    "source_text": "计算机相关扩展",
    "proposal": "是否扩展到软件工程、人工智能、数据科学、网络空间安全",
    "requires_human_confirmation": true
  }
]
```

Candidate rule 的原则是：可以提出，但不能在确认前执行。

## 4. LLM-Needed / Non-Executable Parts

```json
[
  {
    "source_text": "中外合作",
    "status": "not_executable_in_mvp",
    "reason": "Excel schema 中没有专门的 cooperation_type 字段。"
  }
]
```

MVP 不从文本字段推断中外合作。

## 5. 确认问题

### Q1：安全边际

```text
你说“学校稳一点”。请选择安全边际：

A. 轻微稳妥：专业组最低位次1 >= 32000 * 1.05 = 33600
B. 适中稳妥：专业组最低位次1 >= 32000 * 1.10 = 35200
C. 保守稳妥：专业组最低位次1 >= 32000 * 1.15 = 36800
D. 不使用这个规则
```

### Q2：学费阈值

```text
你说“不想太贵”。请选择最高可接受学费：

A. <= 10000 元/年
B. <= 20000 元/年
C. <= 40000 元/年
D. 不使用学费规则
```

### Q3：专业扩展

```text
你说“想学计算机”。是否扩展到相关专业？

A. 不扩展，只匹配“计算机”
B. 扩展到 软件工程、人工智能、数据科学、网络空间安全
C. 自定义相关专业词表
```

## 6. 模拟用户确认

```json
{
  "safety_margin": "10%",
  "rank_threshold": 35200,
  "tuition_cap": 20000,
  "major_expansion": false,
  "cooperation_type": "not_executable"
}
```

## 7. 最终可执行规则

```json
[
  {"field": "生源地", "operator": "eq", "value": "广东"},
  {"field": "科类", "operator": "eq", "value": "物理"},
  {"field": "专业名称", "operator": "contains", "value": "计算机"},
  {"field": "城市", "operator": "in_contains", "value": ["广州", "深圳"]},
  {"field": "专业组最低位次1", "operator": ">=", "value": 35200},
  {"field": "学费", "operator": "<=", "value": 20000}
]
```

非可执行偏好：

```json
{
  "source_text": "中外合作",
  "status": "not_executed",
  "reason": "缺少 dedicated cooperation_type 字段。"
}
```

## 8. 预期查询行为

查询引擎应当：

1. 使用第 3 行作为表头。
2. 从第 4 行开始遍历数据。
3. 对 6 条最终规则使用 AND 逻辑。
4. 将 `学费` 解析为数字后比较。
5. 对 `城市` 使用 `广州` / `深圳` contains 匹配。
6. 对 `专业名称` 只做 `计算机` 精确子串匹配。
7. 使用 `专业组最低位次1 >= 35200` 作为安全边际规则。
8. 不执行任何中外合作过滤。
9. 返回筛选结果。
10. 按 `专业组最低位次1 - 35200` 从小到大排序。

当前数据运行结果为 93 条。

## 9. Result Trace 格式

每条结果必须包含：

```text
PASS 生源地 == 广东
PASS 科类 == 物理
PASS 专业名称 contains 计算机
PASS 城市 matches 广州/深圳
PASS 专业组最低位次1 >= 35200
PASS 学费 <= 20000
NOT EXECUTED 中外合作：缺少 cooperation_type 字段
```

Trace 要求：

- 显示所有已执行规则。
- 显示未执行偏好及原因。
- 显示安全边际阈值。
- 显示解析后的学费。
- 每条 trace 必须对应具体行值，不能只是模板文本。

## 10. 本 demo 单元测试

### Slot extraction

| 测试 | 期望 |
|---|---|
| 提取广东 | `source_province = 广东` |
| 提取物理类 | `subject_type = 物理` |
| 提取排位32000 | `user_rank = 32000` |
| 提取计算机 | `major_keyword = 计算机` |
| 提取广州深圳 | `preferred_cities = [广州, 深圳]` |
| 提取稳一点 | candidate risk preference |
| 提取太贵 | candidate tuition preference |
| 提取中外合作 | non-executable preference |

### Rule classification

| 偏好 | 期望 |
|---|---|
| 广东物理类 | deterministic |
| 广州深圳 | deterministic if `城市` exists |
| 计算机 | deterministic exact keyword |
| 计算机相关 | candidate |
| 稳一点 | candidate |
| 太贵 | candidate |
| 中外合作 | non-executable if field missing |

### Query behavior

| 测试 | 期望 |
|---|---|
| AND 逻辑 | 返回行必须满足所有可执行规则 |
| 不过滤中外合作 | 不创建 cooperation_type 规则 |
| 城市匹配 | 只返回广州或深圳 |
| 专业匹配 | 只匹配 `计算机`，不扩展 |
| 安全边际 | `专业组最低位次1 >= 35200` |
| 学费阈值 | `学费 <= 20000` |
| 排序 | 按 `专业组最低位次1 - 35200` 升序 |

### 安全回归测试

| 禁止行为 |
|---|
| 未确认就执行“稳一点” |
| 未确认就发明“太贵”的学费上限 |
| 默认扩展到软件工程/人工智能 |
| 缺少字段时伪造中外合作过滤 |
| 执行 schema 中不存在的字段 |

## Demo 验收标准

Demo 成功条件：

1. 输入被拆解为 slots。
2. 三类规则被区分。
3. Candidate rules 不在确认前执行。
4. 缺失字段会阻止执行。
5. 模拟确认产生最终可执行规则。
6. 查询只使用可执行规则。
7. 每条结果有 trace。
8. 输出明确说明中外合作未被过滤。
