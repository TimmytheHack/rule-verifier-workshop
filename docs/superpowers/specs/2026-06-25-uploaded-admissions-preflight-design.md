# Uploaded Admissions 查询前检查设计

## 背景

当前前端已经支持内置 admissions 查询、uploaded dataset 上传审查、候选项确认再查和
`WorkbenchResponse` 展示。后端也已经在 uploaded admissions 的 LLM semantic
recommendation 链路中引入 evidence requirement gate：

```text
DeepSeekSemanticIntentExtractor
-> EvidenceRequirementClassifier
-> PreferenceGrounder
-> SemanticQueryVerifier
-> SQLBuilder
-> DuckDB candidates
-> DeepSeekRankingPlanGenerator
-> RankingVerifier
-> GenericRankingEngine
```

但现有前端仍以“直接查询后展示 warnings / not_executed_preferences”为主。用户输入
“我想进深圳大学，目前排位15000，帮我看看有什么专业可以选”这类问题时，系统已经可以避免把
“深圳大学”误拆成“深圳的大学”，但用户还不能在查询前看到哪些先验边界需要确认，哪些偏好当前没有证据不能执行。

本设计把 uploaded admissions 的主查询改成查询前门禁：

```text
自然语言输入
-> 查询前检查
-> 用户确认边界或选择暂不使用
-> 正式查询
-> 结果与证据展示
```

核心不变：

```text
前端只展示后端证据需求和确认项，不生成 hard filter、SQL、RankingPlan 或推荐逻辑。
```

## 目标

- uploaded admissions 数据源选中后，正式查询前必须先运行一次查询前检查。
- 查询前检查展示后端返回的执行资格：已识别事实、需要用户确认、不会参与筛选、还缺少信息。
- 用户只能确认后端生成的边界确认项，或选择暂不使用该边界。
- 正式查询只能引用当前查询前检查返回的 `preflight_id` 和系统生成的确认项 ID。
- 需要已审核知识库、已审核排序策略或已审核字段但当前没有证据的偏好，只展示为不会参与筛选，不提供确认按钮。
- 内置 admissions 数据源继续使用当前体验，不接入这次查询前检查。
- 所有普通用户可见文案使用中文；技术名只在调试折叠区或开发文档中保留。

## 非目标

- 不改内置 admissions 查询体验，包括既有 `广东省2025年志愿填报大数据（24-25）0523.xlsx` 数据源。
- 不实现通用自然语言 SQL planner。
- 不实现 reviewed KB ingestion、检索、引用和验证闭环。
- 不实现 reviewed ranking policy registry。
- 不扩展完整字段语义审核工作台。
- 不允许前端把自由文本、第二轮用户输入或 LLM 输出编译成 hard filter。
- 不允许前端直接生成或修改 `SemanticIntent`、`QueryAST`、SQL、RankingPlan 或 executable rules。

## 适用范围

查询前检查只在以下条件同时满足时启用：

- 主查询页当前数据源是 uploaded dataset；
- `domain_name=admissions`；
- uploaded domain pack 已批准并已生成可查询 warehouse；
- 用户发起自然语言查询；
- 前端处于 API 模式。

以下路径保持现状：

- 内置 admissions 数据源；
- 非 admissions uploaded dataset；
- 显式演示数据；
- legacy candidate confirmation 再查；
- 上传与审查页面中的字段审查和建仓流程。

## 用户流程

### 初始状态

主查询页保留现有信息架构：顶部运行条、左侧输入、右侧主要反馈区。

当选择内置 admissions 时，顶部按钮仍显示 `开始查询`，行为不变。

当选择 uploaded admissions 时，顶部按钮改为 `先做预检`。右侧显示 `查询前检查` 空态，不展示推荐结果。

### 查询前检查

用户填写基础信息和自然语言偏好后，点击 `先做预检`。

前端调用后端查询前检查接口。该步骤不返回推荐结果，不返回 SQL 结果行，不展示院校列表。

成功后右侧面板显示四类内容：

1. `已识别事实`
   - 明确来自用户输入或 reviewed value index 的事实。
   - 示例：`排位 = 15000`、`院校名称 = 深圳大学`、`科类 = 物理`。
   - 这些事实只表示可以进入验证链路，不表示已经执行 SQL。

2. `需要你确认`
   - 用户确认后才可作为受控边界进入正式查询的内容。
   - 示例：`稳一点` 确认成排位窗口，`计算机相关` 确认成专业关键词集合，`珠三角` 确认成城市集合。
   - 如果后端认为 `深圳大学` 存在实体边界歧义，可以要求确认 `按院校名称处理` 或 `暂不使用`。
   - 如果后端已经确定 `深圳大学` 是完整院校实体，则展示在 `已识别事实`，不强制用户确认。

