# 偏好到规则验证前端

这是当前 Preference-to-Rule Verification 项目的前端工作台。页面可使用演示数据，也可调用后端 API。前端不新增推荐逻辑，也不推断新规则。

工作台输入拆成两类：

- 考生基础信息：生源地、科类、再选科目（化学/生物/政治/地理四选二）、省排位。这些是结构化事实，进入后端后仍需经过规则验证。
- 偏好描述：专业、城市、费用、中外合作、学校性质等偏好都写入文本，由规则解析或 LLM 辅助解析。前端不为具体偏好预设勾选项。
- 边界确认：安全边际和费用上限只用于确认已经从文本中识别出的候选偏好，不会单独创建可执行规则。

## 技术栈

- Vue 3
- Vite
- Element Plus

## 本地运行

```bash
cd frontend
npm install
npm run dev
```

## 生产构建

```bash
cd frontend
npm run build
```

## 数据来源

- 演示数据：展示单次管线输出，包括规则解析、确定性规则、候选规则、不可执行偏好、最终可执行规则、筛选结果、行级追踪和证据回答。
- 当前审计：展示本次运行的已执行规则数、待确认规则数、未执行偏好数、结果数量和 Trace 覆盖。

页面中的“中外合作未执行：缺少合作办学类型字段”是安全约束展示项，不代表已过滤中外合作。

“上传数据集接入流程”面板调用 `/datasets` 和 `/workbench/query`：上传 CSV/Excel、展示 schema profile、展示 review summary、执行 approve/block、构建 warehouse，并把 uploaded dataset 的 `WorkbenchResponse` 中的 `items`、`top_results`、`result_sections`、`EvidencePack` 和 warnings 展示出来。面板优先用 `items` 和 `result_sections` 展示结果；`top_results` 只作为兼容层。`needs_confirmation` 会展示上一轮系统生成的 `candidate_id` 并允许 operator 选择后重跑；`blocked`、`no_results`、warnings 和前端操作审计记录会单独显示。该面板不在前端生成 hard filter。

## API 模式

启动后端：

```bash
make serve
```

API 模式只暴露受控选项：规则提取方式、证据回答方式和 LLM 模型。选择 LLM 辅助解析软偏好或 LLM 证据回答时，后端会返回 token 用量并在页面展示。
Vite 会把 `/api`、`/datasets` 和 `/workbench` 代理到本地后端。开发模式默认发送
`operator-token`，配合 `make serve` 可直接完成查询、上传、审核和建仓。生产构建不会内置
默认 token；如需覆盖本地 token，可在浏览器 `localStorage.actor_token` 写入服务端配置的 token。
