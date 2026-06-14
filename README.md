# 偏好到规则验证工作台

本项目是一个面向广东高考志愿填报场景的研究工程项目，核心目标是验证“自然语言偏好”能否被安全地转换为可执行规则。当前工程形态已经包装为 `LLM-safe structured data query tool server for Excel/CSV`：LLM/agent/前端可以调用稳定 tool contracts，但不能绕过 schema grounding、RuleVerifier、confirmation loop 或 DuckDB fingerprint guard。它不是普通志愿推荐 bot，也不会把模糊偏好直接当作筛选条件执行。

项目关注的问题是：

- 哪些偏好可以被 schema 支持并转换成确定性规则；
- 哪些偏好需要用户确认后才能执行；
- 哪些偏好因为缺少字段、语义太模糊或需要外部信息而必须保留为不可执行项；
- 前端如何把抽取、字段接地、规则验证、执行结果和 trace 展示给用户。

## 当前形态

仓库包含一个 FastAPI 后端和一个 Vue 3 前端工作台：

- 后端运行现有验证管线，读取由广东志愿填报 Excel 构建出的本地 DuckDB 数据仓库，返回规则、结果、trace 和证据回答。
- 前端只可视化 mock 数据或后端 API 输出，不新增推荐逻辑，也不推断新规则。
- LLM 可以用于辅助抽取或基于证据回答，但执行权仍由基于 schema 接地的验证器控制。

主要目录：

| 路径 | 说明 |
|---|---|
| `src/` | 验证管线、规则、执行器、API 和报告生成代码 |
| `frontend/` | Vue 3 + Vite + Element Plus 前端工作台 |
| `domains/` | domain pack 配置：schema mapping、value aliases、rule taxonomy、排序、答案模板和 golden cases |
| `schemas/` | schema profile 和历史配置；运行时 schema 以 `domains/admissions/schema_registry.json` 为准 |
| `rules/` | 跨 domain 的规则生命周期、信息需求和模糊词参考配置 |
| `scripts/` | demo、评估、离线 schema profiling 和 domain pack auto-generator 脚本 |
| `schemas/tools/` | 面向 LLM/agent/前端的 functional tool contracts |
| `docs/` | 方法、评估和端到端 demo 文档 |
| `outputs/` | 已生成 demo 和 evaluation artifact |

## 本地环境

建议环境：

- Python 3.10+
- Node.js 18+
- npm

后端 demo 会读取仓库根目录下的 Excel 文件：

```text
广东省2025年志愿填报大数据（24-25）0523.xlsx
```

如果这个文件不存在，API 模式和 MVP demo 不能正常执行。

API 模式还需要先构建本地结构化数据仓库：

```bash
source .venv/bin/activate
python scripts/build_data_warehouse.py
```

该脚本会生成：

- `outputs/data/guangdong_admissions.duckdb`：本地 DuckDB 数据仓库，默认不提交。
- `outputs/data/schema_value_index.json`：schema/value index，用于字段值审计。
- `outputs/data/ingestion_summary.json`：ingestion summary，记录 source path、fingerprint、row/column count、field profiles 和 created_at。

Workbench API 每次执行前都会校验 DuckDB metadata、schema/value index metadata 和源 Excel fingerprint 是否一致；不一致时返回结构化 warning，不会静默回退到 raw Excel/Pandas 执行。

当前默认 domain 是 `domains/admissions/`。招生字段名、字段别名、值别名、规则分类、排序策略、`top_results` 映射、答案模板和 golden cases 都由该 domain pack 提供；Workbench、AttributeGrounder、RuleVerifier 和 DuckDBExecutor 只通过 `DomainConfig` 读取 canonical fields。仓库还包含 `domains/housing/` 和 `domains/products/` toy fixture，用单元测试验证同一套符号管线可以切换 domain 运行。项目没有接入 Qwen、BGE 或向量库；结构化招生表继续使用 DuckDB 与 schema/value index。

可以用 auto-generator 从 CSV/Excel 生成 draft domain pack：

```bash
source .venv/bin/activate
python scripts/generate_domain_pack.py path/to/source.csv products
```

生成器会在 `domains/<domain>/` 下输出 `domain.yaml`、`schema_mapping.yaml`、`rule_taxonomy.seed.yaml`、`extraction_aliases.seed.json`、`top_result_mapping.yaml`、`sort_policy.seed.yaml`、`answer_templates.seed.md`、`golden_cases.seed.yaml`，并复用 warehouse ingestion 生成 `<domain>.duckdb`、`schema_profile.json`、`schema_value_index.json` 和 `ingestion_summary.json`。所有自动配置都是 `draft` 或 `needs_review`，默认不会给字段写入可执行 `allowed_ops`。`--llm off` 是默认值；`--llm deepseek` 只发送 schema profile 和少量脱敏样例，输出也只能作为候选 aliases/templates，不能直接进入 hard rules。

