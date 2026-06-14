# Workbench API 响应契约

本文固定 `/api/workbench/run` 和 `/workbench/query` 的多领域响应契约。前端应优先读取统一 `items`
层；`top_results` 仅作为 domain-specific 兼容层保留。`debug_trace` 内保留旧调试
结构，用于排查，不应作为主展示字段来源。

项目对外定位为 `LLM-safe structured data query tool server for Excel/CSV`。HTTP API、
`src/api/tool_registry.py` 和 `schemas/tools/*.json` 都必须复用本文的
`WorkbenchResponse` / DatasetResponse / QualityGate report 契约，不能另造一套可绕过 verifier
的输入或输出结构。

## status 枚举

| status | 含义 |
|---|---|
| `ok` | 已执行安全 hard filters，可以展示基于已执行规则的结果。 |
| `needs_confirmation` | 存在未确认的 `partial_match` candidate；这些 candidate 不能声称已执行。可以返回 provisional `items`。 |
| `no_results` | SQL 正常执行，但 `filtered_row_count` 为 `0`。回答不能编造推荐。 |
| `blocked` | fingerprint guard、未 approve 的 draft domain pack、伪造/过期/不属于当前 query 的 `candidate_id`、stale warehouse 等安全问题导致不执行 SQL。 |
| `error` | 非预期异常。返回 structured error，不向前端暴露 stack trace。 |

## domain_pack_status

| domain_pack_status | 含义 |
|---|---|
| `draft` | 自动生成或尚未 review 的 domain pack。默认 `blocked`，不允许执行 hard filters。 |
| `needs_review` | 已有人处理但仍未 approve。默认 `blocked`，不允许执行 hard filters。 |
| `approved` | 已审查并可进入 Workbench 执行。 |
| `blocked` | pack 配置异常或被安全策略阻断。 |

## Domain Pack Review / Approval

新 CSV/Excel 不能从 auto-generator 直接进入生产执行。正式接入流程固定为：

```text
generate draft
-> review
-> approve
-> demo acceptance
-> real dataset pilot
-> quality gate
-> commit / release
```

`scripts/generate_domain_pack.py` 只生成 `draft` / `needs_review` 配置、schema profile、
schema/value index 和 seed 文件。seed 中的 `candidate_allowed_ops`、候选
`rule_taxonomy`、候选 `top_result_mapping` 和候选 `sort_policy` 只能作为 review 输入，
不能直接进入 `RuleVerifier` hard rules。

`scripts/review_domain_pack.py` 负责审查和批准：

- `summarize` 汇总字段、dtype、空值率、唯一值数量、样例、数值范围、PII/高基数风险和 value index 状态。
- `validate` 校验 `DomainConfig`、`WorkbenchResponse` contract、`top_result_mapping`、`rule_taxonomy` 和 `sort_policy` 结构。
- `approve-field` / `approve-op` 显式写入被批准的字段和 op。
- `block-field` / `block-op` 显式阻断字段或 op，并写入审计历史。
- `approve-domain` 只有在 required checks 通过后，才允许把 `domain_pack_status` 改成 `approved`。
- `report` 输出 `outputs/domain_review/<domain>_review.md` 和 `<domain>_review.json`。

CLI 默认 dry-run；只有显式 `--write` 才写文件。`review.yaml` 至少记录 domain、
domain version、pack status、source fingerprint、schema profile fingerprint、reviewed
fields、blocked fields、approved ops、blocked ops、review notes、reviewed_at、
reviewed_by 和 approval history。

安全规则：

- `draft` / `needs_review` 仍然返回 `blocked`，不执行 SQL。
- `approve-domain` 前必须确认至少一个 item title mapping、至少一个 primary attribute mapping，以及非空 sort policy 或明确 `--default-safe-sort`。
- PII、高基数字段不能默认 approve 为 categorical hard filter。
- 数值字段必须通过 dtype、空值率和范围 sanity check 后，才能 approve `<=`、`>=`、`between`。
- categorical 字段必须唯一值数量低于阈值，且 value index 可审查，才能 approve `eq` / `in`。
- text contains / keyword filter 默认 `needs_review`，不能自动 approve。

