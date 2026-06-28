# 本地表格筛选助手

这是一个本地运行的结构化表格筛选工作台。普通用户入口只读取自己上传的 Excel/CSV，并根据上传表格在本机生成已审核的字段能力和查询规则；研发和演示模式仍保留广东招生数据链路，用于验证志愿填报场景。

它的核心原则很简单：

```text
自然语言可以提出偏好，但只有表格里存在、已经审核、可以解释的字段才会参与筛选。
```

所以它不是普通聊天推荐系统，也不会因为你写了“稳一点”“学校好一点”“不想去中外合作”就偷偷生成筛选条件。页面会明确告诉你：

- 哪些条件已经参与筛选；
- 哪些条件还需要你确认；
- 哪些条件因为表格缺少字段或含义太模糊，没有参与筛选；
- 每条结果为什么会出现。

## 适合做什么

- 用广东招生 Excel 快速筛出符合条件的院校专业组。
- 把一份新的结构化表格变成本机可查询数据源，下次打开不用重新上传。
- 对比“冲一冲”“稳一点”“保底”等明确排位范围下的结果。
- 检查一份新表格的字段、类型、可筛操作和未执行偏好。
- 给 operator、老师或评审展示：筛选条件从哪里来，哪些偏好没有被执行。
- 给 LLM/agent 提供安全 tool 接口，让它只能查询和解释，不能绕过审核直接改规则。

## 不适合做什么

- 不给最终志愿填报建议。
- 不预测录取概率。
- 不用分数代替排位判断风险；广东志愿场景里，排位比裸分更关键。
- 不从自由文本里推断没有边界的规则，例如“学校好一点”“发展好一点”“不要太偏远”。
- 不在缺少字段时假装已经筛掉某类结果。例如表格没有“合作办学类型”字段时，“不想去中外合作”会被展示为未执行偏好。

## 快速开始

首次安装依赖：

```bash
make bootstrap
cp .env.example .env
```

启动后端：

```bash
make serve-user
```

macOS 也可以直接双击仓库根目录的 `start_local_user_web.command`。

如果想生成真正的 macOS `.app` 包：

```bash
make macos-app
open outputs/local_user_app/本地表格工作台.app
```

该 app 包内只放上传数据流所需的后端源码快照、tool contract 和前端构建产物；构建时会把可运行的 Python runtime 安装到 `~/Library/Application Support/SZU Local Workbench/runtime/workbench/`，双击后不需要再打开 Terminal。上传数据、LLM key、查询规则和日志也写入 `~/Library/Application Support/SZU Local Workbench/`；不会写回 app 包，也不会复制仓库里的 `.env`、上传数据、outputs 产物、内置 admissions/housing/products domain pack 或质量/pilot 诊断工具。更新代码或依赖后，重新运行 `make macos-app` 生成新快照并刷新本机 runtime。

这个 `.app` 是同一台机器上的本地启动包，不是跨机器分发包；如果移动到另一台电脑，需要在目标机器上从项目重新运行 `make macos-app`。

打开：

```text
http://127.0.0.1:8001
```

`make serve-user` 和 `start_local_user_web.command` 会先构建 `frontend-user/dist`，再用同一个 FastAPI 服务托管新本地用户 Web 和 API。`make macos-app` 生成的 `.app` 会复用该前端构建产物并在本机自动打开页面。需要改前端代码时，再使用开发模式：

```bash
cd frontend-user
npm install
npm run dev
```

开发模式地址：

```text
http://127.0.0.1:5173
```

`frontend-user/` 是面向本地用户的新入口，不加载旧 mock/demo 数据，也不展示内部领域数据源。它只从本机后端读取用户上传的数据源列表、能力摘要和 LLM 设置。旧 `frontend/` 仍保留给研发、演示和证据调试使用。

本机未设置 `AUTH_TOKENS_JSON` 时，`make serve-user` 会使用开发 token，并通过 HttpOnly cookie 让同端口页面访问本机 API；token 不会写进前端 JS 构建产物。生产或多人环境不要使用示例 token，应配置真实 `AUTH_TOKENS_JSON`；如仍需要本机单用户自动登录，可把 `LOCAL_USER_AUTO_AUTH_TOKEN` 设为其中一个真实 token。

