# 前端 C-lite 重构设计

## 背景

当前前端已经能跑通 uploaded admissions 的上传、模板批准、建仓、查询前检查和正式查询。但页面形态仍接近调试工作台：

- 上传页暴露 `domainName`、`fieldId`、`opFieldId` 等内部概念，普通用户无法理解。
- 查询前检查组件已经存在，但不是主流程的第一视觉中心。
- 上传、字段审查、试查、调试 JSON 混在同一屏，用户不知道下一步该做什么。
- 现有布局延续“三列工作台”思路，和之前设计的“普通用户查询前确认流程”不一致。

本次重构采用 C-lite：

```text
普通体验采用一键导入和左输入右预检；
工程结构按查询、导入、字段审查、证据调试拆分；
第一版只打通 uploaded admissions，不把 admissions 写死到页面壳里。
```

核心边界保持不变：

```text
前端只展示后端 API 输出、确认项和证据状态，不生成 hard filter、SQL、QueryAST、RankingPlan 或推荐逻辑。
```

## 目标

- 让普通用户默认进入可理解的查询流程，而不是规则审查流程。
- uploaded admissions 正式查询前必须先展示查询前检查。
- 上传招生表的普通路径是一键导入：上传文件后自动执行上传、生成字段草稿、采用 admissions 模板、生成可查询数据。
- 失败时展示明确的步骤状态和后续处理，不暴露内部字段 ID 作为默认路径。
- 字段审查和证据调试作为独立工作区或折叠高级入口，不挤占普通查询与导入主路径。
- 工程结构预留未来数据类型接入能力，新增领域时尽量新增配置和适配组件，而不是重写页面壳。
- 保留已测试的 API 请求、状态归一化和 WorkbenchResponse 展示工具，降低重踩历史问题的概率。

## 非目标

- 不改后端验证边界、`WorkbenchResponse` 顶层契约或状态枚举。
- 不实现通用自然语言 SQL planner。
- 不实现 reviewed KB ingestion、检索、引用和验证闭环。
- 不实现 reviewed ranking policy registry。
- 不把字段语义审核做成完整多人协作后台。
- 不允许前端推断 admissions 规则、自动生成 SQL、构造 QueryAST 或生成 RankingPlan。
- 不删除内置 admissions 数据源；但 uploaded admissions 普通导入和查询必须与内置行数据隔离。
- 不在第一版支持任意领域自然语言分析；第一版只把框架做成可扩展。

## 总体选择

已确认的三项设计选择：

1. 重构范围选择 B：重写页面壳和主要可视组件，保留已测试的请求、状态、展示归一化工具。
2. 主查询布局选择 A：左侧输入，右侧查询前检查与结果。
3. 上传架构选择 C-lite：普通路径是一键导入，底层按导入、字段审查、证据调试拆分。

## 信息架构

页面分为四个工作区：

```text
查询
导入数据
字段审查
证据调试
```

### 查询

默认入口，面向普通填报用户。

职责：

- 选择数据源。
- 填写基础信息和自然语言目标。
- 对 uploaded admissions 先运行查询前检查。
- 展示已识别事实、需要确认的边界、不会参与筛选的偏好、还缺少的信息。
- 确认后发起正式查询。
- 展示结果、候选确认、筛选依据和关键提醒。

### 导入数据

普通用户上传数据的入口。

职责：

- 上传 CSV / Excel。
- 自动执行导入流水线。
- 显示当前数据源是否可查询。
- 失败时展示卡住的步骤、净化后的错误信息和进入字段审查的入口。

普通路径不展示：

- `domainName`
- `fieldId`
- `opFieldId`
- `template_id`
- 原始 profile JSON
- 任意可手输的字段授权输入框

### 字段审查

高级工作区，只在模板不匹配、字段缺失或用户主动进入时使用。

职责：

- 展示字段映射摘要。
- 展示缺失字段、风险字段、已批准字段和被阻断字段。
- 允许操作员针对后端返回的 reviewed mapping 候选做受控批准或阻断。
- 不在第一版做完整字段行内编辑器；保留后续扩展空间。

### 证据调试

开发和研究工作区。

职责：

