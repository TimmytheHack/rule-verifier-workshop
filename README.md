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
| `schemas/` | 已审查 schema registry 和 schema profile |
| `rules/` | 规则生命周期、分类和模糊词配置 |
| `scripts/` | demo、评估和离线 schema profiling 脚本 |
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
- [评估报告](docs/evaluation_report.md)
- [端到端 demo 用例](docs/end_to_end_demo_cases.md)
- [Excel schema profile](docs/excel_schema_profile.md)
- [完整项目计划](docs/full_project_plan.md)