发行给普通用户时建议使用：

```bash
APP_DISTRIBUTION_MODE=user_upload_only
```

该模式表示页面只面向用户上传表格和本机配置，不依赖内部 admissions Excel、内部 warehouse 或旧 mock 结果。

## 使用内置招生数据

内置 admissions API 模式会读取仓库根目录下的招生 Excel：

```text
广东省2025年志愿填报大数据（24-25）0523.xlsx
```

如果这个文件不存在，前端 demo 仍可查看，但内置 admissions 的 API 查询和旧 MVP demo 不能正常执行。
该真实数据文件属于本地数据资产，已被 `.gitignore` 排除；不要提交到版本库。

首次使用内置招生数据前，先构建本地结构化数据仓库：

```bash
source .venv/bin/activate
python scripts/build_data_warehouse.py
```

生成物默认写入 `outputs/data/`，包括 DuckDB warehouse、schema/value index 和 ingestion summary。DuckDB 和上传原件属于本地数据产物，默认不提交；内置 admissions 运行时需要的 `outputs/data/schema_value_index.json` 与 `outputs/data/ingestion_summary.json` 是经过 release check 约束的稳定证据产物，必须包含 `university_name`、`city`、`major_name`、`group_code` 等已审核字段，其中 `university_name` lookup 至少能精确命中“深圳大学”，`city` lookup 至少能命中“深圳”。如果这些产物落后，先重新运行 `python scripts/build_data_warehouse.py`，再运行 `python scripts/validate_release_package.py --json-only`。

内置 admissions Workbench 会使用 reviewed value entity linker 处理已审查 value index 中的显式实体。比如“我想进深圳大学”会优先识别为 `院校名称 = 深圳大学`，并抑制其中的 `深圳` 城市子串；“我想去深圳的大学”仍可识别为 `城市 in_contains 深圳`。如果用户说“深圳大学附近”或使用否定、距离、身份边界等表达，相关实体会写入 `EvidencePack.entity_linking.not_executed_links`，不会变成 SQL filter。这个 linker 只读取 schema/value index，不读原始 Excel，不调用 LLM，也不能绕过 `RuleVerifier`。

如果用户明确填写或表达了当前专业名称 value index 未命中的专业，例如“天体物理”，Workbench 会把原词保留到 `not_executed_preferences` / `unanswerable_intents`，并说明未进入 hard filter；不会静默忽略，也不会把它当作已执行的专业筛选。`就业好`、`宿舍好`、`学校氛围好一点` 这类外部质量偏好在没有已审查结构化字段时同样只作为不可回答/未执行证据保留，不会被误当作“相关专业”候选。

## 上传自己的表格

1. 启动后端和前端。
2. 打开页面上的“导入数据”。
3. 上传 Excel 或 CSV。
4. 点击“一键导入”。
5. 导入成功后，系统会回到数据源列表；点开可查询数据源进入查询页。
6. 如果导入失败或能力不足，再进入审查信息查看 sheet、表头、字段类型、风险字段和可筛操作。

上传流程会把数据状态从 `uploaded` 推到 `queryable`。未审核、缺少必填字段、warehouse 过期或 `dataset_id` 不合法时，系统会返回 blocked/error，不会执行 SQL。

一键导入会自动审查通用表格里后端判定安全的枚举、数值和标识字段，并只批准这些字段的安全操作。自由文本、高基数名称、备注和潜在 PII 字段不会自动变成 hard filter；页面可以展示后端结果中的源列名，但不能把未审查文本偏好当作已执行筛选。

如果同一份源文件被重复导入多次，本地用户列表会按文件 fingerprint 折叠展示，优先保留最新可查询版本；底层历史 dataset 不会被页面静默删除。

上传数据源在正式查询前会先运行查询前检查。通用表格的预检只确认数据源已经完成审查，不调用 LLM、不生成 SQL；招生语义链路会额外展示可执行事实、需要确认的边界、缺失信息和未执行偏好。用户确认后才会提交后端生成的 `preflight_id` 与确认项。

