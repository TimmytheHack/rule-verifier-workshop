# Workbench API 响应契约

本文固定 `/api/workbench/run` 的多领域响应契约。前端应优先读取统一 `items`
层；`top_results` 仅作为 domain-specific 兼容层保留。`debug_trace` 内保留旧调试
结构，用于排查，不应作为主展示字段来源。

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

## 固定顶层字段

| 字段 | 类型 | 必选 | 跨领域含义 |
|---|---|---|---|
| `schema_version` | string | 是 | 当前固定为 `workbench_response.v1`。 |
| `domain` | string | 是 | 当前执行的 domain id，例如 `admissions`、`housing`、`products`。 |
| `domain_version` | string | 是 | domain pack 版本。 |
| `domain_pack_status` | string | 是 | 只能是 `draft`、`needs_review`、`approved`、`blocked`。 |
| `status` | string | 是 | 只能是 `ok`、`needs_confirmation`、`no_results`、`blocked`、`error`。 |
| `query` | object | 是 | 本轮请求文本、domain、结构化输入和提交的 `candidate_id`。 |
| `answer` | string | 是 | 面向用户的证据回答文本。 |
| `result_count` | number | 是 | DuckDB filtered row count；`blocked` 和 `error` 为 `0`。 |
| `items` | array | 是 | 跨领域稳定 item card。前端主列表应优先使用该字段。 |
| `top_results` | array | 是 | domain-specific 兼容层，由 `domains/<domain>/top_result_mapping.yaml` 生成。 |
| `executed_filters` | array | 是 | 已进入 hard filter 的规则。 |
| `candidates_to_confirm` | array | 是 | 本轮仍可用 `candidate_id` 确认的候选。 |
| `confirmed_rules` | array | 是 | 已通过 `candidate_id` 确认并进入执行审查的规则。 |
| `unconfirmed_candidates` | array | 是 | 尚未确认的可执行候选。 |
| `unexecuted_preferences` | array | 是 | 已保留但未执行的偏好。 |
| `no_schema_field_preferences` | array | 是 | 缺少 schema 字段的偏好；即使确认也不能执行。 |
| `rejected_confirmations` | array | 是 | 被拒绝的 `candidate_id` 确认请求。 |
| `warnings` | array | 是 | 结构化 warning，每项至少包含 `code` 和 `message`。 |
| `evidence_pack` | object | 是 | Answer/EvidencePack 证据包。内部可以保留源字段名。 |
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

## 示例：admissions ok

```json
{
  "schema_version": "workbench_response.v1",
  "domain": "admissions",
  "domain_version": "1",
  "domain_pack_status": "approved",
  "status": "ok",
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
  "query": {"text": "广东物理，物化生，排位32000，想学计科，广深优先。", "domain": "admissions", "confirmed_candidates": []},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 3962,
  "items": [{"item_id": "result_001", "title": "香港中文大学(深圳)", "subtitle": "理科试验班", "primary_attributes": [], "secondary_attributes": [], "matched_filters": [], "raw": {}}],
  "top_results": [{"university_name": "香港中文大学(深圳)", "group_code": "16407101", "major_name": "理科试验班", "city": "深圳", "rank_2024": 968}],
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
  "query": {"text": "广东物理，物化生，排位32000，想学计科，广深优先。", "domain": "admissions", "confirmed_candidates": ["cand_example"]},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 149,
  "items": [{"item_id": "result_001", "title": "中山大学", "subtitle": "计算机类", "primary_attributes": [], "secondary_attributes": [], "matched_filters": [{"id": "e_confirmed_example", "matched": true}], "raw": {}}],
  "top_results": [{"university_name": "中山大学", "group_code": "10558219", "major_name": "计算机类", "city": "广州", "rank_2024": 4019}],
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
  "query": {"text": "Austin, at least 2 bedrooms, under 1900.", "domain": "housing"},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 3,
  "items": [{"item_id": "result_001", "title": "14", "subtitle": "Austin", "primary_attributes": [{"key": "rent_usd", "label": "rent_usd", "value": 1650}], "secondary_attributes": [], "matched_filters": [], "raw": {"listing_id": 14}}],
  "top_results": [{"listing_id": 14, "city": "Austin", "bedrooms": 2, "rent_usd": 1650, "property_type": "townhouse"}],
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
  "query": {"text": "audio products under 100", "domain": "products"},
  "answer": "根据已验证规则生成结果：...",
  "result_count": 2,
  "items": [{"item_id": "result_001", "title": "Speaker Mini", "subtitle": "audio", "primary_attributes": [{"key": "price_usd", "label": "price_usd", "value": 49}], "secondary_attributes": [], "matched_filters": [], "raw": {"product_name": "Speaker Mini"}}],
  "top_results": [{"product_id": 17, "product_name": "Speaker Mini", "category": "audio", "price_usd": 49, "rating": 4.2}],
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
  "query": {"text": "广东物理，排位90000，想学网络安全，深圳。", "domain": "admissions"},
  "answer": "共筛选到 0 条符合已执行规则的结果。",
  "result_count": 0,
  "items": [],
  "top_results": [],
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
  "query": {"text": "Austin under 1900", "domain": "draft_contract"},
  "answer": "domain pack 状态为 draft，未 approve 前不能执行 SQL。",
  "result_count": 0,
  "items": [],
  "top_results": [],
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
  "query": {"text": "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。", "domain": "admissions", "confirmed_candidates": ["cand_forged"]},
  "answer": "candidate_id 确认失败，Workbench 未执行 SQL。",
  "result_count": 0,
  "items": [],
  "top_results": [],
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
为空，`warnings[].code` 为 `workbench_error`。`answer` 和 `warnings` 不得包含
`Traceback`、文件路径栈或内部调用栈。
