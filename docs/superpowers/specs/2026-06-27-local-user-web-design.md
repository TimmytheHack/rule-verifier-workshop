# 独立本地用户 Web 设计

## 背景

当前仓库已经有研发和演示用前端，但它包含 mock/demo 数据、证据调试视图和较多 operator 流程。新 Web 面向非技术用户本地使用，目标是让用户下载项目后打开应用，配置 LLM key，上传自己的 Excel/CSV，并在下次打开时继续使用本机已经导入的数据源。

核心边界保持不变：

```text
自然语言可以提出偏好，但只有表格里存在、已经审核、可以解释的字段才会参与筛选。
```

新 Web 不内置内部招生数据，不读取现有 mock 结果，不把前端做成推荐逻辑执行层。

## 设计读法

这是一个给学生、家长和本地操作者使用的信任优先本地产品 UI。它应该像“本地招生数据工作台”，不是营销页，也不是研发控制台。

设计取向：

- 首页先展示本机数据源库，用户先选表格，再进入查询页。
- 查询页由后端 profile、`capability_graph` 和 `semantic_query_options` 驱动，不在前端硬编码招生字段。
- 新 Web 不把 `admissions_schema_v1` 暴露为产品概念，也不以它做 UI 分支。
- 所有数据源都展示同一套 schema 驱动查询体验；招生能力只是后端能力摘要中的一种可能结果。
- 视觉上采用扁平、清楚、低阴影、8px 圆角、强文本层级和明确状态色条。

## 范围

第一阶段新增一个独立前端包，建议命名为 `frontend-user/`。它复用现有 FastAPI 后端和上传数据集能力，但不复用现有研发前端的 mock/demo 页面。

本阶段包含：

- 本地数据源首页。
- 数据源详情和 schema 驱动查询页。
- 上传和导入流程。
- LLM key 本地设置入口。
- 已导入数据源恢复。
- 查询前检查、确认后查询、结果和证据展示。
- 公开发行模式，禁止捆绑内部数据。

本阶段不包含：

- 任意表格的“全自动推荐”承诺。
- 前端生成 SQL、规则、RankingPlan 或最终推荐。
- 云端多用户账号体系。
- 将内部招生 Excel、内部 warehouse 或 mock evidence 打包给用户。

## 用户流程

### 首次打开

1. 用户打开本地 Web。
2. 页面检查本机是否有已导入数据源。
3. 如果没有数据源，展示两个主动作：配置 LLM、导入 Excel/CSV。
4. 用户可以先不配置 LLM，只使用确定性上传、字段审查和查询能力。

### 导入表格

1. 用户选择 Excel/CSV。
2. 前端调用 `POST /datasets/upload`。
3. 前端调用 `POST /datasets/{dataset_id}/generate-domain-pack`。
4. 前端调用 `GET /datasets/{dataset_id}/profile` 展示字段识别和能力摘要。
5. 如果需要用户说明表格用途，前端只提交用途提示，例如“招生数据”；如后端需要兼容现有接口，可由 API 适配层在内部映射到已审查能力种子，不能在 UI 中暴露模板名。
6. 前端调用 `POST /datasets/{dataset_id}/approve-domain` 和 `POST /datasets/{dataset_id}/build-warehouse`。
7. 后端返回 `status=queryable` 后，数据源进入首页列表。

### 再次打开

1. 前端调用新增的 `GET /datasets`。
2. 后端扫描 `DATA_ROOT` 下的 `dataset.json`，返回本机数据源列表。
3. 前端默认展示 `queryable` 数据源，同时保留 blocked/error 数据源的修复入口。
4. 用户点击某张表，进入该数据源详情页。

### 查询

1. 前端先调用 `GET /datasets/{dataset_id}/profile`。
2. 前端根据 `semantic_query_options.query_types`、`filters` 和 `sort_fields` 渲染查询控件。
3. 前端根据后端返回的必要用户上下文渲染必要输入，例如某个招生能力要求 `user_rank` 时才显示省排位输入。
4. 前端根据后端返回的查询准备状态决定按钮文案和结果文案，例如“查询候选列表”或“查看字段筛选结果”。
5. 用户提交后，优先调用 `POST /workbench/preflight` 做查询前检查。
6. 如果后端返回需要确认的边界或 candidate，用户只确认系统返回的 ID 或选项。
7. 前端再调用 `POST /workbench/query`。
8. 结果页展示已执行条件、待确认条件、未执行偏好、结果列表和 EvidencePack 摘要。

## 页面结构

### 本机数据源首页

主要内容：

- 顶部显示产品名和本机状态。
- 主区显示已导入数据源卡片。
- 空态显示“导入表格”和“配置 LLM”。
- 数据源卡片展示文件名、状态、行数、字段状态、最近更新时间和主按钮“开始查询”。
- blocked/error 数据源展示明确修复动作，例如重新生成字段摘要或重新建仓。

首页不显示 query 输入框。用户必须先选择一个数据源，避免 query 被发送到错误表格。

