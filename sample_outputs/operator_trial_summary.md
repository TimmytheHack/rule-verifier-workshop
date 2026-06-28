# Operator Trial 候选摘要

- release candidate：`v0.1.0-rc1`
- run_id：`20260628_143339`
- status：`pass`
- dataset_id：`ds_operator_trial_real_like_admissions_pil`
- sheet_name：`招生数据`
- detected_header_row：`3`
- row_count / column_count：`6` / `25`
- source_fingerprint：`b4aa3bd0b32fb2da4c475da0aa724dab7ca2e6bd40b97893286e1c7bb86f27d0`
- warehouse_fingerprint：`b4aa3bd0b32fb2da4c475da0aa724dab7ca2e6bd40b97893286e1c7bb86f27d0`
- failures：`[]`

## 操作卡点

| stage | status | 说明 |
|---|---|---|
| sheet_header | `needs_review` | 已记录 sheet list、选中 sheet、detected header row 和人工确认点。 |
| schema_profile | `needs_review` | 已记录字段类型、行列规模、warning 和 schema profile 摘要。 |
| review_approval | `pass` | required admissions fields 无缺失，risky fields 已进入人工审查路径。 |
| warehouse | `pass` | DuckDB warehouse 构建完成，source fingerprint 与 warehouse fingerprint 一致。 |
| target_queries | `pass` | `group_detail_report` 返回 1 条专业组明细，score-only `recommendation` 返回 `needs_confirmation` 且不执行 SQL。 |
| trial_closeout | `pass` | failures 为空，常见失败处理已写入报告。 |

## 目标查询

| query_type | status | result_count | 关键证据 |
|---|---|---:|---|
| `group_detail_report` | `ok` | 1 | 返回深圳大学专业组及组内专业最低分/位次明细。 |
| `recommendation` | `needs_confirmation` | 0 | 保留 `score_without_rank` warning，SQL 为空，要求补充广东省排位/位次。 |

## 人工结论

该候选 run 覆盖 upload -> profile -> draft -> review -> approve -> build warehouse ->
query 的完整 operator trial 路径。正式发布前仍应读取对应 `report.json` 中的
`missing_fields`、`risky_fields`、`warnings`、`EvidencePack`、SQL/params 和 fingerprint
guard 结果；如果换成真实招生 Excel，必须重新运行 trial 并更新本摘要或 release notes。
