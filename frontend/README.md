# 偏好到规则验证前端

这是当前 Preference-to-Rule Verification 项目的前端工作台。页面可使用演示数据，也可调用后端 API。前端不新增推荐逻辑，也不推断新规则。

工作台输入拆成三部分：

- 考生基础信息：生源地、科类、再选科目（化学/生物/政治/地理四选二）、省排位。这些是结构化事实，进入后端后仍需经过规则验证。
- 排位范围：用户可以选择“先不选”“冲一冲”“稳一点”“保底”或“自定义”。这些选项会作为明确的 `rank_window_lower_percent` / `rank_window_upper_percent` 参数交给后端执行，不由 LLM 猜测。
- 偏好描述：专业、城市、费用、中外合作、学校性质等偏好可以写入文本，由规则解析或 LLM 辅助解析。前端不把自由文本直接变成 hard filter。

因此，补充偏好里的“学校稳一点”只会作为待确认或未执行偏好展示；只有用户在排位范围控件里明确选择窗口，后端才会按这个窗口筛选历史最低位次。

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

“上传数据集接入流程”面板调用 `/datasets` 和 `/workbench/query`：上传 CSV/Excel、展示 schema profile、展示 review summary、执行 approve/block、构建 warehouse，并把 uploaded dataset 的 `WorkbenchResponse` 中的 `items`、`top_results`、`result_sections`、`EvidencePack` 和 warnings 展示出来。面板优先用 `items` 和 `result_sections` 展示结果；`top_results` 只作为兼容层。`needs_confirmation` 如果包含上一轮系统生成的 `candidate_id`，会允许 operator 选择后重跑；如果是缺少位次等必要信息，则只展示 warning 并等待补充输入。`blocked`、`no_results`、warnings 和前端操作审计记录会单独显示。该面板不在前端生成 hard filter。

## API 模式

启动后端：

```bash
make serve
```

API 模式只暴露受控选项：规则提取方式、证据回答方式和 LLM 模型。选择 LLM 辅助解析软偏好或 LLM 证据回答时，后端会返回 token 用量并在页面展示。
Vite 会把 `/api`、`/datasets` 和 `/workbench` 代理到本地后端。开发模式默认发送
`operator-token`，配合 `make serve` 可直接完成查询、上传、审核和建仓。生产构建不会内置
默认 token；如需覆盖本地 token，可在浏览器 `localStorage.actor_token` 写入服务端配置的 token。

主查询页面面向非技术用户：默认只需要填写生源地、科类、省排位、意向专业、城市和排位范围，然后点击“查看可筛结果”。右侧会用中文说明哪些条件已参与筛选、哪些还需要确认、哪些没有参与筛选。页面不会展示服务端 traceback，也不会在前端补造推荐规则。