`scripts/run_quality_gate.py` 是交付前统一门禁。它会运行 Python 语法检查、unit tests、
regex evaluator、API contract tests、demo acceptance、domain pack validate、domain review
workflow smoke、warehouse fingerprint guard、`git diff --check` 和可选前端 build。门禁报告写入
`outputs/quality_gate/report.md` 和 `outputs/quality_gate/report.json`；任何 required check
失败时，release 不应继续。

## Uploaded Dataset / Ingestion API

上传数据集产品流复用 `generate_domain_pack.py`、`review_domain_pack.py`、warehouse
ingestion、fingerprint guard、`DomainConfig` 和 `WorkbenchResponse`，不复制执行逻辑。
状态流转固定为：

```text
uploaded
-> profiled
-> draft_domain_generated
-> needs_review
-> approved
-> warehouse_ready
-> queryable
-> blocked/error
```

endpoint：

| endpoint | 含义 |
|---|---|
| `POST /datasets/upload?filename=...` | 上传 CSV/Excel 原始 body，保存到托管目录，返回 `dataset_id` 和 `source_fingerprint`。 |
| `POST /datasets/{dataset_id}/generate-domain-pack` | 生成 draft domain pack、schema profile、schema/value index 和 ingestion summary。 |
| `GET /datasets/{dataset_id}/profile` | 返回字段类型、空值率、唯一值数量、样例值、sheet list、detected header row、原始列映射和风险标记。 |
| `GET /datasets/{dataset_id}/review-summary` | 返回可审查字段、seed ops、required/missing fields、PII / high-cardinality / text / special-plan 风险。 |
| `POST /datasets/{dataset_id}/approve-field` | 调用 review workflow 批准字段，并写入审计记录。 |
| `POST /datasets/{dataset_id}/approve-op` | 调用 review workflow 批准字段的特定 op，并写入审计记录。 |
| `POST /datasets/{dataset_id}/block-field` | 调用 review workflow 阻断字段，并写入审计记录。 |
| `POST /datasets/{dataset_id}/approve-domain` | required checks 通过后批准 domain pack。 |
| `POST /datasets/{dataset_id}/build-warehouse` | 基于 approved pack 构建 DuckDB warehouse 和 value index。 |
| `POST /workbench/query` | 支持 `dataset_id` / `domain_name`，返回同一 `WorkbenchResponse` contract。 |

这些 endpoint 与 tool registry 使用同一套 actor context 和 permission enforcement。HTTP 调用方可以通过 `X-Actor-Id` 与 `X-Permission-Scopes` 传递身份和权限；`POST /tools/{tool_name}/invoke` 也可以在 body 的 `actor_context` 中传递同样字段。

## Tool Server API

工具层把 DatasetService、Workbench、EvidencePack、Quality Gate 和 Real Dataset Pilot 包装成 stable tool contracts，不复制业务逻辑。

| endpoint | 返回 |
|---|---|
| `GET /tools/list` | 当前 actor 可见的 tool 摘要。支持 `permission_scope` 和 `llm_safe_only` query 参数。 |
| `GET /tools/{tool_name}/schema` | 单个 `schemas/tools/*.json` contract。 |
| `POST /tools/{tool_name}/invoke` | 调用 `src/api/tool_registry.py` 中的 `invoke_tool`，成功时返回 tool 原始 output，失败时返回 structured error。 |
| `GET /healthz` | liveness，固定 `{"status":"ok"}`。 |
| `GET /readyz` | readiness，检查 data root、tool schemas、DomainConfig 和 Quality Gate 基础依赖。 |
| `GET /version` | 返回 `git_commit`、`schema_version`、`api_version`、`tool_contract_version`。 |

`POST /tools/{tool_name}/invoke` 请求形状：

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

LLM-safe tools 只能是：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

LLM-facing input schema 不允许出现 `raw_sql`、`sql`、`executable_rules`、`hard_rules`、`approved_ops`、`domain_pack_status` 等可绕过 verifier 的字段。`workbench.query` 只接受 `dataset_id`、`domain`、`deterministic_fields`、`natural_language`、`confirmed_candidate_ids`、`top_k`；`workbench.confirm` 只能引用上一轮系统生成的 `candidate_id`。

所有 tool invoke 都写 audit event，包含 `actor_id`、`tool_name`、`dataset_id`、`status`、`duration_seconds`、`side_effects` 和 `error_code`。audit log 不记录密钥、完整上传文件内容或环境变量；`evidence.get` 和错误响应不能暴露 stack trace、绝对路径或 secret。

