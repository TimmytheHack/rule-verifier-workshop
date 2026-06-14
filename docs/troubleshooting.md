# 故障排查

本文记录本地部署、uploaded dataset 流程和 tool server 接入的常见问题。排查时优先查看 `WorkbenchResponse.status`、`warnings`、`evidence_pack`、`debug_trace.execution`、dataset metadata 和 tool audit log。

## draft / needs_review 被 blocked

现象：

```json
{"status": "blocked", "domain_pack_status": "needs_review"}
```

原因：

- auto-generator 生成的 draft pack 默认不能执行；
- seed `candidate_allowed_ops` 不是 executable `allowed_ops`；
- `approve-domain` 尚未通过 required checks。

处理：

1. 调用 `dataset.review_summary` 查看 required/missing/risky fields。
2. 使用 `approve-field`、`approve-op`、`block-field` 完成人工审查。
3. 确认 title mapping、primary attributes 和 sort policy。
4. 调用 `approve-domain` 和 `build-warehouse`。

## fingerprint stale

现象：

- `status=blocked`；
- warning 或 evidence 中出现 stale warehouse / fingerprint mismatch；
- SQL 为空。

原因：

- 上传源文件被替换；
- DuckDB 或 schema/value index 来自旧源文件；
- 手工移动或复制了 warehouse artifact。

处理：

1. 检查 dataset metadata 的 `source_fingerprint`。
2. 重新运行 `build-warehouse`。
3. 不要手工修改 DuckDB、schema/value index 或 ingestion summary。

## missing required fields

现象：

- `review-summary.missing_fields` 非空；
- admissions `group_detail_report` 或 `recommendation` 返回 `blocked` / `needs_review`；
- warnings 指出缺少 `university_name`、`group_code`、`major_name`、`min_score`、`min_rank` 等 canonical field。

原因：

- Excel 列名无法映射到 admissions canonical fields；
- header row detection 选错行；
- 字段存在但未 approve。

处理：

1. 检查 profile 的 `detected_header_row` 和原始列名映射。
2. 必要时调整源文件表头或重新上传指定 sheet。
3. 使用 review workflow 审查并批准字段。

## ambiguous score fields

现象：

- group detail query 对“录取最高”返回 `needs_confirmation` 或 warning；
- EvidencePack 中 metric 未能确定。

原因：

- 同时存在 `score`、`min_score`、`group_min_score`、`major_min_score` 候选；
- 没有配置默认 metric。

处理：

1. 在 review summary 中确认每个分数字段的 admissions semantics。
2. 只批准明确语义字段的 op。
3. 对 group detail report，确认 EvidencePack 里的 `metric`、`group_by` 和 `sort`。

## candidate_id rejected

现象：

```json
{
  "status": "blocked",
  "rejected_confirmations": [...]
}
```

原因：

- `candidate_id` 不是上一轮系统生成；
- `candidate_id` 属于另一个 query；
- candidate 已过期或 query text 改变；
- 试图确认 `no_schema_field` 偏好。

处理：

1. 前端必须保存上一轮完整 `WorkbenchResponse`。
2. `workbench.confirm` 只传 `previous_response` 和用户确认的 `candidate_id`。
3. 不要把新的自由文本传入 confirm。

## top_results / items 字段误读

现象：

- 前端从 `top_results` 读取字段后，在非 admissions domain 显示错列；
- admissions 字段英文兼容层可用，但 toy domain 或 uploaded dataset 字段不一致。

处理：

- 跨 domain 展示优先读 `items`：
  - `item_id`
  - `title`
  - `subtitle`
  - `primary_attributes`
  - `secondary_attributes`
  - `matched_filters`
  - `raw`
- `top_results` 只作为 domain-specific compatibility layer。
- admissions 兼容字段包括 `university_name`、`group_code`、`major_code`、`major_name`、`full_major_name`、`city`、`tuition`、`rank_2024`、`plan_count`。

## warehouse missing

现象：

- approved domain query 返回 `blocked`；
- SQL 为空；
- warning 指出 warehouse 不存在。

处理：

1. 调用 `dataset.build_warehouse`。
2. 检查 `warehouse_database_path` 和 `schema_value_index_path`。
3. 重新跑 `readyz` 和 `quality gate`。

## tools/list 缺少管理类工具

现象：

`GET /tools/list?llm_safe_only=true` 不返回 `approve-*`、`build-warehouse`、`quality.run` 或 `pilot.run`。

这是预期行为。LLM-safe tools 只能包括：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

operator 需要使用带对应 scope 的服务端 token：

```text
Authorization: Bearer <operator-token>
```

## permission_denied

现象：

```json
{
  "detail": {
    "code": "permission_denied",
    "message": "Tool requires permission_scope=review_admin"
  }
}
```

处理：

- 检查 `AUTH_TOKENS_JSON` 中 token 是否映射了所需 `permission_scopes`；
- 检查 HTTP header 是否包含 `Authorization: Bearer <token>` 或 `X-Actor-Token: <token>`；
- 不要依赖请求体 `actor_context.permission_scopes` 或旧 `X-Permission-Scopes` header；
- 不要把 admin tools 暴露给 LLM 自动调用。

## readiness 失败

`/readyz` 会检查：

- data root 可写；
- tool schemas 可加载；
- `admissions`、`housing`、`products` DomainConfig 可加载；
- `.venv/bin/python` 和 `scripts/run_quality_gate.py` 存在。

失败时先运行：

```bash
make bootstrap
make quality
```

## 错误响应暴露路径或密钥

API 和 tool registry 会净化 stack trace、绝对路径、环境变量和 secret。若发现输出包含敏感内容，应立即补测试并扩大净化规则。当前测试覆盖：

- tool invoke 权限不足结构化错误；
- evidence.get 不暴露 stack trace / env / secret / absolute path；
- audit log 不记录 secret、完整上传内容或环境变量。
