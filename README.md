# 招生筛选助手

这是一个本地运行的招生数据筛选工作台。你可以使用内置招生数据，也可以上传自己的 Excel/CSV，填写生源地、科类、省排位、意向专业、城市、排位范围和排序方式，然后查看哪些专业组通过了数据筛选。

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
- 对比“冲一冲”“稳一点”“保底”等明确排位范围下的结果。
- 上传一份新表格，检查它能不能安全地变成可查询数据。
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
make serve
```

另开一个终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

只看前端演示数据时，可以不启动后端。要使用真实 API、上传表格、审核字段或构建 warehouse，需要后端正在运行。

## 使用内置招生数据

内置 admissions API 模式会读取仓库根目录下的招生 Excel：

```text
广东省2025年志愿填报大数据（24-25）0523.xlsx
```

如果这个文件不存在，前端 demo 仍可查看，但内置 admissions 的 API 查询和旧 MVP demo 不能正常执行。

首次使用内置招生数据前，先构建本地结构化数据仓库：

```bash
source .venv/bin/activate
python scripts/build_data_warehouse.py
```

生成物默认写入 `outputs/data/`，包括 DuckDB warehouse、schema/value index 和 ingestion summary。这些本地数据产物默认不提交。

## 上传自己的表格

1. 启动后端和前端。
2. 打开页面上的“上传表格”。
3. 上传 Excel 或 CSV。
4. 查看系统识别出的 sheet、表头、字段类型、缺失字段和风险字段。
5. 按页面提示审核字段和可筛操作。
6. 点击构建 warehouse。
7. 回到“我要查询”，在“数据源”里选择上传表格。

上传流程会把数据状态从 `uploaded` 推到 `queryable`。未审核、缺少必填字段、warehouse 过期或 `dataset_id` 不合法时，系统会返回 blocked/error，不会执行 SQL。

### 语义能力查询

上传招生 Excel/CSV 后，系统会基于表格字段生成 `capability_graph` 和 `semantic_query_options`，用来描述当前数据集实际支持哪些字段、值、操作和查询类型。自然语言只会提出候选 `SemanticIntent` / `QueryAST`；只有经过已审查字段、已允许操作和值解析校验后，才会进入参数化 SQL。

例如一张新的 admissions 分数/位次表只包含 `专业`、`最低位次`、`最低分数`、`学校所在` 等字段时，系统可以生成按专业最低位次计算的 `冲`、`稳`、`保` 结果，并在 EvidencePack 中明确记录 `学费`、`城市`、`专业组最低位次` 等缺失字段没有执行。缺失字段不能从自然语言里补出来，也不能被回答层暗示为已经筛选。

uploaded admissions 推荐现在走 reviewed semantic 链路：DeepSeek 只提出候选 `SemanticIntent`，系统把专业、省份、位次等偏好 ground 到 reviewed mapping，再用 verified `QueryAST` 生成 DuckDB SQL 召回 bounded candidates。推荐请求先得到 verified SQL 候选集；只有存在 verified `RankingPlan` 时，系统才把候选集排序为推荐，否则回答会明确称为“候选列表”。LLM 可以提出 `RankingPlan` 和 rationale，但不能直接排序、不能新增候选 item，也不能引用 EvidencePack 之外的就业、城市发展、学校氛围等结论。`不想去国外` 这类偏好在缺少 `school_country_or_region` 字段时会进入 `not_executed_preferences`；只给分数没有位次时返回 `needs_confirmation`，不执行 SQL。

本地探针命令：

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx
.venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx --query "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
ENABLE_LLM=true .venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx --live-llm --query "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
```

## 怎么填写查询

主查询页默认只需要填这些：

- 生源地：例如“广东”。
- 科类：物理或历史。
- 省排位：建议必填；只给分数时，系统会要求补充广东省排位，不执行推荐 SQL。
- 选考科目：从化学、生物、政治、地理里选择。
- 意向专业和城市：例如“计算机”“广州、深圳”。
- 排位范围：只能选择后端白名单里的“冲一冲”“稳一点”或“保底”。
- 排序方式：必须选择后端白名单里的排序方式。
- 补充偏好：例如“学校稳一点，不想去太贵的中外合作”。

填好后点击“查看可筛结果”。

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

系统可以把家庭资源和就业目标结构化为补充问题与非执行证据，但在缺少已审查就业结果字段前，不会按“好就业”筛选或排序。

## LLM 能做什么

默认配置是：

```text
ENABLE_LLM=false
```

不配置 LLM 也可以使用 demo、上传数据、字段审核、DuckDB 查询、Quality Gate 和 tool server。

如果显式设置 `ENABLE_LLM=true` 并配置 `DEEPSEEK_API_KEY`，DeepSeek 只用于补齐 deterministic extractor 缺失的 slots、提出 schema-aware `SemanticIntent`、可选地在 bounded candidates 的 `row_id` 内 rerank，或基于证据解释结果。它不能生成 SQL，不能生成 hard rules，也不能绕过 `RuleVerifier`、reviewed mapping、确认回路、rerank validator 或 warehouse fingerprint guard。

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
| `cd frontend && npm run dev` | 启动前端开发服务。 |
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
| `frontend/` | Vue 3 前端工作台。 |
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
