# 偏好到规则验证前端

这是当前 Preference-to-Rule Verification 项目的前端工作台。页面默认调用后端 API，默认不展示演示结果；用户点击“查看演示数据”后才会加载本地演示数据。前端不新增推荐逻辑，也不推断新规则。

## C-lite 工作区

前端分为四个工作区：

- 查询：普通用户入口。uploaded admissions 会先做查询前检查，再允许确认后查询。
- 导入数据：普通上传入口。招生表采用一键导入，成功后自动成为可查询数据源。
- 字段审查：高级入口。只有字段模板不匹配或导入失败时使用。
- 证据调试：开发和研究入口。展示规则、候选、证据和 trace。

前端不生成 SQL、QueryAST、RankingPlan 或推荐规则。所有可执行条件必须来自后端验证结果。

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

## 验证清单

```bash
npm run test:unit
npm run build
```

后端 unit/API contract 检查在仓库根目录运行：

```bash
.venv/bin/python -m unittest discover -s tests
```

验收时还要做浏览器 smoke：

- desktop：验证 `导入数据 -> 查询前检查 -> 查询` 主路径，普通导入页只展示上传、一键导入和步骤状态。
- mobile：验证 `导入数据`、查询前检查和查询结果纵向滚动，不横向溢出。
- 如果浏览器截图捕获失败，需要在报告里说明，并用 DOM、console 和 responsive 检查结果作为浏览器证据。

## 数据来源

- 演示数据：页面默认不展示演示结果。用户必须点击“查看演示数据”后，前端才会加载 `src/mock/demo_run.json`，并在界面上标记为演示数据。演示数据只用于汇报、调试和本地说明，不代表已调用后端。
- 当前审计：展示本次运行的已执行规则数、可确认条件数、仅提示条件数、未参与偏好数、结果数量和 Trace 覆盖。

页面中的“中外合作未执行：缺少合作办学类型字段”是安全约束展示项，不代表已过滤中外合作。

“导入数据”工作区按 `上传文件 -> 一键导入 -> 可查询数据源` 展示普通上传路径。招生表默认使用 `template_id=admissions_schema_v1`，只复用招生字段模板，不读取内置招生表行，也不要求用户填写 `base_domain` 或城市字段映射控件。导入成功后，上传数据会自动成为主查询页的数据源；如果模板不匹配或导入失败，再进入“字段审查”查看 schema profile、review summary、approve/block 操作和原始 JSON。

“证据调试”工作区展示 uploaded dataset 的 `WorkbenchResponse` 中的 `items`、`top_results`、`result_sections`、`EvidencePack`、warnings 和 trace。`items` 与 `result_sections` 是主展示层，`top_results` 只作为兼容层。当 `status=needs_confirmation` 且 `candidates_to_confirm` 包含上一轮系统生成、可执行的 `candidate_id` 时，前端只允许提交这些 `candidate_id`；缺少 `candidate_id`、`executable=false`、`match_type=no_schema_field` 或 missing-schema 状态的 candidate 只展示为“仅提示”，不会出现确认按钮。如果是缺少位次等必要信息，则只展示 warning 并等待补充输入。`blocked`、`no_results`、warnings 和前端操作审计记录会单独显示。前端任何工作区都不生成 hard filter。

## 后端查询模式

启动后端：

```bash
make serve
```

后端查询模式优先从 `/api/workbench/options` 读取受控选项，包括排位范围、排序方式、规则提取方式、证据回答方式和大模型模式。后端不可用时，前端只使用本地保守选项渲染控件，并显示连接状态；不会把本地保守选项或 mock 伪装成真实查询结果。选择大模型辅助解析软偏好或大模型证据回答时，后端会返回 token 用量并在页面展示。模型用量区域区分三种状态：`已返回用量` 表示至少一个阶段返回正 token 数，`未发生调用` 表示后端返回了零用量，`未返回用量` 表示响应里没有该阶段 usage 字段；这三种状态都不能被前端解释成是否执行了筛选规则。
Vite 会把 `/api`、`/datasets` 和 `/workbench` 代理到本地后端。开发模式默认发送
`operator-token`，配合 `make serve` 可直接完成查询、上传、审核和建仓。生产构建不会内置
默认 token；如需覆盖本地 token，可在浏览器 `localStorage.actor_token` 写入服务端配置的 token。

主查询页面面向非技术用户：默认只需要填写生源地、科类、省排位、意向专业、排位范围和排序方式，然后点击“开始查询”。“城市”是查询工作区里的可选偏好控件，不是导入数据时必须填写的字段。右侧会用中文说明哪些条件已参与筛选、哪些还需要确认、哪些没有参与筛选。页面不会展示服务端 traceback，也不会在前端补造推荐规则。

当主查询页选择上传的 admissions 数据源时，第一次点击会先调用 `/workbench/preflight`，按钮显示“先做预检”。预检面板展示已识别事实、需要补充的信息、需要用户确认的边界，以及不会进入筛选或排序的偏好。用户处理边界后第二次点击“确认后查询”，前端才会把后端生成的 `preflight_id`、`confirmed_boundaries` 和 `disabled_boundaries` 发送到 `/workbench/query`。内置 admissions 数据源保持原查询流程，不经过这个预检 store。

当后端返回可执行 `candidates_to_confirm` 时，主查询页会展示“可确认条件”和“确认后再查”。前端只提交上一轮响应里的 `candidate_id` 到 `confirmed_candidates`，不会把用户第二轮自由文本编译成 SQL 或 hard filter。没有 `candidate_id` 或被后端标记为不可执行的偏好只展示为“仅提示”，不能在前端确认执行。

当 EvidencePack.decision_guidance 包含家庭资源或就业目标信息时，前端只展示后端返回的补充问题和“不参与筛选”说明；前端不根据这些信息生成 hard filter。

排位范围和排序方式必须由用户在前端控件中选择。前端只提交后端白名单中的
`rank_window_*` 和 `sort_mode` 值；自由文本和大模型只能提示选择，不生成 hard filter。

“建议先确认”只展示后端 EvidencePack 中的 reference-only 选项建议，不自动改写表单，也不触发查询。