### 数据源详情页

主要内容：

- 顶部显示当前数据源名称、状态和能力摘要。
- 主区展示查询输入。
- 侧栏展示数据源状态、LLM 配置状态、可用查询能力和未支持能力。
- 查询前检查结果出现在 query 输入区下方。
- 查询结果和证据在同页下方或结果视图展示。

### Schema 驱动查询页

查询页只渲染后端确认过的能力：

- 一个自然语言 query 输入框。
- 基于 `semantic_query_options.filters` 的字段筛选器。
- 基于 `semantic_query_options.sort_fields` 的排序控件。
- 基于 `required_user_context` 的必要输入。
- 基于 `recommendation_readiness` 的能力状态说明。
- 对 `unsupported_fields` 的说明。
- 当后端没有可执行 `query_types` 时，显示“这份表格已导入，但当前字段还不足以执行语义查询”。

前端可以根据能力 ID 使用更贴近领域的字段 label，例如把 `user_rank` 显示为“省排位”，但 label、是否必填和可执行状态都来自后端能力描述。

### 内部领域能力包

后端可以继续保留 admissions domain pack 作为内部已审查能力种子，用来承载广东招生场景的字段别名、规则边界和测试基准。这个能力包不应该在新 Web 里表现为“模板选择”或 UI 分支。

用户看到的是能力摘要，例如“支持专业位次查询”“只能做字段筛选”“缺少省排位字段”。用户不需要知道内部是否使用了 `admissions_schema_v1`。

### 招生能力分级

不是所有 admissions 上传表都适合走同一条语义推荐链路。比如有的表只有院校层级，有的表缺少专业最低位次，有的表只包含分数没有排位，有的表年份或省份语境不适合广东志愿填报默认规则。

后端应把招生数据源分成能力层级，前端只消费该能力层级：

- `admissions_profile_only`：已识别为招生表，但缺少可查询必要字段，只能展示字段审查和缺失项。
- `admissions_filterable`：有已审查字段和可执行 filter/sort，但没有足够 evidence 做招生语义推荐。
- `admissions_major_rank`：后端 `semantic_query_options.query_types` 包含 `admissions_major_rank`，可以回答专业位次类查询。
- `admissions_candidate_list`：可以生成 verified filters 后的候选列表，但没有 verified `RankingPlan` 时不能称为排名推荐。
- `admissions_verified_recommendation`：只有后端确认 `query_types`、必要 `user_context`、字段映射、value evidence 和 `RankingPlan` 都通过验证时，才显示为推荐结果。

UI 文案必须跟随能力层级。没有 verified `RankingPlan` 时，页面说“候选列表”，不能说“推荐排序”。只有分数没有排位时，页面要求补充省排位，不执行推荐 SQL。

如果现有 `semantic_query_options` 不足以表达这些层级，后端应新增只读字段，例如 `capability_level` 或 `recommendation_readiness`。该字段由后端根据 reviewed mapping、`query_types`、必要 `user_context`、warehouse audit 和 `RankingPlan` 准备状态计算，前端只消费结果。

### 设置页

设置页用于本机 LLM 配置：

- 输入 DeepSeek API key、model 和 API URL。
- 保存后只显示“已配置”或“未配置”，不回显明文 key。
- 提供测试连接按钮。
- 没有配置 LLM 时，页面明确说明仍可使用确定性导入和已验证规则。

## 后端接口调整

现有后端已经支持上传、profile、review、建仓、preflight 和 query。新 Web 需要补齐这些产品化接口。

### `GET /datasets`

用途：启动时恢复本机数据源列表。

返回字段建议：

```json
{
  "datasets": [
    {
      "dataset_id": "ds_xxx",
      "status": "queryable",
      "domain_name": "admissions",
      "capability_level": "admissions_filterable",
      "recommendation_readiness": "candidate_list",
      "original_filename": "admissions.xlsx",
      "row_count": 24586,
      "column_count": 28,
      "created_at": "...",
      "updated_at": "...",
      "warnings": []
    }
  ]
}
```

接口必须只读取 `DATA_ROOT` 下的安全 dataset 目录，不扫描仓库根目录 Excel，也不读取内部 `outputs/data`。

### `GET /settings/llm`

用途：查询本机 LLM 配置状态。

返回字段建议：

```json
{
  "enabled": true,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "api_key_configured": true
}
```

接口不能返回 API key 明文。

### `POST /settings/llm`

用途：保存本机 LLM 配置。

服务端可以先保存到本机配置文件，后续桌面 App 版本再接入系统钥匙串。配置文件必须加入 `.gitignore`，不得进入提交。

## 数据和隐私策略

发行包必须排除：

- 根目录真实 `*.xlsx`、`*.xls`、`*.xlsm`、`*.csv`、`*.tsv`、`*.parquet`。
- `outputs/data/` 内部 warehouse 和 schema/value index。
- `outputs/uploaded_datasets/` 用户上传数据。
- 本地 DuckDB、SQLite 或其他数据库文件。
- 含真实内部结果的 mock/demo JSON。