- 展示完整 `WorkbenchResponse`、`EvidencePack`、trace、planner、warnings。
- 展示上传流水线的 audit events。
- 展示请求体摘要，但不得展示 secret、绝对路径、traceback 或 `.env` 内容。

## 主查询体验

主查询页采用：

```text
顶部状态条
左侧输入
右侧查询前检查 / 查询结果
底部或折叠区证据摘要
```

### 顶部状态条

展示：

- 当前数据源。
- 数据源类型：内置数据或上传表格。
- 当前模式：API 或演示。
- 当前状态：未查询、预检中、需要确认、可查询、查询中、已完成、已阻断、出错。
- 主按钮：`先做预检`、`确认后查询`、`开始查询`、`正在查询`、`重新预检`。

规则：

- 选择 uploaded admissions 时，按钮默认是 `先做预检`。
- 选择内置 admissions 时，按钮保持 `开始查询`，不强制接入本次 preflight。
- 修改输入、切换数据源或切换模式后，必须清空当前 preflight 选择。

### 左侧输入

左侧只保留普通用户能理解的字段：

- 生源地。
- 科类。
- 全省排位。
- 再选科目。
- 自然语言目标。
- 可选受控边界：排位窗口、排序方式。

保留的默认值可以体现广东招生场景，但文案要说明这是当前查询条件，而不是系统硬编码的学校或表格。

### 右侧查询前检查

uploaded admissions 的正式查询前，右侧先展示查询前检查。

四个区块固定：

```text
已识别事实
需要你确认
不会参与筛选
还缺少信息
```

交互规则：

- `已识别事实` 只说明系统识别到了可验证事实，不等于已经执行 SQL。
- `需要你确认` 只允许用户选择后端提供的选项，或选择暂不使用。
- `不会参与筛选` 不提供确认按钮。
- `还缺少信息` 有内容时，正式查询按钮禁用。

正式查询请求只能提交：

```text
preflight_id
confirmed_boundaries
disabled_boundaries
```

不能把用户第二轮自由文本编译成确认条件。

### 结果展示

正式查询成功后，右侧从查询前检查状态切换为结果状态。

最小结果形状继续保留：

```text
院校名称
院校专业组代码
专业名称
城市
学费
专业组最低位次
专业最低位次
safety margin
```

当结果为专业组明细时，允许展示分组结构：

```text
专业组
组内专业
最低分 / 最低位次
计划人数
```

当后端返回 `needs_confirmation` 或候选项时，前端只能展示候选确认面板并提交后端生成的 `candidate_id`。

## 导入体验

普通导入页采用一键导入。

用户流程：

```text
选择文件
-> 点击导入
-> 前端顺序调用导入流水线
-> 成功后生成上传数据源
-> 自动切回查询页并选中该数据源
```

第一版流水线：

```text
upload
-> generate-domain-pack(template_id=admissions_schema_v1, llm=off)
-> refresh profile
-> refresh review summary
-> approve-domain
-> build-warehouse
```

约束：

- 普通路径第一版只支持 `uploaded admissions`。
- `domain_name` 由当前导入类型选择产生，不让普通用户手输。
- admissions 模板只读取上传文件，不读取内置招生表行。
- 如果后端判断模板不匹配、字段缺失或批准失败，导入停止并展示步骤详情。
- 步骤详情使用中文状态，不展示原始异常堆栈。
- 提供进入 `字段审查` 的按钮。

导入页的状态展示：

```text
准备上传
正在上传
正在检查字段
正在确认字段模板
正在生成可查询数据
已可查询
需要字段审查
导入失败
```

## 字段审查体验

字段审查工作区面向操作员，不是普通用户主路径。

第一版展示：

- 数据集名称。
- 数据类型。
- 行数和列数。
- required fields。
- missing fields。
- risky fields。
- reviewed mappings。
- 当前 domain pack 状态。

第一版操作：

- 采用字段模板。
- 生成可查询数据。
- 查看字段映射详情。
- 查看调试 JSON。

暂不在第一版暴露任意 `field_id` 手输批准控件作为常规 UI。若必须保留，应放入 `开发者操作` 折叠区，并明确说明它只用于调试。

## 可扩展框架

前端新增领域时应优先新增配置，而不是改页面壳。