tool manifest 可通过命令导出：

```bash
.venv/bin/python scripts/export_tool_manifest.py
```

输出固定为：

```text
outputs/tool_manifest/tool_manifest.json
```

安全语义：

- `dataset_id` 只能包含字母、数字、下划线和连字符，禁止目录穿越；上传数据不能覆盖内置 `admissions`、`housing`、`products`。
- 上传文件会检查扩展名、大小、sheet、行数和列数，并返回 structured warning/error。
- Excel 默认选择第一个非空 sheet，同时返回所有 sheet 的 row/column/non-empty summary。
- header row detection 会扫描前若干行；不确定时返回 `header_row_detection_needs_review` warning。
- 重复列名会生成安全列名并保留 `original_column_mapping`；空列、全空行、列名换行、首尾空格和中文括号会被清洗。
- 合并单元格、隐藏行列、公式单元格会进入 structured warnings。
- `draft` / `needs_review` pack 必须返回 `blocked`，不执行 SQL。
- `warehouse` metadata、schema/value index metadata 和源文件 fingerprint 不一致时返回 `blocked`。
- `POST /workbench/query` 仍走 `DomainConfig`、`RuleVerifier`、confirmation loop 和参数化 DuckDB SQL；前端自然语言不能直接生成 hard filter。
- uploaded admissions 数据集可以复用已审查 `admissions` domain pack，但仍必须先 `approve-domain` 并重建 warehouse。

## Functional Tool Layer

tool registry 位于：

```text
src/api/tool_registry.py
```

机器可读 tool contract 位于：

```text
schemas/tools/*.json
```

LLM-safe tools 仅限：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

`workbench.query` 的 LLM-facing input 只允许 `dataset_id`、`domain`、
`deterministic_fields`、`natural_language`、`confirmed_candidate_ids`、`top_k`。
不得接受 `raw_sql`、`sql`、`hard_rules`、`executable_rules`、`approved_ops` 或
`domain_pack_status`。`workbench.confirm` 必须基于上一轮 `WorkbenchResponse` 和
系统生成的 `candidate_id`，不能接受新的用户自由文本来构造 hard filter。

详细 tool contract 见 `docs/tool_contract.md`，agent 调用规范见
`docs/agent_usage_guide.md`。

## Real Dataset Pilot

真实招生 CSV/Excel 在进入生产前，应先运行：

```bash
python scripts/run_real_dataset_pilot.py path/to/admissions.xlsx
```

pilot 完整执行 upload -> profile -> generate draft domain pack -> review summary ->
safe auto-suggest approvals -> manual approval fixture -> build warehouse -> target
admissions queries，并输出：

```text
outputs/real_dataset_pilot/report.md
outputs/real_dataset_pilot/report.json
```

报告记录 `source_path`、`dataset_id`、`source_fingerprint`、`sheet_name`、
`row_count` / `column_count`、`detected_header_row`、schema profile summary、risky
fields、approved/blocked fields、warehouse path/fingerprint、目标查询结果、warnings
和 failures。缺少必要 admissions canonical fields 或分数字段语义不清时，目标 query
必须返回 `blocked` 或带 needs-review warning，不能硬执行 SQL。

## 固定顶层字段