发行模式建议新增环境变量：

```env
APP_DISTRIBUTION_MODE=user_upload_only
```

该模式下：

- 不展示内置 admissions 数据源。
- 不要求内部 `outputs/data` 存在。
- 不加载现有 `frontend/src/mock/demo_run.json`。
- 只允许用户上传、审查和查询本机数据源。

## 视觉系统

建议 token：

- `--surface`: `#F6F8F5`
- `--surface-elevated`: `#FFFFFF`
- `--text-primary`: `#17362F`
- `--text-muted`: `#60766E`
- `--accent`: `#2B6F8F`
- `--review`: `#D19B3D`
- `--danger`: `#B94B43`
- `--border`: `#D7DFD5`

视觉规则：

- 默认 8px 圆角。
- 少用阴影，主要用边框、间距和状态色条建立层级。
- 数字使用 tabular figures。
- 正文最小 16px。
- 所有可点击目标至少 44px 高。
- 图标使用同一 SVG icon family，不使用 emoji 作为结构图标。
- 动效只用于状态切换、按钮反馈和查询结果进入，必须支持 `prefers-reduced-motion`。

## 前端架构

建议新建独立 Vite/Vue 应用：

```text
frontend-user/
  src/
    api/
    components/
    pages/
    routes/
    styles/
    domain/
```

关键模块：

- `api/datasets`：封装 dataset list、profile、upload、review、warehouse。
- `api/settings`：封装 LLM 设置。
- `domain/queryOptions`：把 `semantic_query_options` 转成 UI 控件模型。
- `pages/DatasetLibrary`：本机数据源首页。
- `pages/DatasetDetail`：数据源详情和查询页。
- `pages/Settings`：本机设置页。
- `components/QueryComposer`：schema 驱动查询输入。
- `components/EvidenceSummary`：证据摘要展示。

前端 API 调用仍通过相对路径 `/datasets`、`/workbench`、`/settings`，便于后续由 FastAPI 同进程托管静态产物，也便于桌面 App 包装。

## 错误、空态和加载

必须覆盖这些状态：

- 没有数据源：展示导入入口和本机数据说明。
- 没有 LLM key：不阻断确定性流程，明确提示 LLM 辅助不可用。
- 上传失败：显示文件类型、大小或读取错误。
- profile 失败：提示重新上传或选择 sheet。
- 字段不足：展示缺少哪些必要字段，不执行查询。
- warehouse 过期或 audit 失败：提示重新建仓。
- preflight 需要确认：只允许确认后端返回的确认项。
- query 没有结果：展示已执行条件和可调整项，不伪造推荐。

## 测试计划

后端：

- `GET /datasets` 列出 queryable、blocked、error 数据源。
- `GET /datasets` 忽略非法目录和保留 dataset id。
- `GET /settings/llm` 不返回密钥明文。
- `POST /settings/llm` 写入本地配置并可被 DeepSeek client 读取。
- `APP_DISTRIBUTION_MODE=user_upload_only` 不依赖内部 admissions 数据。
- admissions 上传表缺少推荐必要字段时，后端能力摘要不能标记为 `admissions_verified_recommendation`。
- 后端可以内部使用 admissions 能力种子，但 `GET /datasets` 和 `profile` 不要求前端读取模板名才能决定 UI。

前端：

- 数据源首页空态。
- 数据源首页恢复已导入数据。
- `QueryComposer` 根据 `semantic_query_options` 渲染字段筛选器。
- `QueryComposer` 根据能力层级降级展示，不能把所有招生数据源都显示为推荐可用。
- 构建产物和运行时分支不以 `admissions_schema_v1` 作为 UI 条件。
- 没有 `query_types` 时展示不可执行说明。
- preflight 确认只提交系统返回的 ID。
- 构建产物不引用现有 mock/demo JSON。

验收：

```bash
.venv/bin/python -m unittest discover -s tests
cd frontend-user && npm run test:unit
cd frontend-user && npm run build
git diff --check
```

浏览器 smoke：

- 375px、768px、1440px 检查无横向滚动。
- 首页空态、导入流程、数据源恢复、查询页、结果页都可操作。
- `prefers-reduced-motion` 下没有必须依赖动画才能理解的状态。

## 后续桌面 App 兼容

本设计为后续 Tauri 或 Electron 包装保留边界：

- 前端只调用相对 API 路径。
- 后端负责本地数据目录、LLM 配置和静态资源托管。
- LLM key 的存储接口抽象在后端，未来可从本地配置文件切换到系统钥匙串。
- 用户数据目录不放在应用包内部，避免升级应用时丢失数据。

## 开放问题

- 本地 LLM key 第一版保存到配置文件还是直接接系统钥匙串。
- 通用非 admissions 表格第一版支持到字段筛选查询，还是允许更宽的自然语言语义意图。
- `frontend-user/` 是否需要与现有 `frontend/` 共享组件，还是完全复制少量基础组件以保持产品边界清晰。
