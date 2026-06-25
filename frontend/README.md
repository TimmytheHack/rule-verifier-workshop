# 偏好到规则验证前端

这是当前 Preference-to-Rule Verification 项目的前端工作台。页面默认调用后端 API，默认不展示演示结果；用户点击“查看演示数据”后才会加载本地演示数据。前端不新增推荐逻辑，也不推断新规则。

工作台输入拆成四部分：

- 考生基础信息：生源地、科类、再选科目（化学/生物/政治/地理四选二）、省排位。这些是结构化事实，进入后端后仍需经过规则验证。
- 排位范围：用户必须选择“冲一冲”“稳一点”或“保底”。显式 `rank_window_lower_percent` / `rank_window_upper_percent` 只来自后端白名单，不由大模型猜测；后端只把 `rank_window_upper_percent` 对应的“后”边界作为 hard filter 上界执行，`rank_window_lower_percent` 仅作为 UI 档位提示，不是下界筛选条件。
- 排序方式：用户必须选择后端白名单中的 `sort_mode`；前端不从自由文本或大模型输出推导排序策略。
- 偏好描述：专业、城市、费用、中外合作、学校性质等偏好可以写入文本，由规则解析或大模型辅助解析。前端不把自由文本直接变成 hard filter。

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

- 演示数据：页面默认不展示演示结果。用户必须点击“查看演示数据”后，前端才会加载 `src/mock/demo_run.json`，并在界面上标记为演示数据。演示数据只用于汇报、调试和本地说明，不代表已调用后端。
- 当前审计：展示本次运行的已执行规则数、待确认规则数、未执行偏好数、结果数量和 Trace 覆盖。

页面中的“中外合作未执行：缺少合作办学类型字段”是安全约束展示项，不代表已过滤中外合作。

“上传与审查”工作区按 `上传文件 -> 生成草稿 -> 字段审查 -> 确认可查询 -> 生成可查询数据 -> 试查` 展示现有后端能力。首屏优先展示上传、生成草稿、采用字段模板、生成可查询数据和试查；手动批准字段、批准条件、阻断字段默认折叠到“高级字段操作”。工作表、缺失字段、风险字段、审查摘要、操作审计记录和原始 JSON 默认折叠到“调试数据”。

“上传与审查”工作区调用 `/datasets` 和 `/workbench/query`：上传 CSV/Excel、展示 schema profile、展示 review summary、执行 approve/block、构建 warehouse，并把 uploaded dataset 的 `WorkbenchResponse` 中的 `items`、`top_results`、`result_sections`、`EvidencePack` 和 warnings 展示出来。上传 admissions 表生成草稿时，前端提交 `template_id=admissions_schema_v1`，只复用招生字段模板，不读取内置招生表行，也不要求用户填写 `base_domain`。面板优先用 `items` 和 `result_sections` 展示结果；`top_results` 只作为兼容层。当 `status=needs_confirmation` 且 `candidates_to_confirm` 包含上一轮系统生成的 `candidate_id` 时，会允许 operator 选择后重跑；如果是缺少位次等必要信息，则只展示 warning 并等待补充输入。`blocked`、`no_results`、warnings 和前端操作审计记录会单独显示。该面板不在前端生成 hard filter。

## 后端查询模式

启动后端：

```bash
make serve
```

后端查询模式优先从 `/api/workbench/options` 读取受控选项，包括排位范围、排序方式、规则提取方式、证据回答方式和大模型模式。后端不可用时，前端只使用本地保守选项渲染控件，并显示连接状态；不会把本地保守选项或 mock 伪装成真实查询结果。选择大模型辅助解析软偏好或大模型证据回答时，后端会返回 token 用量并在页面展示。
Vite 会把 `/api`、`/datasets` 和 `/workbench` 代理到本地后端。开发模式默认发送
`operator-token`，配合 `make serve` 可直接完成查询、上传、审核和建仓。生产构建不会内置
默认 token；如需覆盖本地 token，可在浏览器 `localStorage.actor_token` 写入服务端配置的 token。

主查询页面面向非技术用户：默认只需要填写生源地、科类、省排位、意向专业、城市、排位范围和排序方式，然后点击“开始查询”。右侧会用中文说明哪些条件已参与筛选、哪些还需要确认、哪些没有参与筛选。页面不会展示服务端 traceback，也不会在前端补造推荐规则。

当主查询页选择上传的 admissions 数据源时，第一次点击会先调用 `/workbench/preflight`，按钮显示“先做预检”。预检面板展示已识别事实、需要补充的信息、需要用户确认的边界，以及不会进入筛选或排序的偏好。用户处理边界后第二次点击“确认后查询”，前端才会把后端生成的 `preflight_id`、`confirmed_boundaries` 和 `disabled_boundaries` 发送到 `/workbench/query`。内置 admissions 数据源保持原查询流程，不经过这个预检 store。

当后端返回 `candidates_to_confirm` 时，主查询页会展示“确认后再查”。前端只提交上一轮响应里的 `candidate_id` 到 `confirmed_candidates`，不会把用户第二轮自由文本编译成 SQL 或 hard filter。没有 `candidate_id` 的偏好只展示说明，不能在前端确认执行。

当 EvidencePack.decision_guidance 包含家庭资源或就业目标信息时，前端只展示后端返回的补充问题和“不参与筛选”说明；前端不根据这些信息生成 hard filter。

排位范围和排序方式必须由用户在前端控件中选择。前端只提交后端白名单中的
`rank_window_*` 和 `sort_mode` 值；自由文本和大模型只能提示选择，不生成 hard filter。

“建议先确认”只展示后端 EvidencePack 中的 reference-only 选项建议，不自动改写表单，也不触发查询。