| 字段 | 类型 | 必选 | 跨领域含义 |
|---|---|---|---|
| `schema_version` | string | 是 | 当前固定为 `workbench_response.v1`。 |
| `domain` | string | 是 | 当前执行的 domain id，例如 `admissions`、`housing`、`products`。 |
| `domain_version` | string | 是 | domain pack 版本。 |
| `domain_pack_status` | string | 是 | 只能是 `draft`、`needs_review`、`approved`、`blocked`。 |
| `status` | string | 是 | 只能是 `ok`、`needs_confirmation`、`no_results`、`blocked`、`error`。 |
| `query_type` | string | 是 | 本轮规划类型。通用管线为 `verified_filter`；admissions 额外支持 `group_detail_report` 和 `recommendation`。 |
| `query` | object | 是 | 本轮请求文本、domain、结构化输入和提交的 `candidate_id`。 |
| `answer` | string | 是 | 面向用户的证据回答文本。 |
| `result_count` | number | 是 | DuckDB filtered row count；`blocked` 和 `error` 为 `0`。 |
| `items` | array | 是 | 跨领域稳定 item card。前端主列表应优先使用该字段。 |
| `top_results` | array | 是 | domain-specific 兼容层，由 `domains/<domain>/top_result_mapping.yaml` 生成。 |
| `result_sections` | object | 是 | query type 专用分组结果。无分组时为空对象。 |
| `executed_filters` | array | 是 | 已进入 hard filter 的规则。 |
| `candidates_to_confirm` | array | 是 | 本轮仍可用 `candidate_id` 确认的候选。 |
| `confirmed_rules` | array | 是 | 已通过 `candidate_id` 确认并进入执行审查的规则。 |
| `unconfirmed_candidates` | array | 是 | 尚未确认的可执行候选。 |
| `unexecuted_preferences` | array | 是 | 已保留但未执行的偏好。 |
| `no_schema_field_preferences` | array | 是 | 缺少 schema 字段的偏好；即使确认也不能执行。 |
| `rejected_confirmations` | array | 是 | 被拒绝的 `candidate_id` 确认请求。 |
| `warnings` | array | 是 | 结构化 warning，每项至少包含 `code` 和 `message`。 |
| `evidence_pack` | object | 是 | Answer/EvidencePack 证据包。内部可以保留源字段名；可包含 `policy_references` 这类 reference-only 解释资料。 |
| `debug_trace` | object | 是 | 调试结构，包含旧字段、执行 trace、token usage 等。 |

## items

每个 `items[]` 都必须包含：

| 字段 | 类型 | 含义 |
|---|---|---|
| `item_id` | string | 当前响应内稳定 id。 |
| `title` | string | item 主标题。 |
| `subtitle` | string | item 副标题。 |
| `primary_attributes` | array | 主展示属性，元素包含 `key`、`label`、`value`。 |
| `secondary_attributes` | array | 次展示属性，元素包含 `key`、`label`、`value`。 |
| `matched_filters` | array | 与该 item 匹配的 hard filters。 |
| `raw` | object | 证据追溯用源结果，不作为跨领域 UI 字段契约。 |

## top_results

`top_results` 是兼容层，不是跨领域主列表契约。招生 domain 必须继续返回现有英文
key，包括：

```text
university_name
group_code
major_code
major_name
full_major_name
city
tuition
rank_2024
plan_count
group_min_rank
major_min_rank
safety_margin
```

housing/products 使用各自 `top_result_mapping.yaml` 输出。测试和 demo 应优先依赖
`items`，只保留专门的 backward compatibility 测试防止 admissions 英文字段回归。

## admissions query_type

`admissions` domain 在通用 verified filter 外，新增两个 admissions-specific planner：

- `group_detail_report`：用于“列出某年某校录取最高的专业组及组内专业最低分”。SQL
  必须参数化；`EvidencePack.execution_summary` 记录 `query_type`、`sql`、`params`、
  `detail_sql`、`detail_params`、`group_by`、`metric`、`sort` 和
  `nested_result_count`。`result_sections.groups[]` 包含 `group_code`、
  `group_title`、`group_metric_score` 和 `majors[]`。
- `recommendation`：用于基于历史最低分/最低位次的 admissions 推荐分组。前端传入的
  deterministic fields 优先于自然语言；自然语言只补充 preferences/candidates。输出
  `result_sections.reach`、`result_sections.match`、`result_sections.safety`，展示标签为
  `冲`、`稳`、`保`。如果用户只有分数没有位次，必须返回 `score_without_rank` warning；
  有位次时按 `rank_margin` 优先排序。`EvidencePack.execution_summary` 必须记录
  `margin_policy`、`year_weighting`、`major_match` 和 `bucket_counts`：当前策略只执行
  `latest_available_year`，不跨年加权；专业匹配来源必须区分 deterministic fields、
  exact keywords 和 confirmed candidates。回答不得声称录取概率。

## EvidencePack reference-only 资料

`EvidencePack.policy_references` 是可选数组，用于承载已审核非结构化资料的 lexical
命中，例如招生章程、政策说明或专业介绍片段。每条记录至少包含 `reference_id`、
`title`、`source`、`matched_terms`、`excerpt`、`status` 和 `effect`。其中
`status` 固定为 `reference_only`，`effect` 固定为
`does_not_change_sql_or_results`。前端和 agent 可以展示这些引用，但不能把它们
当作 hard filter、candidate confirmation 或 recommendation bucket 的依据。