建议领域配置形状：

```js
{
  domainName: 'admissions',
  label: '招生录取数据',
  uploadMode: 'one_click_template',
  templateId: 'admissions_schema_v1',
  supportsPreflight: true,
  resultRenderer: 'admissions',
  requiredUserInputs: ['source_province', 'subject_type', 'user_rank'],
}
```

第一版只需要 admissions 配置，但组件边界按配置驱动：

- `domain adapters`：声明上传方式、预检能力、结果渲染器。
- `data source registry`：管理内置数据源和上传数据源。
- `query workspace`：不直接写死 admissions 字段，只消费 adapter 暴露的表单配置和结果渲染器。
- `import workspace`：按 adapter 执行导入流水线。
- `review workspace`：展示 adapter 返回的字段审查摘要。

admissions 可以作为唯一 adapter 存在，但不要把 `admissions_schema_v1`、专业组字段、广东默认值散落在多个组件里。

## 保留和重写边界

优先保留：

- `workbenchRequests.js`
- `workbenchState.js`
- `workbenchPresentation.js`
- `workbenchOptions.js`
- `uploadDatasetState.js`
- `uploadFiles.js`
- 已覆盖请求和状态转换的单元测试

优先重写：

- `App.vue` 的页面组织。
- `DatasetIngestionPanel.vue` 的普通用户导入体验。
- `PreflightPanel.vue` 的视觉层级和四区块展示。
- 结果区的信息层级。
- 调试 JSON 的默认折叠与入口位置。

可逐步迁移：

- `ResultTable.vue`
- `CandidateConfirmation.vue`
- `EvidenceReport.vue`
- `TraceDrawer.vue`
- `VerificationAudit.vue`

## 错误处理

- API 请求失败不回填演示数据。
- options 加载失败时展示连接状态，并明确处于 fallback。
- 上传失败必须指出失败步骤。
- 查询前检查失败只展示净化后的错误。
- 后端返回 `blocked` 时，前端说明“没有执行筛选或排序”，不得展示成正常推荐。
- 没有结果时，前端说明后端返回 0 条，不编造候选。

## 文案原则

普通用户可见界面使用中文。

避免显示：

- `preflight_id`
- `candidate_id`
- `domain_pack`
- `field_id`
- `QueryAST`
- `SemanticIntent`
- `RankingPlan`
- `DuckDB`

这些字段只允许出现在证据调试或开发者折叠区。

推荐文案：

| 技术概念 | 普通用户文案 |
|---|---|
| `preflight` | 查询前检查 |
| `recognized_facts` | 已识别事实 |
| `boundary_confirmations` | 需要你确认 |
| `not_executable_preferences` | 不会参与筛选 |
| `missing_requirements` | 还缺少信息 |
| `domain approval` | 确认字段模板 |
| `warehouse` | 生成可查询数据 |
| `blocked` | 已阻断 |

## 测试与验收

实现完成后至少验证：

- `cd frontend && npm run build`
- 主查询页默认不展示 mock 结果。
- 内置 admissions 仍可直接查询。
- uploaded admissions 必须先显示查询前检查。
- 修改输入后，旧 preflight 不可继续用于正式查询。
- `需要你确认` 只能提交后端生成的确认项。
- `不会参与筛选` 不提供确认按钮。
- 一键导入成功后自动选中上传数据源并回到查询页。
- 一键导入失败时显示失败步骤和进入字段审查的入口。
- 字段审查和调试 JSON 不出现在普通导入首屏。
- 桌面视口下主按钮、输入、预检、结果不互相遮挡。
- 移动视口下页面自然纵向滚动，没有横向溢出。
- 浏览器控制台无 Vue/Vite 错误 overlay。

如实现改动影响 README、API 契约说明或方法论文档，需要同步更新中文文档。

## 后续实现顺序

建议分四步实施：

1. 建立新页面壳和工作区导航，保留现有 API 工具。
2. 重写查询页：左输入、右预检、确认后结果。
3. 重写导入页：一键导入和失败步骤详情。
4. 移出字段审查与证据调试：普通路径隐藏高级内容。

每一步都应保持前后端可跑通，避免一次删除所有旧组件后失去可验证路径。
