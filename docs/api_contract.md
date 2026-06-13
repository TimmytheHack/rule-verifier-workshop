# Workbench API 响应契约

本文固定 `/api/workbench/run` 的前端依赖字段。前端应优先使用本契约字段；`debug_trace` 内保留旧调试结构，用于排查和兼容，不应作为主展示字段来源。

## status 枚举

| status | 含义 |
|---|---|
| `ok` | hard filters 已执行，可以展示基于已执行规则的结果。 |
| `needs_confirmation` | 存在未确认的 `partial_match` 偏好；这些偏好不能声称已执行。可以展示基于已确认规则和可执行规则得到的 provisional results。 |
| `no_results` | DuckDB SQL 正常执行，但 `filtered_row_count` 为 `0`。回答不能编造推荐。 |
| `blocked` | 安全 guard 阻断执行，例如 fingerprint 不一致，或提交了伪造、过期、不属于当前 query 的 `candidate_id`。此状态下不执行 SQL。 |
| `error` | 非预期异常。返回 structured error，不向前端暴露 traceback。 |

## 固定字段

| 字段 | 类型 | 必选 | 含义 |
|---|---|---|---|
| `status` | string | 是 | 只能是 `ok`、`needs_confirmation`、`no_results`、`blocked`、`error`。 |
| `answer` | string | 是 | 面向用户的证据回答文本。 |
| `top_results` | array | 是 | 前端展示的结果列表，只使用英文 key。 |
| `result_count` | number | 是 | DuckDB filtered row count 对应的结果数量；`blocked` 和 `error` 为 `0`。 |
| `executed_filters` | array | 是 | 已进入 hard filter 的规则，包含 `id`、`field`、`operator`、`value` 等字段。 |
| `candidates_to_confirm` | array | 是 | 本轮仍可用 `candidate_id` 确认的候选。 |
| `confirmed_rules` | array | 是 | 已通过 `candidate_id` 确认并进入执行审查的规则。 |
| `unconfirmed_candidates` | array | 是 | 尚未确认的可执行候选，通常与 `candidates_to_confirm` 一致。 |
| `unexecuted_preferences` | array | 是 | 已保留但未执行的偏好。 |
| `no_schema_field_preferences` | array | 是 | 缺少 schema 字段的偏好；即使确认也不能执行。 |
| `rejected_confirmations` | array | 是 | 被拒绝的 `candidate_id` 确认请求。 |
| `warnings` | array | 是 | 结构化 warning，每项至少包含 `code` 和 `message`。 |
| `evidence_pack` | object | 是 | Answer/EvidencePack 证据包。内部可以保留中文原始字段。 |
| `debug_trace` | object | 是 | 调试结构，包含旧字段、执行 trace、token usage 等。 |

## top_results 英文 key

`top_results` 不允许混用中文字段名。固定 key 包括：

- `university_name`
- `group_code`
- `major_code`
- `major_name`
- `full_major_name`
- `city`
- `tuition`
- `rank_2024`
- `plan_count`
- `group_min_rank`
- `major_min_rank`
- `safety_margin`

缺失字段使用 `null`，不要回退到中文 key。`evidence_pack.top_k_results` 可以继续保留中文原始字段，用于证据追溯。

这些 key 的来源列由 `domains/admissions/domain.json` 中的 `top_result_mapping` 配置。前端契约仍保持固定英文 key；后端不得为了语言一致性改名，也不得绕过 domain pack 直接读取招生源列名。

## 示例：ok

```json
{
  "status": "ok",
  "answer": "根据已验证规则生成结果：...",
  "top_results": [
    {
      "university_name": "中山大学",
      "group_code": "10558219",
      "major_code": "0809",
      "major_name": "计算机类",
      "full_major_name": "计算机类",
      "city": "广州",
      "tuition": 6850,
      "rank_2024": 4019,
      "plan_count": null,
      "group_min_rank": 4019,
      "major_min_rank": null,
      "safety_margin": "-87.4%"
    }
  ],
  "result_count": 149,
  "executed_filters": [
    {
      "id": "e_major_keyword",
      "field": "专业名称",
      "operator": "contains_any",
      "value": ["计算机"]
    }
  ],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [],
  "evidence_pack": {
    "execution_summary": {
      "executor": "duckdb",
      "sql": "WITH source AS (...) SELECT * FROM projectable ...",
      "params": ["广东", "物理", "计算机"],
      "filtered_row_count": 149
    }
  },
  "debug_trace": {
    "execution": {
      "executor": "duckdb"
    }
  }
}
```

## 示例：needs_confirmation