## 示例：admissions ok

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "admissions",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "ok",
  "query_type": "verified_filter",
  "query": {"text": "广东物理，排位32000，想学计算机，广深优先。", "domain": "admissions", "confirmed_candidates": []},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 149,
  "items": [
    {
      "item_id": "result_001",
      "title": "中山大学",
      "subtitle": "计算机类",
      "primary_attributes": [{"key": "city", "label": "city", "value": "广州"}],
      "secondary_attributes": [{"key": "rank_2024", "label": "rank_2024", "value": 4019}],
      "matched_filters": [{"id": "e_major_keyword", "field": "专业名称", "matched": true}],
      "raw": {"院校名称": "中山大学", "专业名称": "计算机类"}
    }
  ],
  "top_results": [
    {"university_name": "中山大学", "group_code": "10558219", "major_code": "0809", "major_name": "计算机类", "full_major_name": "计算机类", "city": "广州", "tuition": 6850, "rank_2024": 4019, "plan_count": null}
  ],
  "result_sections": {},
  "executed_filters": [{"id": "e_major_keyword", "field": "专业名称", "operator": "contains_any", "value": ["计算机"]}],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [],
  "evidence_pack": {"execution_summary": {"executor": "duckdb", "filtered_row_count": 149}},
  "debug_trace": {"execution": {"executor": "duckdb"}}
}
```

## 示例：admissions needs_confirmation

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "admissions",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "needs_confirmation",
  "query_type": "verified_filter",
  "query": {"text": "广东物理，物化生，排位32000，想学计科，广深优先。", "domain": "admissions", "confirmed_candidates": []},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 3962,
  "items": [{"item_id": "result_001", "title": "香港中文大学(深圳)", "subtitle": "理科试验班", "primary_attributes": [], "secondary_attributes": [], "matched_filters": [], "raw": {}}],
  "top_results": [{"university_name": "香港中文大学(深圳)", "group_code": "16407101", "major_name": "理科试验班", "city": "深圳", "rank_2024": 968}],
  "result_sections": {},
  "executed_filters": [{"id": "e_city", "field": "城市", "operator": "in_contains", "value": ["广州", "深圳"]}],
  "candidates_to_confirm": [{"candidate_id": "cand_example", "source_text": "计科", "match_type": "partial_match", "executable": true}],
  "confirmed_rules": [],
  "unconfirmed_candidates": [{"candidate_id": "cand_example", "source_text": "计科"}],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [{"code": "needs_confirmation", "severity": "warning", "message": "存在未确认 partial_match candidate，未进入 hard filter。"}],
  "evidence_pack": {"unconfirmed_candidates": [{"candidate_id": "cand_example"}]},
  "debug_trace": {"confirmation_state": {"accepted_candidate_ids": []}}
}
```

## 示例：admissions confirmed rerun

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "admissions",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "ok",
  "query_type": "verified_filter",
  "query": {"text": "广东物理，物化生，排位32000，想学计科，广深优先。", "domain": "admissions", "confirmed_candidates": ["cand_example"]},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 149,
  "items": [{"item_id": "result_001", "title": "中山大学", "subtitle": "计算机类", "primary_attributes": [], "secondary_attributes": [], "matched_filters": [{"id": "e_confirmed_example", "matched": true}], "raw": {}}],
  "top_results": [{"university_name": "中山大学", "group_code": "10558219", "major_name": "计算机类", "city": "广州", "rank_2024": 4019}],
  "result_sections": {},
  "executed_filters": [{"id": "e_confirmed_example", "field": "专业名称", "operator": "contains_any", "value": ["计算机"]}],
  "candidates_to_confirm": [],
  "confirmed_rules": [{"id": "e_confirmed_example", "candidate_id": "cand_example", "executed": true}],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [],
  "evidence_pack": {"confirmed_rules": [{"rule_id": "e_confirmed_example"}], "executed_after_confirmation": ["e_confirmed_example"]},
  "debug_trace": {"execution": {"hard_rule_ids": ["e_confirmed_example"]}}
}
```

## 示例：housing ok

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "housing",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "ok",
  "query_type": "verified_filter",
  "query": {"text": "Austin, at least 2 bedrooms, under 1900.", "domain": "housing"},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 3,
  "items": [{"item_id": "result_001", "title": "14", "subtitle": "Austin", "primary_attributes": [{"key": "rent_usd", "label": "rent_usd", "value": 1650}], "secondary_attributes": [], "matched_filters": [], "raw": {"listing_id": 14}}],
  "top_results": [{"listing_id": 14, "city": "Austin", "bedrooms": 2, "rent_usd": 1650, "property_type": "townhouse"}],
  "result_sections": {},
  "executed_filters": [{"id": "e_rent_cap", "field": "rent_usd", "operator": "<=", "value": 1900}],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [],
  "evidence_pack": {"execution_summary": {"executor": "duckdb"}},
  "debug_trace": {"execution": {"executor": "duckdb"}}
}
```

