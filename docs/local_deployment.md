# 本地部署说明

本项目发布形态是 `LLM-safe structured data query tool server for Excel/CSV`。部署目标是让前端、LLM/agent 和 operator 都通过同一套 FastAPI / ToolRegistry / DatasetService / Workbench contract 接入，不绕过 schema grounding、RuleVerifier、confirmation loop 或 DuckDB fingerprint guard。

## 环境准备

建议使用仓库根目录的 `Makefile`：

```bash
make bootstrap
```

该命令会创建或复用 `.venv`，并安装 `requirements.txt`。如果不使用 Makefile，也可以手动执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

复制环境变量样例：

```bash
cp .env.example .env
```

默认配置保持 `ENABLE_LLM=false`。只跑 schema profiling、review、DuckDB 查询、demo acceptance、quality gate 和 tool server 时不需要 DeepSeek key。

## 关键环境变量

| 变量 | 含义 |
|---|---|
| `DATA_ROOT` | uploaded dataset 托管目录，默认 `outputs/uploaded_datasets`。 |
| `OUTPUT_ROOT` | 报告、audit、manifest 等输出根目录，默认 `outputs`。 |
| `AUTH_TOKENS_JSON` | HTTP 鉴权 token 映射，生产环境必须配置。 |
| `UPLOAD_MAX_MB` | 单个上传文件大小上限，默认 `25`。 |
| `ENABLE_LLM` | 是否允许可选 LLM 辅助生成，默认 `false`。 |
| `DEEPSEEK_API_KEY` | 可选 DeepSeek key；默认留空。 |
| `DEEPSEEK_MODEL` | DeepSeek 模型名，默认 `deepseek-chat`。 |
| `DEEPSEEK_API_URL` | DeepSeek OpenAI-compatible chat completions URL。 |
| `TOOL_AUDIT_LOG_PATH` | tool invoke audit JSONL 路径。 |
| `TOOL_AUDIT_MAX_BYTES` | 单个 audit JSONL 文件最大字节数，超过后轮转。 |
| `TOOL_AUDIT_BACKUPS` | audit log 保留的轮转备份数量。 |
| `FRONTEND_ORIGIN` | 允许的前端 origin，逗号分隔。 |
| `FRONTEND_USER_DIST` | 本地用户 Web 静态构建目录，默认 `frontend-user/dist`。 |
| `LOCAL_USER_AUTO_AUTH_TOKEN` | 本地同端口用户 Web 自动登录 cookie 使用的 token；必须同时存在于 `AUTH_TOKENS_JSON`。生产默认不应启用。 |
| `LOG_LEVEL` | 服务日志级别。 |

DeepSeek slot adapter 默认不启用。需要验证真实 API 时，确认 `.env` 中存在
`ENABLE_LLM=true` 和 `DEEPSEEK_API_KEY`，然后运行：

```bash
.venv/bin/python scripts/run_deepseek_slot_probe.py
```

该脚本只输出 fallback/adapter/token 使用摘要，不输出密钥或完整 prompt。

对 uploaded admissions 查询，`planner_mode=auto` 会在 `ENABLE_LLM=true` 且 DeepSeek 可用时先尝试
`DeepSeekSemanticIntentExtractor`；不可用时会降级到 legacy verified planner，并在
`EvidencePack.planner` 记录降级原因。需要强制跳过 LLM planner 时，API 或 probe 可传
`planner_mode=legacy`。

## 启动服务

普通用户本机入口建议使用：

```bash
make serve-user
```

该命令会先构建 `frontend-user/dist`，再以 `APP_DISTRIBUTION_MODE=user_upload_only` 启动 FastAPI，并在 `http://127.0.0.1:8001` 同端口托管本地用户 Web 和 API。用户不需要再单独启动 Vite 前端。
本机未设置 `AUTH_TOKENS_JSON` 时，`make serve-user` 会使用仓库的开发 token，并设置 HttpOnly `actor_token` cookie 供同端口页面访问 API。生产或多人环境必须换成真实 token；只有明确需要本机单用户自动登录时，才设置 `LOCAL_USER_AUTO_AUTH_TOKEN`。

只启动后端 API 时使用：

```bash
make serve
```

等价于：

```bash
.venv/bin/python -m uvicorn src.api.server:app --reload --port 8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
```

`/readyz` 会检查 data root 可写、tool schemas 可加载、内置 DomainConfig 可加载、Quality Gate 基础依赖存在。它不是完整测试；发布前仍必须跑 `make quality`。

## Tool Server 入口

