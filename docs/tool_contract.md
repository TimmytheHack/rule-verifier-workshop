# 功能工具契约

本项目现在对外暴露为：

```text
LLM-safe structured data query tool server for Excel/CSV
```

tool layer 的职责是把现有 `DatasetService`、Workbench、EvidencePack、Quality Gate 和 Real Dataset Pilot 组合成稳定 callable registry。它不复制业务逻辑，不绕过 `DomainConfig`、`RuleVerifier`、confirmation loop、DuckDB fingerprint guard 或 `WorkbenchResponse` contract。

机器可读 contract 位于：

```text
schemas/tools/*.json
```

运行时 registry 位于：

```text
src/api/tool_registry.py
```

HTTP 发布入口位于：

```text
GET /tools/list
GET /tools/{tool_name}/schema
POST /tools/{tool_name}/invoke
```

服务版本入口：

```text
GET /healthz
GET /readyz
GET /version
```

`/version` 当前返回 `api_version=api.v1`、`schema_version=workbench_response.v1` 和 `tool_contract_version=tools.v1`。

## 权限范围

| permission_scope | 含义 |
|---|---|
| `read_only` | 只读 profile、review summary 或 evidence。 |
| `query` | 运行 `workbench.query`。 |
| `confirm` | 用上一轮系统生成的 `candidate_id` 调用 `workbench.confirm`。 |
| `dataset_write` | 上传数据或生成 draft domain pack。 |
| `review_admin` | approve/block 字段、op 或 domain。 |
| `warehouse_admin` | 构建 DuckDB warehouse 和 schema/value index。 |
| `diagnostics` | 运行 quality gate 或 real dataset pilot。 |

## LLM-safe 工具

只有以下 tool 可标记为 LLM-safe：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

LLM-facing input schema 禁止出现可绕过 verifier 的字段名：

```text
raw_sql
sql
executable_rules
hard_rules
approved_ops
domain_pack_status
```

`workbench.query` 只接受 `dataset_id`、`domain`、`deterministic_fields`、`natural_language`、`confirmed_candidate_ids`、`top_k`。自然语言只能提出候选偏好，是否执行仍由 schema grounding、RuleVerifier 和 confirmation loop 决定。

`workbench.confirm` 不接受新的用户自由文本。它必须接收上一轮 `WorkbenchResponse` 和 `confirmed_candidate_ids`，从上一轮 `query.text` 重跑同一 query。伪造、过期或不属于当前 query 的 `candidate_id` 会返回 `blocked` / `rejected_confirmations`。

## 工具一览

| tool | permission_scope | LLM-safe | executes_sql | writes_files | required_domain_status |
|---|---|---:|---:|---:|---|
| `dataset.upload` | `dataset_write` | 否 | 否 | 是 | `none` |
| `dataset.profile` | `read_only` | 是 | 否 | 否 | `draft_or_later` |
| `dataset.generate_domain_pack` | `dataset_write` | 否 | 否 | 是 | `uploaded` |
| `dataset.review_summary` | `read_only` | 是 | 否 | 否 | `draft_or_later` |
| `dataset.approve_field` | `review_admin` | 否 | 否 | 是 | `needs_review` |
| `dataset.approve_op` | `review_admin` | 否 | 否 | 是 | `needs_review` |
| `dataset.block_field` | `review_admin` | 否 | 否 | 是 | `needs_review` |
| `dataset.approve_domain` | `review_admin` | 否 | 否 | 是 | `needs_review` |
| `dataset.build_warehouse` | `warehouse_admin` | 否 | 是 | 是 | `approved` |
| `workbench.query` | `query` | 是 | 是 | 否 | `approved_and_warehouse_ready` |
| `workbench.confirm` | `confirm` | 是 | 是 | 否 | `approved_and_warehouse_ready` |
| `evidence.get` | `read_only` | 是 | 否 | 否 | `none` |
| `quality.run` | `diagnostics` | 否 | 是 | 是 | `none` |
| `pilot.run` | `diagnostics` | 否 | 是 | 是 | `none` |

## 通用 contract 字段

每个 `schemas/tools/*.json` 都包含：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `permission_scope`
- `side_effects`
- `required_domain_status`
- `executes_sql`
- `writes_files`
- `security_notes`
- `status_enum`
- `examples`

所有 output 必须符合已有 contract：

- dataset tools 返回 `DatasetService` / review workflow 的结构化响应。
- `workbench.query` 和 `workbench.confirm` 返回 `WorkbenchResponse`。
- `evidence.get` 返回净化后的 `EvidencePack`。
- `quality.run` 返回 Quality Gate report。
- `pilot.run` 返回 Real Dataset Pilot report。

## 调用示例

列出 LLM-safe tools：

```python
from src.api.tool_registry import list_tools

tools = list_tools(llm_safe_only=True)
```

查询 approved + warehouse_ready 数据集：

```python
from src.api.tool_registry import invoke_tool

response = invoke_tool(
    "workbench.query",
    {
        "dataset_id": "ds_example",
        "domain": "admissions",
        "natural_language": "我今年高考分数630，想读计算机，想留在广东省",
        "deterministic_fields": {"user_score": 630},
        "top_k": 10
    },
    {
        "actor_id": "agent",
        "permission_scopes": ["query"]
    }
)
```