## 示例：products ok

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "products",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "ok",
  "query_type": "verified_filter",
  "query": {"text": "audio products under 100", "domain": "products"},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 2,
  "items": [{"item_id": "result_001", "title": "Speaker Mini", "subtitle": "audio", "primary_attributes": [{"key": "price_usd", "label": "price_usd", "value": 49}], "secondary_attributes": [], "matched_filters": [], "raw": {"product_name": "Speaker Mini"}}],
  "top_results": [{"product_id": 17, "product_name": "Speaker Mini", "category": "audio", "price_usd": 49, "rating": 4.2}],
  "result_sections": {},
  "executed_filters": [{"id": "e_price_cap", "field": "price_usd", "operator": "<=", "value": 100}],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [],
  "evidence_pack": {"execution_summary": {"executor": "duckdb"}},
  "debug_trace": {"execution": {"executor": "duckdb"}}
}
```

## 示例：no_results

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "admissions",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "no_results",
  "query_type": "verified_filter",
  "query": {"text": "广东物理，排位90000，想学网络安全，深圳。", "domain": "admissions"},
  "answer": "共筛选到 0 条符合已执行规则的结果。",
  "result_count": 0,
  "items": [],
  "top_results": [],
  "result_sections": {},
  "executed_filters": [{"id": "e_major_keyword", "field": "专业名称", "operator": "contains_any", "value": ["网络安全"]}],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [{"code": "no_results", "severity": "warning", "message": "SQL 正常执行但 filtered_row_count 为 0，不能生成推荐。"}],
  "evidence_pack": {"result_count": 0, "top_k_results": []},
  "debug_trace": {"execution": {"executor": "duckdb", "filtered_row_count": 0}}
}
```

## 示例：blocked draft domain pack

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "draft_contract",
  "domain_version": "1",
  "domain_pack_status": "draft",
  "status": "blocked",
  "query_type": "verified_filter",
  "query": {"text": "Austin under 1900", "domain": "draft_contract"},
  "answer": "domain pack 状态为 draft，未 approve 前不能执行 SQL。",
  "result_count": 0,
  "items": [],
  "top_results": [],
  "result_sections": {},
  "executed_filters": [],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [{"code": "domain_pack_not_approved", "severity": "error", "message": "domain pack 状态为 draft，未 approve 前不能执行 SQL。"}],
  "evidence_pack": {},
  "debug_trace": {"execution": {"executor": null, "sql": "", "params": []}}
}
```

## 示例：blocked rejected confirmation

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "admissions",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "blocked",
  "query_type": "verified_filter",
  "query": {"text": "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。", "domain": "admissions", "confirmed_candidates": ["cand_forged"]},
  "answer": "candidate_id 确认失败，Workbench 未执行 SQL。",
  "result_count": 0,
  "items": [],
  "top_results": [],
  "result_sections": {},
  "executed_filters": [],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [{"candidate_id": "cand_forged", "reason_code": "candidate_id_not_current_query", "blocks_execution": true}],
  "warnings": [{"code": "candidate_id_not_current_query", "severity": "error", "message": "candidate_id 不属于当前 query，或不是系统上一轮生成的候选。"}],
  "evidence_pack": {},
  "debug_trace": {"execution": {"executor": null, "sql": "", "params": []}}
}
```

## error 语义

`error` 响应同样保留所有顶层字段，但 `items`、`top_results`、`executed_filters`
为空，`result_sections` 为空对象，`warnings[].code` 为 `workbench_error`。`answer` 和 `warnings` 不得包含
`Traceback`、文件路径栈或内部调用栈。