| endpoint | 含义 |
|---|---|
| `GET /tools/list` | 按 actor permission 和 `llm_safe_only` 列出可见 tools。 |
| `GET /tools/{tool_name}/schema` | 返回单个 tool contract。 |
| `POST /tools/{tool_name}/invoke` | 调用 ToolRegistry，写入 audit event。 |
| `GET /openapi.json` | FastAPI 内置 OpenAPI。 |

HTTP 权限只来自服务端 `AUTH_TOKENS_JSON` token 映射。开发环境可以先配置：

```bash
export AUTH_TOKENS_JSON='{"operator-token":{"actor_id":"operator","permission_scopes":["read_only","query","confirm","dataset_write","review_admin","warehouse_admin","diagnostics"]},"agent-token":{"actor_id":"agent","permission_scopes":["read_only","query","confirm"]}}'
```

`make serve` 在本地未设置 `AUTH_TOKENS_JSON` 时会自动使用上述开发 token。本地 Vite 开发模式会默认发送 `operator-token`，只用于配合 `make serve` 的本机演示。生产部署不得接受示例 token，必须通过服务端 `AUTH_TOKENS_JSON` 配置真实 token，并在网关或运维系统中控制 operator token 的分发。生产构建不会内置默认 token，必须由真实登录态、网关或部署环境注入。

请求通过 `Authorization: Bearer <token>` 或 `X-Actor-Token: <token>` 传递 token。服务端不信任浏览器或请求体传来的 `permission_scopes`、`actor_id`、`audit_path` 或 `dataset_root`。

普通用户在“导入数据”上传招生 Excel/CSV 并点击一键导入；`approve` 和 `build` 是后端流水线内部步骤，
不要求用户手动进入字段审查。导入成功后，前端会把最近可查询的 uploaded admissions `dataset_id`
保存在浏览器本地状态，并在主查询页作为数据源使用。清理 `DATA_ROOT`、更换本地数据目录或重启到空目录后，
需要在前端切回内置 admissions，或在“导入数据”重新上传并一键导入。只有字段模板不匹配或导入失败时，
才进入“字段审查”处理高级审查信息。

`POST /tools/{tool_name}/invoke` 请求体：

```json
{
  "payload": {}
}
```

HTTP header：

```text
Authorization: Bearer agent-token
```

LLM/agent 默认只应看到 `llm_safe_only=true` 的工具：`dataset.profile`、`dataset.review_summary`、`workbench.query`、`workbench.confirm`、`evidence.get`。

## 导出契约

```bash
.venv/bin/python scripts/export_openapi.py
.venv/bin/python scripts/export_tool_manifest.py
.venv/bin/python scripts/export_openai_tools.py
```

输出：

```text
outputs/openapi/openapi.json
outputs/tool_manifest/tool_manifest.json
outputs/tool_manifest/openai_tools.json
```

tool manifest 会标记每个 tool 的 `permission_scope`、`llm_safe`、`side_effects`、`executes_sql` 和 `writes_files`，供前端、agent 网关或 operator 控制台读取。

OpenAI-compatible tools 和 MCP adapter 默认只暴露 LLM-safe tools。黑盒验收命令：

```bash
make agent-acceptance
```

输出：

```text
outputs/agent_tool_acceptance/report.md
outputs/agent_tool_acceptance/report.json
```

## 发布前检查

```bash
make release-check
make demo
make agent-acceptance
make pilot
make operator-trial
make quality
```

`make release-check` 会校验 `release_manifest.json`、`sample_data/`、`sample_outputs/`、发布文档和关键 Makefile 入口。`make quality` 会运行统一 Quality Gate，并生成临时报告：

```text
outputs/quality_gate/tmp/latest/report.md
outputs/quality_gate/tmp/latest/report.json
```

常用辅助命令：

```bash
make test
make demo
make agent-acceptance
make pilot
make operator-trial
make release-check
make frontend
make clean-artifacts
```

`make clean-artifacts` 会清理临时 audit、临时 gate warehouse、临时 Quality Gate 报告和临时导出产物，不删除正式发布样例。

## Operator Trial

真实招生 Excel 进入生产前，operator 可以先跑一次人工试运行：

```bash
.venv/bin/python scripts/run_operator_trial.py path/to/admissions.xlsx
```

没有真实文件时可以使用内置 fixture：

```bash
make operator-trial
```

输出位于：

```text
outputs/operator_trial/<run_id>/report.md
outputs/operator_trial/<run_id>/report.json
```

该报告面向人工审查，重点记录 sheet/header/profile/review/approve/build/query 每一步的 `operation_cards`、`manual_checkpoints`、`failure_playbook`、missing fields、risky fields、warnings 和 failures。通过 operator trial 不会绕过 domain review；正式发布仍需继续运行 demo acceptance、real dataset pilot 和 Quality Gate。