确认候选：

```python
confirmed = invoke_tool(
    "workbench.confirm",
    {
        "previous_response": response,
        "confirmed_candidate_ids": ["cand_..."]
    },
    {
        "actor_id": "agent",
        "permission_scopes": ["confirm"]
    }
)
```

审计事件默认写入：

```text
outputs/tool_audit/audit.jsonl
```

调用方也可以在 `actor_context.audit_path` 指定审计文件。

HTTP tool invoke 请求体固定为：

```json
{
  "payload": {},
  "actor_context": {
    "actor_id": "agent",
    "permission_scopes": ["query"],
    "dataset_root": "outputs/uploaded_datasets",
    "audit_path": "outputs/tool_audit/audit.jsonl"
  }
}
```

HTTP headers 也可提供同样权限信息：

```text
X-Actor-Id: agent
X-Permission-Scopes: query,read_only
```

`GET /tools/list?llm_safe_only=true` 在无权限 header 时只暴露 LLM-safe scopes；普通 `GET /tools/list` 会按 actor permission 过滤，不默认展示 admin tools。

## Tool Manifest

发布时可导出统一 manifest：

```bash
.venv/bin/python scripts/export_tool_manifest.py
.venv/bin/python scripts/export_openai_tools.py
```

输出：

```text
outputs/tool_manifest/tool_manifest.json
outputs/tool_manifest/openai_tools.json
```

manifest 顶层结构：

```json
{
  "tool_contract_version": "tools.v1",
  "tools": []
}
```

每个 tool 条目都会标记 `permission_scope`、`llm_safe`、`side_effects`、`executes_sql`、`writes_files`、`required_domain_status`、`input_schema`、`output_schema`、`status_enum` 和 `security_notes`。

## OpenAI-compatible Adapter

`src/api/openai_tool_adapter.py` 把内部 tool contract 转成 OpenAI function calling 可用的 tools：

```python
from src.api.openai_tool_adapter import OpenAIToolAdapter

adapter = OpenAIToolAdapter()
tools = adapter.export_tools()
```

默认导出的函数名使用双下划线映射点号，例如：

| 内部 tool | OpenAI function name |
|---|---|
| `dataset.profile` | `dataset__profile` |
| `dataset.review_summary` | `dataset__review_summary` |
| `workbench.query` | `workbench__query` |
| `workbench.confirm` | `workbench__confirm` |
| `evidence.get` | `evidence__get` |

默认 adapter 只包含 LLM-safe tools。即使调用方手工传入 `dataset__approve_op`，也会返回 `tool_not_allowed`，不会落到 review workflow。`scripts/export_openai_tools.py --include-admin` 仅用于 operator 审查导出，不应交给 LLM-safe agent。

## MCP Adapter

`src/api/mcp_tool_adapter.py` 提供最小 MCP-style adapter：

```python
from src.api.mcp_tool_adapter import MCPToolAdapter

adapter = MCPToolAdapter()
tools_payload = adapter.list_tools()
result = adapter.call_tool(
    "workbench.query",
    {"natural_language": "Austin under 1900"},
    {"actor_id": "agent", "permission_scopes": ["query"]}
)
```

`list_tools()` 返回 `tools` 数组，每个元素包含 `name`、`description` 和 `inputSchema`。`call_tool()` 返回 `isError`、`content` 和 `structuredContent`。默认同样只允许 LLM-safe tools；admin tool 返回 `tool_not_allowed`。

## 黑盒 Agent 验收

```bash
.venv/bin/python scripts/run_agent_tool_acceptance.py
```

该脚本用 operator 权限准备临时 queryable dataset，然后让 fake agent 只通过 OpenAI adapter 调用 LLM-safe tools，覆盖：

- list tools 只返回五个 LLM-safe tools；
- `dataset.profile`；
- `dataset.review_summary`；
- `workbench.query`；
- `workbench.confirm` 拒绝伪造 `candidate_id`；
- `evidence.get`；
- admin tool 权限拒绝。

输出固定为：

```text
outputs/agent_tool_acceptance/report.md
outputs/agent_tool_acceptance/report.json
```

## 安全规则

- `draft`、`needs_review`、`blocked` domain pack 调用 `workbench.query` 必须返回 `blocked`，不执行 SQL。
- `approve_field`、`approve_op`、`approve_domain` 必须使用 `review_admin` 权限，不能标记为 LLM-safe。
- `dataset.build_warehouse` 必须使用 `warehouse_admin` 权限。
- `quality.run` 和 `pilot.run` 是 diagnostics/admin tools，不暴露给 LLM 自动调用。
- `evidence.get` 会移除 stack trace、环境变量、密钥和绝对本地路径。
- LLM 不允许生成 SQL、不允许构造 hard rules、不允许伪造 `candidate_id`。
- 每次 tool invoke 都写 audit event；audit event 只记录摘要和副作用，不记录完整上传文件内容、环境变量或 secret。
