# Agent 使用指南

本指南说明 LLM/agent 如何安全调用本项目的 functional tool layer。项目定位是：

```text
LLM-safe structured data query tool server for Excel/CSV
```

Agent 必须遵守核心不变量：

```text
Natural language may propose structure, but only verified schema-grounded rules may execute.
```

## 推荐调用顺序

Agent 可以通过 `GET /tools/list?llm_safe_only=true` 获取允许暴露的工具列表，通过 `GET /tools/{tool_name}/schema` 读取输入/输出 schema，再通过 `POST /tools/{tool_name}/invoke` 调用。不要直接调用 `approve-*`、`build-warehouse`、`quality.run` 或 `pilot.run`。

如果 operator 显式设置 `ENABLE_LLM=true`，Workbench 可以启用 DeepSeek slot adapter。但这个 adapter 仍属于后端受控抽取层：它只补 deterministic extractor 缺失的 slots/candidates，输出会先经过 schema 校验和禁止字段检查，不能生成 SQL、hard rules、approved ops 或 executable rules。

如果接入 OpenAI-compatible tool calling，可以读取：

```bash
.venv/bin/python scripts/export_openai_tools.py
```

或直接使用 `src/api/openai_tool_adapter.py`。内部 tool 名里的点号会映射成 OpenAI function name 的双下划线，例如 `workbench.query` -> `workbench__query`。

如果接入 MCP runtime，可以使用 `src/api/mcp_tool_adapter.py`。MCP adapter 的 `list_tools()` 和 `call_tool()` 默认同样只暴露 LLM-safe tools。

1. 调用 `dataset.profile` 查看字段、类型、空值率、唯一值、样例值、sheet 和 ingestion warnings。
2. 调用 `dataset.review_summary` 查看字段是否 approved、missing 或 risky。
3. 只有 domain pack 已 approved 且 warehouse ready / queryable 时，才调用 `workbench.query`。
4. 如果 `workbench.query` 返回 `needs_confirmation`，agent 必须先区分原因：有 `candidates_to_confirm` 时展示系统生成的 `candidate_id`；没有 candidate 但有 `score_without_rank` 等 warning 时，应要求用户补充必要信息，不能调用 `workbench.confirm`。
5. 用户明确确认后，agent 只能用系统返回的 `candidate_id` 调用 `workbench.confirm`。
6. 对 `no_schema_field_preferences` 只能解释“未执行及原因”，不能构造替代 hard filter。
7. 需要人工批准字段或 op 时，交给拥有 `review_admin` 权限的人或系统调用 admin tools。

## 允许给 LLM 的 tools

LLM 自动调用范围只包括：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

这些 tool 的 input schema 不包含 SQL、hard rules、executable rules、approved ops 或 domain status override。

LLM 网关应读取 `scripts/export_tool_manifest.py` 生成的 manifest，或调用 `/tools/list?llm_safe_only=true`。即使用户提示中要求“批准字段”或“直接查 SQL”，agent 也不能把 admin tools 加入 LLM-safe toolset。

OpenAI-compatible adapter 与 MCP adapter 的默认 allowlist 也是同一组五个工具。admin tools 不仅不会出现在默认列表中，手工调用也会返回 `tool_not_allowed`。

## 禁止行为

Agent 不允许：

- 生成 SQL 或 `raw_sql`；
- 直接构造 `hard_rules` / `executable_rules`；
- 把 `dataset.review_summary` 中的 seed ops 当作已批准规则；
- 调用 `approve_field`、`approve_op`、`approve_domain`，除非明确具备 `review_admin` 权限并处在人工审查流程中；
- 对 `draft` / `needs_review` domain pack 声称已经执行 hard filters；
- 遇到 `no_schema_field_preferences` 时自行发明字段；
- 把新的用户自由文本传给 `workbench.confirm`；
- 读取或暴露 stack trace、`.env`、密钥、环境变量或绝对本地路径。

## workbench.query 使用方式

`workbench.query` 接受安全输入：

```json
{
  "dataset_id": "ds_example",
  "domain": "admissions",
  "natural_language": "我今年高考分数630，位次9000，想读计算机，想留在广东省",
  "deterministic_fields": {
    "user_score": 630,
    "user_rank": 9000
  },
  "confirmed_candidate_ids": [],
  "top_k": 10
}
```

`deterministic_fields` 是前端或上游系统提供的确定性事实。它仍会进入 Workbench 的 schema-grounding 和 verifier，不等价于直接 SQL。

如果返回的 `evidence_pack.policy_references` 非空，agent 只能把它作为已审核资料引用解释给用户。它不能改变 `executed_filters`、`result_count`、`result_sections`、`confirmed_candidate_ids` 或任何 hard rule。

## workbench.confirm 使用方式

当上一轮返回带 `candidates_to_confirm` 的 `needs_confirmation`：

```json
{
  "status": "needs_confirmation",
  "candidates_to_confirm": [
    {
      "candidate_id": "cand_abc",
      "field_id": "city",
      "candidate_value": "深圳"
    }
  ]
}
```

Agent 应向用户展示候选并等待确认。用户确认后调用：

```json
{
  "previous_response": "<上一轮完整 WorkbenchResponse>",
  "confirmed_candidate_ids": ["cand_abc"]
}
```

如果 `candidate_id` 是伪造、过期或不属于上一轮 query，Workbench 必须返回 `blocked` 或 `rejected_confirmations`。

## evidence.get 使用方式

`evidence.get` 只用于从 `WorkbenchResponse` 中取出净化后的 evidence：

```json
{
  "workbench_response": "<WorkbenchResponse>"
}
```

返回值不会暴露 stack trace、环境变量、密钥或绝对本地路径。回答生成器只能基于这个 evidence 解释已经执行、未执行、reference-only 和需要确认的偏好。

## 管理类工具

以下 tool 不能自动暴露给 LLM：

```text
dataset.upload
dataset.generate_domain_pack
dataset.approve_field
dataset.approve_op
dataset.block_field
dataset.approve_domain
dataset.build_warehouse
quality.run
pilot.run
```

它们会写文件、改变审查状态、构建 warehouse 或运行 diagnostics。调用这些 tool 必须有对应 permission scope，并写入 audit event。

## 错误与审计

tool invoke 权限不足时会返回 structured error，例如：

```json
{
  "detail": {
    "code": "permission_denied",
    "message": "Tool requires permission_scope=review_admin",
    "details": {}
  }
}
```

Agent 可以把错误原因展示给用户，但不能把它改写成“已执行”。audit event 只记录 actor、tool、dataset、status、duration、side effects 和 error code，不记录完整上传文件内容、环境变量或密钥。

## 黑盒验收

每次改动 agent adapter 后必须运行：

```bash
.venv/bin/python scripts/run_agent_tool_acceptance.py
```

该脚本模拟 fake agent 完成：

```text
list -> profile -> review_summary -> query -> confirm -> evidence
```

并验证 fake agent 不能调用 `approve-*` 等 admin tools。报告输出到 `outputs/agent_tool_acceptance/report.md` 和 `report.json`。