3. `不会参与筛选`
   - 当前缺少已审核证据的偏好。
   - 示例：`好就业`、`学校好一点`、`不想去国外`、`学校氛围好`。
   - 每项显示原因，例如 `需要已审核知识库`、`需要已审核排序策略`、`当前表格没有已审核字段可以证明`。
   - 这些项没有确认按钮，不进入 SQL filter，不进入 RankingPlan，不进入最终回答 claim。

4. `还缺少信息`
   - 缺少正式查询所需的必要输入或数据源状态。
   - 示例：只有分数没有省排位、缺少科类、缺少再选科目、uploaded dataset 尚未 approved 或 warehouse 不可用。
   - 该区存在条目时，正式查询按钮保持禁用。

### 用户确认

`需要你确认` 中每个项目只能有受控操作：

- 选择后端给出的确认值；
- 选择 `暂不使用`。

前端不允许用户输入任意条件来补充该项。用户选择 `暂不使用` 后，该偏好在正式查询中进入
`not_executed_preferences`，不得参与筛选或排序。

所有可确认项都处理完，且 `还缺少信息` 为空后，按钮变为可用状态：`确认后查询`。

### 正式查询

正式查询引用同一轮查询前检查：

```text
preflight_id
confirmed_boundaries
disabled_boundaries
```

后端必须重新检查 dataset fingerprint、domain approval、warehouse 状态、reviewed mapping、
EvidenceRequirementGate、SemanticQueryVerifier 和 RankingVerifier。查询前检查结果不能绕过任何 verifier。

如果用户修改了输入、切换数据源、切换运行模式或查询前检查过期，前端必须清空确认状态并要求重新运行 `先做预检`。

## 后端契约方向

新增查询前检查接口：

```text
POST /workbench/preflight
```

请求形状接近现有 `/workbench/query`，但只用于 uploaded admissions：

```json
{
  "dataset_id": "dataset_...",
  "domain_name": "admissions",
  "user_input": "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选",
  "hard_filters": {},
  "soft_preferences": {},
  "planner_mode": "llm_semantic"
}
```

响应核心字段：

```json
{
  "status": "ready",
  "preflight_id": "pf_...",
  "dataset_id": "dataset_...",
  "domain_name": "admissions",
  "recognized_facts": [],
  "boundary_confirmations": [],
  "not_executable_preferences": [],
  "missing_requirements": [],
  "planner": {
    "semantic_intent": {},
    "evidence_requirements": {}
  },
  "warnings": []
}
```

`status` 含义：

| status | 用户可见含义 |
|---|---|
| `ready` | 可以进入查询。 |
| `needs_confirmation` | 需要确认边界后才能查询。 |
| `blocked` | 当前数据源或证据状态不允许查询。 |
| `error` | 查询前检查失败，前端展示净化后的错误。 |

正式查询请求新增引用字段：

```json
{
  "dataset_id": "dataset_...",
  "domain_name": "admissions",
  "preflight_id": "pf_...",
  "confirmed_boundaries": [
    {
      "confirmation_id": "boundary_..."
    }
  ],
  "disabled_boundaries": [
    {
      "confirmation_id": "boundary_..."
    }
  ]
}
```

安全要求：

- `preflight_id` 由后端生成，正式查询只能引用当前 query 对应的 ID。
- `confirmation_id` 由后端生成，前端只提交 ID 和后端允许的受控值。
- 伪造、过期、跨数据源、跨输入或不属于当前 preflight 的确认项必须被拒绝。
- 查询前检查不得返回 raw SQL。
- 错误响应不得暴露 traceback、绝对路径、密钥、prompt 原文或未净化 exception 文本。

## 前端信息架构

采用已确认的 A 方案：左输入，右查询前检查，结果在确认后出现。

```text
顶部运行条
  数据源 / 模式 / 运行选项 / 主按钮

主区域
  左侧：用户输入和受控基础字段
  右侧：查询前检查面板

结果区域
  查询前检查通过并正式查询后展示
```

uploaded admissions 状态机：

```text
idle
-> preflight_loading
-> preflight_needs_confirmation
-> preflight_ready
-> query_loading
-> ok / needs_confirmation / no_results / blocked / error
```

内置 admissions 状态机保持现有：

```text
idle
-> query_loading
-> ok / needs_confirmation / no_results / blocked / error
```

## 用户可见文案

普通用户界面不直接展示英文技术名。映射如下：

| 技术字段或概念 | 用户可见文案 |
|---|---|
| `preflight` | 查询前检查 |
| `recognized_facts` | 已识别事实 |
| `boundary_confirmations` | 需要你确认 |
| `not_executable_preferences` | 不会参与筛选 |
| `missing_requirements` | 还缺少信息 |
| `reviewed KB` | 已审核知识库 |
| `reviewed ranking policy` | 已审核排序策略 |
| `reviewed field` | 已审核字段 |
| `SemanticIntent` | 语义意图 |
| `RankingPlan` | 排序计划 |

