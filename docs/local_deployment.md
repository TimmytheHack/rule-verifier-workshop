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
| `UPLOAD_MAX_MB` | 单个上传文件大小上限，默认 `25`。 |
| `ENABLE_LLM` | 是否允许可选 LLM 辅助生成，默认 `false`。 |
| `DEEPSEEK_API_KEY` | 可选 DeepSeek key；默认留空。 |
| `TOOL_AUDIT_LOG_PATH` | tool invoke audit JSONL 路径。 |
| `FRONTEND_ORIGIN` | 允许的前端 origin，逗号分隔。 |
| `LOG_LEVEL` | 服务日志级别。 |

## 启动服务

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

`POST /tools/{tool_name}/invoke` 请求体：

```json
{
  "payload": {},
  "actor_context": {
    "actor_id": "operator",
    "permission_scopes": ["query"],
    "dataset_root": "outputs/uploaded_datasets",
    "audit_path": "outputs/tool_audit/audit.jsonl"
  }
}
```

也可以通过 HTTP headers 传递：

```text
X-Actor-Id: operator
X-Permission-Scopes: query,read_only
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
make quality
```

该命令运行统一 Quality Gate，并生成：

```text
outputs/quality_gate/report.md
outputs/quality_gate/report.json
```

常用辅助命令：

```bash
make test
make demo
make agent-acceptance
make pilot
make frontend
make clean-artifacts
```

`make clean-artifacts` 只清理临时 audit、临时 gate warehouse 和临时导出产物，不删除正式报告。