正式接入新 CSV/Excel 必须走 review/approval workflow，不能直接把 generator seed 当作生产配置：

```bash
python scripts/review_domain_pack.py summarize domains/<domain>
python scripts/review_domain_pack.py validate domains/<domain>
python scripts/review_domain_pack.py approve-field domains/<domain> city --write
python scripts/review_domain_pack.py approve-op domains/<domain> city in --write
python scripts/review_domain_pack.py approve-domain domains/<domain> \
  --title-field listing_id \
  --primary-field city \
  --primary-field rent_usd \
  --sort-field rent_usd \
  --write
python scripts/review_domain_pack.py report domains/<domain> --write
python scripts/run_demo_acceptance.py
python scripts/run_real_dataset_pilot.py path/to/admissions.xlsx
python scripts/run_quality_gate.py
```

`review_domain_pack.py` 默认 dry-run，只有显式 `--write` 才会写入 `review.yaml`、runtime schema、rule taxonomy、attribute grounding、`top_result_mapping.yaml` 和 domain status。PII、高基数字段、自由文本 contains/keyword filter、未通过数值范围 sanity check 的字段都不能自动 approve。`draft` / `needs_review` pack 即使已有 seed candidate ops，也会在 Workbench 中返回 `blocked`，不执行 SQL；只有 `approved` pack 才能进入 demo acceptance、quality gate 和生产使用。`run_quality_gate.py` 会统一运行 Python 语法检查、unit tests、regex evaluator、临时 demo acceptance、domain pack validate、warehouse fingerprint guard、前端 build 和生成产物一致性检查，并输出到 `outputs/quality_gate/tmp/latest/`。

后端现在也提供 uploaded dataset 产品流，把上述 CLI 能力接成 API/service：

```text
uploaded
-> profiled
-> draft_domain_generated
-> needs_review
-> approved
-> warehouse_ready
-> queryable
```

核心 endpoint 包括 `POST /datasets/upload`、`POST /datasets/{dataset_id}/generate-domain-pack`、`GET /datasets/{dataset_id}/profile`、`GET /datasets/{dataset_id}/review-summary`、`POST /datasets/{dataset_id}/approve-field`、`POST /datasets/{dataset_id}/approve-op`、`POST /datasets/{dataset_id}/block-field`、`POST /datasets/{dataset_id}/approve-domain`、`POST /datasets/{dataset_id}/build-warehouse` 和 `POST /workbench/query`。上传文件保存在 `outputs/uploaded_datasets/<dataset_id>/`，不会覆盖内置 `admissions`、`housing`、`products` domain pack。Excel ingestion 会返回 sheet list、默认选中的非空 sheet、detected header row、重复列安全映射、合并单元格/隐藏行列/公式单元格 warning，以及行列规模 warning/error。未 approved 的 pack、stale warehouse fingerprint、非法 `dataset_id` 或缺失 warehouse 都返回结构化 `blocked` / error，不执行 SQL。前端“上传数据集接入流程”面板只调用这些 API，并展示 profile、review summary、required/missing/risky fields、`items`、`top_results`、`result_sections`、`EvidencePack`、warnings、blocked/no_results 状态、candidate confirmation 交互和前端操作审计记录，不在前端生成推荐逻辑。

真实招生 Excel 上线前可以先跑 pilot：

```bash
python scripts/run_real_dataset_pilot.py path/to/admissions.xlsx
```

该脚本会执行 upload -> profile -> generate draft domain pack -> review summary -> safe auto-suggest approvals -> manual approval fixture -> build warehouse -> target admissions queries，并输出 `outputs/real_dataset_pilot/report.md` 与 `outputs/real_dataset_pilot/report.json`。没有真实文件时可用 `--fixture` 运行内置 real-like admissions fixture。详见 [Real Dataset Pilot](docs/real_dataset_pilot.md)。

面向 operator 的真实 Excel 试运行可以使用：

```bash
python scripts/run_operator_trial.py path/to/admissions.xlsx
make operator-trial
```

报告输出到 `outputs/operator_trial/<run_id>/report.md` 与 `report.json`，重点记录 sheet/header/profile/review/approve/build/query 每一步的操作卡点、`manual_checkpoints`、常见失败处理、missing/risky fields、warnings 和 failures。详见 [Operator Trial Checklist](docs/operator_trial_checklist.md) 和 [Operator Feedback Template](docs/operator_feedback_template.md)。

