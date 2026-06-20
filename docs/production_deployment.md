# 生产部署说明

本文说明 `LLM-safe structured data query tool server for Excel/CSV` 的生产部署方式。生产环境必须让所有写入、审批、入仓和查询请求经过后端鉴权，不得信任浏览器或 LLM payload 中的 `permission_scopes`。

## 容器部署

构建镜像：

```bash
docker build -t szu-preference-rule-server:local .
```

使用 compose 启动：

```bash
export AUTH_TOKENS_JSON='{"operator-token":{"actor_id":"operator","permission_scopes":["read_only","query","confirm","dataset_write","review_admin","warehouse_admin","diagnostics"]},"agent-token":{"actor_id":"agent","permission_scopes":["read_only","query","confirm"]}}'
docker compose up --build
```

健康检查：

```bash
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
```

## 持久化目录

默认容器内路径：

| 路径 | 用途 |
|---|---|
| `/data/uploaded_datasets` | 上传文件、dataset metadata、domain pack、uploaded warehouse。 |
| `/data/outputs` | tool audit、临时报告、导出产物。 |
| `/data/outputs/tool_audit/audit.jsonl` | tool invocation audit log。 |

生产部署必须把 `/data` 挂载到持久卷。不要把 `.env`、DeepSeek key、原始大表或 DuckDB 本地文件提交进版本库。

## 鉴权配置

HTTP 层只读取以下认证材料：

- `Authorization: Bearer <token>`
- `X-Actor-Token: <token>`
- `actor_token` cookie

token 到 actor 和权限的映射只来自服务端环境变量 `AUTH_TOKENS_JSON`。示例：

```json
{
  "operator-token": {
    "actor_id": "operator",
    "permission_scopes": ["read_only", "query", "confirm", "dataset_write", "review_admin", "warehouse_admin", "diagnostics"]
  },
  "agent-token": {
    "actor_id": "agent",
    "permission_scopes": ["read_only", "query", "confirm"]
  }
}
```

HTTP 请求体里的 `actor_context.permission_scopes`、`actor_context.audit_path`、`X-Permission-Scopes` 和 `X-Actor-Id` 不再授予权限。它们只能作为旧客户端兼容字段存在，不能影响服务端授权。

本地 Vite 开发模式会默认发送 `operator-token`，只用于配合 `make serve` 的本机演示。生产部署不得接受示例 token，必须通过服务端 `AUTH_TOKENS_JSON` 配置真实 token，并在网关或运维系统中控制 operator token 的分发。

## 上传与入仓

- `/datasets/upload` 使用 HTTP body 上传 CSV/Excel。
- `dataset.upload` tool 只接受 `content_base64`，默认不允许服务端读取 `source_path`。
- `dataset.build_warehouse` 对每个 `dataset_id` 加文件锁，构建到临时 DuckDB/index 后再原子替换正式文件。
- Workbench query 在执行前仍会校验 DuckDB metadata、schema/value index 和源文件 fingerprint，一致性失败时返回 `blocked`，不执行 SQL。

## Audit Log

audit log 路径由服务端 `TOOL_AUDIT_LOG_PATH` 固定，默认位于 `OUTPUT_ROOT/tool_audit/audit.jsonl`。运行时会：

- 使用文件锁串行写入；
- 按 `TOOL_AUDIT_MAX_BYTES` 轮转；
- 保留 `TOOL_AUDIT_BACKUPS` 个历史文件；
- 净化 secret、stack trace 和本机绝对路径。

## 发布检查

候选发布前运行：

```bash
make release-check
make demo
make agent-acceptance
make pilot
make operator-trial
make quality
```

`make quality` 的临时报告写入 `outputs/quality_gate/tmp/latest/`，不会更新 tracked release evidence。如果需要更新正式 demo acceptance evidence，请显式运行 `make demo` 并审查 diff。