```json
{
  "status": "needs_confirmation",
  "answer": "根据已验证规则生成结果：...",
  "top_results": [
    {
      "university_name": "香港中文大学(深圳)",
      "group_code": "16407101",
      "major_code": "0700",
      "major_name": "理科试验班",
      "full_major_name": "理科试验班",
      "city": "深圳",
      "tuition": 115000,
      "rank_2024": 968,
      "plan_count": null,
      "group_min_rank": 968,
      "major_min_rank": null,
      "safety_margin": "-97.0%"
    }
  ],
  "result_count": 3962,
  "executed_filters": [
    {
      "id": "e_city",
      "field": "城市",
      "operator": "in_contains",
      "value": ["广州", "深圳"]
    }
  ],
  "candidates_to_confirm": [
    {
      "candidate_id": "cand_d00fc7406ff415b9",
      "source_text": "计科",
      "field": "专业名称",
      "match_type": "partial_match",
      "operator": "contains_any",
      "value": ["计算机"],
      "executable": true
    }
  ],
  "confirmed_rules": [],
  "unconfirmed_candidates": [
    {
      "candidate_id": "cand_d00fc7406ff415b9",
      "source_text": "计科"
    }
  ],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [
    {
      "code": "needs_confirmation",
      "severity": "warning",
      "message": "存在未确认 partial_match candidate，未进入 hard filter。"
    }
  ],
  "evidence_pack": {
    "unconfirmed_candidates": [
      {
        "candidate_id": "cand_d00fc7406ff415b9"
      }
    ]
  },
  "debug_trace": {
    "confirmation_state": {
      "accepted_candidate_ids": []
    }
  }
}
```

## 示例：confirmed rerun

```json
{
  "status": "ok",
  "answer": "根据已验证规则生成结果：...",
  "top_results": [
    {
      "university_name": "中山大学",
      "group_code": "10558219",
      "major_code": "0809",
      "major_name": "计算机类",
      "full_major_name": "计算机类",
      "city": "广州",
      "tuition": 6850,
      "rank_2024": 4019,
      "plan_count": null,
      "group_min_rank": 4019,
      "major_min_rank": null,
      "safety_margin": "-87.4%"
    }
  ],
  "result_count": 149,
  "executed_filters": [
    {
      "id": "e_confirmed_d00fc7406ff415b9",
      "field": "专业名称",
      "operator": "contains_any",
      "value": ["计算机"]
    }
  ],
  "candidates_to_confirm": [],
  "confirmed_rules": [
    {
      "id": "e_confirmed_d00fc7406ff415b9",
      "candidate_id": "cand_d00fc7406ff415b9",
      "field": "专业名称",
      "operator": "contains_any",
      "value": ["计算机"],
      "executed": true
    }
  ],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [],
  "evidence_pack": {
    "confirmed_rules": [
      {
        "rule_id": "e_confirmed_d00fc7406ff415b9",
        "derived_from": "cand_d00fc7406ff415b9"
      }
    ],
    "executed_after_confirmation": ["e_confirmed_d00fc7406ff415b9"]
  },
  "debug_trace": {
    "execution": {
      "hard_rule_ids": ["e_confirmed_d00fc7406ff415b9"]
    }
  }
}
```

## 示例：no_results

```json
{
  "status": "no_results",
  "answer": "共筛选到 0 条符合已执行规则的结果。",
  "top_results": [],
  "result_count": 0,
  "executed_filters": [
    {
      "id": "e_major_keyword",
      "field": "专业名称",
      "operator": "contains_any",
      "value": ["网络安全"]
    }
  ],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [
    {
      "code": "no_results",
      "severity": "warning",
      "message": "SQL 正常执行但 filtered_row_count 为 0，不能生成推荐。"
    }
  ],
  "evidence_pack": {
    "result_count": 0,
    "top_k_results": []
  },
  "debug_trace": {
    "execution": {
      "executor": "duckdb",
      "filtered_row_count": 0
    }
  }
}
```

## 示例：blocked

```json
{
  "status": "blocked",
  "answer": "candidate_id 确认失败，Workbench 未执行 SQL。",
  "top_results": [],
  "result_count": 0,
  "executed_filters": [],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [
    {
      "candidate_id": "cand_forged",
      "reason_code": "candidate_id_not_current_query",
      "blocks_execution": true,
      "reason": "candidate_id 不属于当前 query，或不是系统上一轮生成的候选。"
    }
  ],
  "warnings": [
    {
      "code": "candidate_id_not_current_query",
      "severity": "error",
      "message": "candidate_id 不属于当前 query，或不是系统上一轮生成的候选。"
    }
  ],
  "evidence_pack": {},
  "debug_trace": {
    "execution": {
      "executor": null,
      "sql": "",
      "params": []
    }
  }
}
```

## 示例：error

```json
{
  "status": "error",
  "answer": "Workbench 运行失败，未返回推荐结果。",
  "top_results": [],
  "result_count": 0,
  "executed_filters": [],
  "candidates_to_confirm": [],
  "confirmed_rules": [],
  "unconfirmed_candidates": [],
  "unexecuted_preferences": [],
  "no_schema_field_preferences": [],
  "rejected_confirmations": [],
  "warnings": [
    {
      "code": "workbench_error",
      "severity": "error",
      "message": "Workbench 运行失败，前端不应展示内部异常细节。"
    }
  ],
  "evidence_pack": {},
  "debug_trace": {
    "execution": {
      "sql": ""
    }
  }
}
```