示例文案：

```text
用户原话：学校好一点
系统判断：需要已审核排序策略
本次处理：不会参与筛选或排序
```

```text
用户原话：不想去国外
系统判断：当前表格没有已审核字段可以证明
本次处理：不会参与筛选
```

```text
用户原话：稳一点
系统建议：按位次窗口解释
你选择：冲一冲 / 稳一点 / 保底 / 暂不使用
```

技术字段名可以在调试折叠区展示，但必须避免让普通用户把技术名理解成已执行能力。

## 视觉方向

这不是 landing page，而是证据门禁型数据工作台。视觉目标是“填报场景中的专业审查台”：

- 保持现有 Element Plus 和工作台密度。
- 不做 hero、大插画、渐变背景或营销卡片。
- 用清晰状态色表达执行资格：绿色表示可进入验证链路，黄色表示需要确认，红色表示阻断，灰色表示不会参与。
- 卡片只用于独立面板和重复项，不做卡片套卡片。
- 移动端使用自然纵向滚动，顺序为输入、查询前检查、结果。
- 签名元素是 `执行资格条`：每个偏好都有用户原话、系统判断和本次处理，用户能快速看出哪些内容进入系统，哪些被挡住。

## 组件影响

前端实现预计涉及：

- `App.vue`：根据数据源切换查询前检查状态机，管理 `preflight_id` 和确认状态。
- 新增 `PreflightPanel.vue`：展示查询前检查四类内容和边界确认控件。
- `WorkbenchRunBar.vue`：uploaded admissions 时主按钮显示 `先做预检` 或 `确认后查询`。
- `UserInputPanel.vue`：输入变化时通知父组件清空过期 preflight。
- `workbenchRequests.js`：新增查询前检查请求构造和正式查询确认 payload 构造。
- `workbenchState.js`：新增 preflight 状态归一化、确认项提取和输入签名校验。
- `frontend/README.md`：同步说明 uploaded admissions 查询前检查。

后端实现预计涉及：

- 新增 `/workbench/preflight` endpoint 或同等 tool contract。
- 新增 preflight response dataclass / schema。
- 将 EvidenceRequirementGate 的输出整理成前端可展示的四类列表。
- 正式查询接受并验证 `preflight_id`、`confirmed_boundaries` 和 `disabled_boundaries`。
- 更新 `docs/api_contract.md` 和相关 API/tool contract 文档。

## 错误处理

- 查询前检查失败时，前端保留输入，不展示 mock 或旧结果。
- 后端返回 `blocked` 时，前端展示阻断原因和恢复路径，例如重新上传、完成审查或重建 warehouse。
- 用户修改输入、数据源、模型、planner mode 或基础字段后，已完成的查询前检查立即失效。
- 正式查询拒绝确认项时，前端展示后端返回的 rejected confirmation，不自行修正。
- 网络失败时，前端展示 `查询前检查失败，请稍后重试`，并保留输入。

## 测试与验收

实现后至少验证：

- uploaded admissions 数据源下，默认按钮为 `先做预检`，不直接查询。
- 内置 admissions 数据源下，按钮和现有查询体验不变。
- 查询前检查返回 `recognized_facts` 时，前端展示 `已识别事实`，但不展示推荐结果。
- 查询前检查返回 `boundary_confirmations` 时，用户必须确认或选择 `暂不使用` 才能正式查询。
- `not_executable_preferences` 中的 `好就业`、`学校好一点`、`不想去国外` 只展示 `不会参与筛选`，没有确认按钮。
- 缺少省排位、科类或再选科目时，`确认后查询` 保持禁用。
- 输入变化或数据源切换后，旧 `preflight_id` 和确认状态被清空。
- 正式查询 payload 只包含后端生成的 ID 和受控选择，不包含 SQL、hard rule 或 RankingPlan。
- `cd frontend && npm run test:unit` 通过。
- `cd frontend && npm run build` 通过。
- 后端相关单测覆盖伪造、过期、跨数据源 preflight 和 confirmation rejection。
- 浏览器桌面和移动视口检查无文字溢出、按钮遮挡或横向滚动。

## 已确认决策

- 采用主查询页两步门禁，不放在上传页，也不做轻量 sidecar。
- 查询前检查发生在正式查询之前。
- 前端调用后端查询前检查接口，不在前端判断证据需求。
- 第一版只覆盖 uploaded admissions。
- 内置 admissions 和既有广东大数据文件保持隔离。
- 第一版只允许确认边界类先验。
- 需要已审核知识库、已审核排序策略或已审核字段的偏好只展示不可执行，不给确认按钮。
- 普通用户可见文案全部中文。