### 语义能力查询

上传 Excel/CSV 后，系统会基于表格字段生成 `capability_graph` 和 `semantic_query_options`，用来描述当前数据集实际支持哪些字段、值、操作和查询类型。新本地用户入口不复用内置 `admissions_schema_v1` 模板，也不会把上传表格切回内置 admissions 数据；domain 名称会按上传数据生成，例如 `uploaded_ds_xxx`。

通用表格查询页只渲染后端返回的字段控件。自然语言可以补充偏好，但只有已审查字段和已允许操作会进入参数化 SQL；缺失字段不能从自然语言里补出来，也不能被回答层暗示为已经筛选。

研发或 operator 显式选择招生模板时，上传 admissions 分数/位次表仍可走 reviewed admissions semantic 链路。例如源表只包含 `专业`、`所属专业组`、`最低位次`、`最低分数`、`学校所在` 等字段时，`admissions_schema_v1` 会按已审查列名别名映射到 canonical 字段。该模板不在 `user_upload_only` 普通用户模式中启用。

uploaded admissions 推荐现在走 reviewed semantic 链路：DeepSeek 先提出候选 `SemanticIntent`，系统随后运行 `EvidenceRequirementClassifier`，把每个 LLM 抽取出的 preference 先分成 `table_field`、`knowledge_base_or_reviewed_field`、`reviewed_ranking_policy`、`user_boundary` 或 `unsupported`。只有 `table_field` preference 会继续进入 `PreferenceGrounder`、`SemanticQueryVerifier` 和 verified `QueryAST`；需要 reviewed KB、reviewed ranking policy、用户边界或 unsupported 的偏好会进入 `not_executed_preferences` / `unanswerable_intents`，不会进入 SQL filter、候选 `RankingPlan` prompt 或答案结论。

对 `semantic_recommendation`，Workbench 只会在 evidence gate 之后继续请求候选 `RankingPlan`；只有 `RankingVerifier` 验证 reviewed 字段、allowed operation 和可信 value evidence 后，系统才用 `GenericRankingEngine` 排序，否则回答会明确称为“候选列表”。LLM 可以提出 `RankingPlan` 和 rationale，但不能直接排序、不能新增候选 item，也不能引用 EvidencePack 之外的就业、城市发展、学校氛围等结论。`EvidencePack.planner.evidence_requirements` 记录 gate 分流，`EvidencePack.planner.ranking_plan` 记录排序计划层的状态，例如 `generated`、`empty`、`generation_failed`、`deepseek_disabled` 或 debug-injected `supplied`。只给分数没有位次时返回 `needs_confirmation`，不执行 SQL。

uploaded admissions 查询的 `planner_mode` 默认为 `auto`：在 `ENABLE_LLM=true` 且 DeepSeek 可用时，系统会先调用 `DeepSeekSemanticIntentExtractor` 生成候选 `SemanticIntent`，再由系统验证并执行 `admissions_major_rank` 或 `semantic_recommendation`。UI 中明确填写的硬条件，例如生源地、科类、再选科目、省排位和分数，会在 verifier 之前合并进 `SemanticIntent.user_context`；LLM 没抽到或抽错这些上下文时，不能覆盖用户在表单中提交的结构化事实。DeepSeek 不可用、抽取失败，或适用的 `EvidenceRequirementClassifier` 失败时，`auto` 会降级到 legacy verified planner，但 `EvidencePack.planner` 会记录 `fallback_used`、`fallback_reason` 和错误类型摘要；显式传 `planner_mode=legacy` 可以跳过 LLM semantic planner。是否真的调用了 DeepSeek，应看 `token_usage.extractor` 和 `EvidencePack.planner`，不能只看答案文本。