Workbench API 响应已经固定为 multi-domain `WorkbenchResponse` contract。前端应依赖 `schema_version`、`domain`、`domain_version`、`domain_pack_status`、`status`、`query_type`、`query`、`answer`、`items`、`top_results`、`result_sections`、`result_count`、`executed_filters`、`candidates_to_confirm`、`confirmed_rules`、`unconfirmed_candidates`、`unexecuted_preferences`、`no_schema_field_preferences`、`rejected_confirmations`、`warnings`、`evidence_pack` 和 `debug_trace`。`status` 只能是 `ok`、`needs_confirmation`、`no_results`、`blocked`、`error`；`items` 是跨领域稳定 item card，`top_results` 只作为 domain-specific 兼容层，由 `domains/<domain>/top_result_mapping.yaml` 生成。admissions 额外支持 `group_detail_report` 和 `recommendation` 两类 `query_type`，通过 `result_sections` 返回专业组明细或冲/稳/保分组。`recommendation` 的 `EvidencePack.execution_summary` 会记录 `score_margin` / `rank_margin`、专业匹配来源、bucket 计数和当前 `latest_available_year` 策略；这些字段只解释历史最低分/最低位次分组，不代表录取概率，也不会绕过已审核字段和 confirmation loop。招生 domain 还可以在 `EvidencePack.policy_references` 中返回已审核 Markdown 资料的 lexical 命中，用于解释中外合作、专项计划或选科要求等背景；这些引用只作为 `reference_only`，不会改变 SQL、`result_count` 或推荐分组。draft/needs_review domain pack 默认返回 `blocked`，不执行 SQL。详见 [Workbench API 响应契约](docs/api_contract.md)。

Workbench 还支持 candidate_id confirmation loop：

- 第一次运行时，`partial_match` 偏好会出现在 contract 字段 `candidates_to_confirm` 中，不会进入 hard filter；旧调试结构中仍保留 `confirmation_candidates`。
- 用户确认时只能提交上一轮响应里的 `candidate_id`，不能提交新的文本条件。
- 后端会按当前 query 重新生成候选并校验 `candidate_id`；伪造、过期或不属于当前 query 的 id 会被拒绝。
- 确认通过后，系统只把该 candidate 对应的已审查字段和值编译成参数化 DuckDB SQL。
- `no_schema_field` 偏好即使被提交确认也不会执行，只会保留在证据包中解释。

LLM/agent/前端可通过 functional tool layer 调用现有能力：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

这些是唯一 LLM-safe tools。`dataset.upload`、`dataset.generate_domain_pack`、`approve-*`、`build-warehouse`、`quality.run` 和 `pilot.run` 都是写入或管理类工具，需要对应权限，不能自动暴露给 LLM。HTTP 权限只来自服务端 `AUTH_TOKENS_JSON` token 映射，不信任浏览器或 LLM 传入的 `permission_scopes`；`dataset.upload` tool 只接受 `content_base64`，不读取服务端 `source_path`。tool registry 位于 `src/api/tool_registry.py`，机器可读契约位于 `schemas/tools/*.json`。HTTP 包装层提供 `GET /tools/list`、`GET /tools/{tool_name}/schema`、`POST /tools/{tool_name}/invoke`、`GET /healthz`、`GET /readyz` 和 `GET /version`。使用指南见 [功能工具契约](docs/tool_contract.md)、[Agent 使用指南](docs/agent_usage_guide.md)、[本地部署说明](docs/local_deployment.md)、[Operator 操作指南](docs/operator_guide.md)、[生产部署说明](docs/production_deployment.md)、[安全模型](docs/security_model.md)、[备份与恢复](docs/backup_restore.md) 和 [故障排查](docs/troubleshooting.md)。

发布前可以导出接入契约：

```bash
.venv/bin/python scripts/export_openapi.py
.venv/bin/python scripts/export_tool_manifest.py
.venv/bin/python scripts/export_openai_tools.py
```

输出分别位于 `outputs/openapi/openapi.json`、`outputs/tool_manifest/tool_manifest.json` 和 `outputs/tool_manifest/openai_tools.json`。OpenAI-compatible tools 和 MCP adapter 默认只暴露五个 LLM-safe tools；admin tools 默认不可见、不可调用。

可以用 fake agent 黑盒验收工具调用链：

```bash
make agent-acceptance
```

该脚本验证 list/profile/review/query/confirm/evidence 和 admin 权限拒绝，并输出 `outputs/agent_tool_acceptance/report.md` 与 `report.json`。

Release demo package 包含：

- `release_manifest.json`：固定发布入口、契约版本、sample data、sample outputs 和安全不变量。
- `sample_data/`：脱敏 admissions CSV、housing/products toy CSV 和说明。
- `sample_outputs/`：精简 WorkbenchResponse、Quality Gate 和 operator trial 输出示例。
- `CHANGELOG.md`、`RELEASE_CHECKLIST.md`、`docs/demo_script.md`：发布说明、检查清单和演示脚本。

发布包静态校验：

```bash
make release-check
```

## 启动后端

推荐用 Makefile 创建环境并安装依赖：

```bash
make bootstrap
```

