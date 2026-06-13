# 偏好到规则验证工作台

本项目是一个面向广东高考志愿填报场景的研究工程项目，核心目标是验证“自然语言偏好”能否被安全地转换为可执行规则。它不是普通志愿推荐 bot，也不会把模糊偏好直接当作筛选条件执行。

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
```

`review_domain_pack.py` 默认 dry-run，只有显式 `--write` 才会写入 `review.yaml`、runtime schema、rule taxonomy、attribute grounding、`top_result_mapping.yaml` 和 domain status。PII、高基数字段、自由文本 contains/keyword filter、未通过数值范围 sanity check 的字段都不能自动 approve。`draft` / `needs_review` pack 即使已有 seed candidate ops，也会在 Workbench 中返回 `blocked`，不执行 SQL；只有 `approved` pack 才能进入 demo acceptance 和生产使用。

Workbench API 响应已经固定为 multi-domain `WorkbenchResponse` contract。前端应依赖 `schema_version`、`domain`、`domain_version`、`domain_pack_status`、`status`、`query`、`answer`、`items`、`top_results`、`result_count`、`executed_filters`、`candidates_to_confirm`、`confirmed_rules`、`unconfirmed_candidates`、`unexecuted_preferences`、`no_schema_field_preferences`、`rejected_confirmations`、`warnings`、`evidence_pack` 和 `debug_trace`。`status` 只能是 `ok`、`needs_confirmation`、`no_results`、`blocked`、`error`；`items` 是跨领域稳定 item card，`top_results` 只作为 domain-specific 兼容层，由 `domains/<domain>/top_result_mapping.yaml` 生成。draft/needs_review domain pack 默认返回 `blocked`，不执行 SQL。详见 [Workbench API 响应契约](docs/api_contract.md)。

Workbench 还支持 candidate_id confirmation loop：

- 第一次运行时，`partial_match` 偏好会出现在 contract 字段 `candidates_to_confirm` 中，不会进入 hard filter；旧调试结构中仍保留 `confirmation_candidates`。
- 用户确认时只能提交上一轮响应里的 `candidate_id`，不能提交新的文本条件。
- 后端会按当前 query 重新生成候选并校验 `candidate_id`；伪造、过期或不属于当前 query 的 id 会被拒绝。
- 确认通过后，系统只把该 candidate 对应的已审查字段和值编译成参数化 DuckDB SQL。
- `no_schema_field` 偏好即使被提交确认也不会执行，只会保留在证据包中解释。

## 启动后端

在仓库根目录创建并启用 Python 虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

创建本地环境变量文件：

```bash
cp .env.example .env
```

`.env` 里需要配置：

```text
DEEPSEEK_API_KEY=replace_with_your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat
```

只使用前端 demo 模式、regex 抽取或模板证据回答时不需要 DeepSeek key；选择 LLM 辅助抽取或 LLM 证据回答时需要有效 key。

启动 FastAPI：

```bash
source .venv/bin/activate
python -m uvicorn src.api.server:app --reload --port 8001
```

检查后端健康状态：

```bash
curl http://127.0.0.1:8001/health
```

预期返回：

```json
{"status":"ok"}
```

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

运行快速 regex-only 评估：

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

构建前端：

```bash
cd frontend
npm run build
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
- [评估报告](docs/evaluation_report.md)
- [端到端 demo 用例](docs/end_to_end_demo_cases.md)
- [Excel schema profile](docs/excel_schema_profile.md)
- [完整项目计划](docs/full_project_plan.md)