本地探针命令：

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx
.venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx --query "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
ENABLE_LLM=true .venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx --planner-mode llm_semantic --query "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
ENABLE_LLM=true .venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx --planner-mode llm_semantic --live-llm --query "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
```

## 怎么填写查询

主查询页先选择一个本机数据源，再进入查询页。页面上的必填项、筛选字段和排序字段都来自后端生成的 `semantic_query_options`，不会固定显示招生字段。

通用表格通常只需要填写一句话需求，并在页面展示的字段控件里输入筛选值。招生模板或内置 admissions 链路才会出现生源地、科类、省排位、选科、排位范围等志愿填报字段；只给分数没有位次时，系统会要求补充广东省排位，不执行推荐 SQL。

填好后点击“查询前检查”，确认没有阻断项后再点击“执行查询”。

## 排位范围怎么理解

排位范围是用户明确选择的受控条件，不由 LLM 猜测；前端只提交后端白名单中的选项。

| 选项 | 含义 |
|---|---|
| 冲一冲 | 只执行后 `0%` 上界，不设置前向下界。 |
| 稳一点 | 只执行后 `15%` 上界，不设置前向下界。 |
| 保底 | 只执行后 `50%` 上界，不设置前向下界。 |

例如省排位是 `32000`，选择“保底”时，后端会生成 `专业组最低位次1 <= 48000`。`rank_window_lower_percent` 只是前端档位提示，不是 hard filter 下界。补充偏好里写“学校稳一点”不会自动变成 SQL；只有排位范围控件里的选择会参与执行。

## 怎么看结果

页面中间会展示“可看结果”，每条结果至少关注：

- 院校名称；
- 院校专业组代码；
- 专业名称；
- 城市；
- 学费；
- 专业组最低位次；
- 专业最低位次，如果原表提供；
- 当前排位与历史最低位次的差距。

右侧会展示“本次怎么筛”：

- 已参与筛选：已经进入后端规则和 SQL 的条件。
- 还要确认：系统识别到但需要你确认的候选条件。
- 没有参与筛选：表格缺字段、语义太模糊或需要外部信息的偏好。
- 为什么这样筛：基于 EvidencePack 的解释。
- 检查详情：给 operator 或开发者排查用的审计信息。

如果看到“未执行”，意思是系统保留了这条偏好，但没有把它当成筛选条件。

如果状态显示“仅提示”或“有提示”，说明后端返回了说明性 candidate/warning，但没有可提交的、可执行的 `candidate_id`；前端不会显示确认按钮，也不会把这些文本转成 SQL。只有上一轮响应里带有系统生成 `candidate_id` 且未被后端标记为不可执行的 candidate，才会进入“可确认条件”。

系统可以把家庭资源和就业目标结构化为补充问题与非执行证据，但在缺少已审查就业结果字段前，不会按“好就业”筛选或排序。

## LLM 能做什么

默认配置是：

```text
ENABLE_LLM=false
```

不配置 LLM 也可以使用 demo、上传数据、字段审核、DuckDB 查询、Quality Gate 和 tool server。

如果显式设置 `ENABLE_LLM=true` 并配置 `DEEPSEEK_API_KEY`，DeepSeek 只用于补齐 deterministic extractor 缺失的 slots、为 uploaded admissions 提出 schema-aware `SemanticIntent`、可选地在 bounded candidates 的 `row_id` 内 rerank，或基于证据解释结果。它不能生成 SQL，不能生成 hard rules，也不能绕过 `RuleVerifier`、reviewed mapping、确认回路、rerank validator 或 warehouse fingerprint guard。

验证 DeepSeek slot adapter：

```bash
ENABLE_LLM=true .venv/bin/python scripts/run_deepseek_slot_probe.py
```

该脚本只输出 fallback/adapter/token 使用摘要，不会打印密钥或完整 prompt。

## 管理员和 agent 权限

前端、operator 和 LLM/agent 都通过同一套 FastAPI/tool server 接入。

LLM-safe tools 只有：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

`dataset.upload`、`dataset.generate_domain_pack`、`approve-*`、`build-warehouse`、`quality.run` 和 `pilot.run` 都是写入或管理类工具，需要服务端 token 权限。服务端只信任 `AUTH_TOKENS_JSON` 里的 token 映射，不信任浏览器或请求体传来的 `permission_scopes`。

本地 Vite 开发模式会默认发送 `operator-token`，只用于配合 `make serve` 的本机演示。生产部署不得接受示例 token，必须通过服务端 `AUTH_TOKENS_JSON` 配置真实 token，并在网关或运维系统中控制 operator token 的分发。

## 常用命令

| 命令 | 用途 |
|---|---|
| `make bootstrap` | 创建 `.venv` 并安装 Python 依赖。 |
| `make serve` | 启动 FastAPI 后端。 |
| `make serve-user` | 构建并启动同端口本地用户 Web。 |
| `make macos-app` | 生成可双击的 macOS 本地用户 Web app。 |
| `make frontend-user-build` | 构建本地用户 Web 静态产物。 |
| `./start_local_user_web.command` | macOS 双击/命令行启动本地用户 Web。 |
| `cd frontend-user && npm run dev` | 启动本地用户 Web 开发模式。 |
| `cd frontend && npm run dev` | 启动旧研发前端。 |
| `make frontend` | 构建前端。 |
| `make test` | 运行单元测试。 |
| `make demo` | 运行 demo acceptance。 |
| `make pilot` | 使用内置 fixture 跑真实数据 pilot。 |
| `make operator-trial` | 使用 fixture 跑 operator trial。 |
| `make agent-acceptance` | 验证 fake agent 不能调用 admin tools。 |
| `make release-check` | 校验 release package。 |
| `make quality` | 运行统一质量门禁。 |
| `make clean-artifacts` | 清理临时产物。 |

健康检查：

```bash
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
```

## 发布前检查

候选发布前先准备依赖：

```bash
make bootstrap
```

另开一个终端启动后端：

```bash
make serve
```

再用另一个终端确认服务可用：

```bash
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
```

服务确认后，在主终端执行：

```bash
make demo
make pilot
make operator-trial
make agent-acceptance
make quality
make clean-artifacts
make release-check
```

完成后检查：

```bash
git status --short
```

工作区应保持干净，不能把临时 audit、上传原件、DuckDB、真实 Excel、密钥或本机报告提交进版本库。完整发布步骤见 [发布检查清单](RELEASE_CHECKLIST.md)。

## 项目结构

| 路径 | 说明 |
|---|---|
| `frontend-user/` | 独立本地用户 Web，不读取旧 mock/demo 数据。 |
| `frontend/` | 研发、演示和证据调试用 Vue 3 前端工作台。 |
| `src/` | 后端 API、规则验证、执行器和报告生成代码。 |
| `domains/` | admissions、housing、products 的 domain pack 配置。 |
| `rules/` | 跨 domain 的规则生命周期、信息需求和模糊词配置。 |
| `schemas/tools/` | tool contracts。 |
| `scripts/` | 数据构建、demo、评估、pilot 和 release 脚本。 |
| `docs/` | 方法、部署、安全、演示和排障文档。 |
| `sample_data/` | 小型脱敏样例数据。 |
| `sample_outputs/` | 精简示例输出和 release evidence。 |
| `outputs/` | 本地生成产物；大多数不应提交。 |

## 相关文档

- [本地部署说明](docs/local_deployment.md)
- [生产部署说明](docs/production_deployment.md)
- [安全模型](docs/security_model.md)
- [备份与恢复](docs/backup_restore.md)
- [故障排查](docs/troubleshooting.md)
- [演示脚本](docs/demo_script.md)
- [Workbench API 响应契约](docs/api_contract.md)
- [功能工具契约](docs/tool_contract.md)
- [Agent 使用指南](docs/agent_usage_guide.md)
- [Operator 操作指南](docs/operator_guide.md)
- [Real Dataset Pilot](docs/real_dataset_pilot.md)
- [Operator Trial Checklist](docs/operator_trial_checklist.md)
- [Operator Feedback Template](docs/operator_feedback_template.md)
- [方法报告](docs/methodology_report.md)
- [评估报告](docs/evaluation_report.md)
- [端到端 demo 用例](docs/end_to_end_demo_cases.md)
- [发布检查清单](RELEASE_CHECKLIST.md)
- [变更日志](CHANGELOG.md)