创建本地环境变量文件：

```bash
cp .env.example .env
```

`.env.example` 默认保持：

```text
ENABLE_LLM=false
AUTH_TOKENS_JSON=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
TOOL_AUDIT_LOG_PATH=outputs/tool_audit/audit.jsonl
TOOL_AUDIT_MAX_BYTES=5242880
TOOL_AUDIT_BACKUPS=5
```

只使用前端 demo 模式、regex 抽取、模板证据回答、uploaded dataset、Quality Gate 或 tool server 时不需要 DeepSeek key；只有显式设置 `ENABLE_LLM=true` 并配置 `DEEPSEEK_API_KEY` 时，Workbench 才会调用 DeepSeek slot adapter。生产路径中的 DeepSeek 只补 deterministic extractor 缺失的 slots，不覆盖已抽取字段，不生成 SQL，不返回 hard rules 或 executable rules。

本地验证 DeepSeek slot adapter：

```bash
ENABLE_LLM=true .venv/bin/python scripts/run_deepseek_slot_probe.py
```

输出只包含 `fallback_extraction`、`llm_slot_adapter`、token usage、抽取摘要和执行摘要，不会打印密钥或完整 prompt。

启动 FastAPI：

```bash
make serve
```

检查后端健康、就绪和版本：

```bash
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
```

`/readyz` 会检查 data root 可写、tool schemas 可加载、内置 DomainConfig 可加载和 Quality Gate 基础依赖存在。

旧的 `/health` endpoint 仍保留为兼容入口。

## 启动前端

另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

Vite 已配置把 `/api` 代理到 `http://127.0.0.1:8001`。如果只看 demo 模式，前端可以不启动后端；如果切到 API 模式，需要后端正在运行。
上传数据集面板还会调用 `/datasets` 和 `/workbench`，同样由 Vite 代理到后端。

## 如何测试工作台

1. 打开 `http://127.0.0.1:5173`。
2. 先保持 demo 模式，点击“运行规则验证”，检查页面是否展示偏好解析、字段接地、规则审查、候选规则、不可执行偏好、筛选结果和 trace。
3. 启动后端后切换到 API 模式，再次运行默认输入：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

4. 检查页面是否明确展示“中外合作”未执行，因为当前 schema 缺少合作办学类型字段。
5. 如果选择 LLM 辅助解析或 LLM 证据回答，确认 `.env` 已配置 DeepSeek key，并观察页面 token 用量面板。

## 本地验证命令

构建本地 DuckDB 数据仓库和 schema/value index：

```bash
python scripts/build_data_warehouse.py
```

运行单元测试：

```bash
python3 -m unittest discover -s tests
```

运行 MVP demo：

```bash
python3 scripts/run_mvp_demo.py
```

`outputs/mvp_demo/` 和 `outputs/answer_demo/` 是本地可重建的旧演示产物，默认不再入库。当前交付验收以 `make demo`、`make pilot`、`make quality` 和 tool server contracts 为准。

运行快速 regex-only 评估：

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

后续路线见 [下一阶段路线](docs/next_route.md)。当前主线已经先适配 DeepSeek slot adapter，但默认仍关闭；后续继续优先做 production hardening、operator trial 和 release readiness，暂不接 OpenAI-compatible local endpoint、Qwen/vLLM、BGE 或向量库。

运行真实数据集 pilot fixture：

```bash
make pilot
```

运行 operator trial fixture：

```bash
make operator-trial
```

校验 release package：

```bash
make release-check
```

运行统一质量门禁：

```bash
make quality
```

构建前端：

```bash
make frontend
```

可选 DeepSeek-backed 评估：

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
python3 scripts/eval_fuzzy_inputs.py --methods all
```

DeepSeek-backed 评估会读取 `.env`，并可能产生 API 延迟和 token 消耗。

## 相关文档

- [方法报告](docs/methodology_report.md)
- [Workbench API 响应契约](docs/api_contract.md)
- [功能工具契约](docs/tool_contract.md)
- [Agent 使用指南](docs/agent_usage_guide.md)
- [演示脚本](docs/demo_script.md)
- [本地部署说明](docs/local_deployment.md)
- [Operator 操作指南](docs/operator_guide.md)
- [故障排查](docs/troubleshooting.md)
- [Real Dataset Pilot](docs/real_dataset_pilot.md)
- [Operator Trial Checklist](docs/operator_trial_checklist.md)
- [Operator Feedback Template](docs/operator_feedback_template.md)
- [发布检查清单](RELEASE_CHECKLIST.md)
- [变更日志](CHANGELOG.md)
- [评估报告](docs/evaluation_report.md)
- [端到端 demo 用例](docs/end_to_end_demo_cases.md)
- [Excel schema profile](docs/excel_schema_profile.md)
- [完整项目计划](docs/full_project_plan.md)
