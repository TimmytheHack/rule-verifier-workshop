# Operator Trial 摘要示例

- status：`pass`
- dataset_id：`ds_operator_trial_real_like_admissions`
- sheet_name：`招生数据`
- detected_header_row：`3`
- row_count / column_count：`6` / `25`
- warehouse_fingerprint：`example-fingerprint`

## 操作卡点

| stage | status | 说明 |
|---|---|---|
| upload | `warning` | 检测到合并单元格、隐藏行和公式单元格，已写入 structured warnings。 |
| generate_draft_domain_pack | `pass` | 生成 draft domain pack 和 schema profile。 |
| profile | `pass` | 字段类型、空值率、唯一值数量和样例值可审查。 |
| review_summary | `pass` | admissions required fields 未缺失。 |
| approve_domain | `pass` | 使用已审查 admissions template 批准 domain。 |
| build_warehouse | `pass` | DuckDB warehouse 和 source fingerprint 一致。 |
| target_query_1 | `pass` | `group_detail_report` 返回专业组和组内专业明细。 |
| target_query_2 | `pass` | `recommendation` 返回冲/稳/保分组，并保留 `score_without_rank` warning。 |

## 人工结论

该示例只展示报告摘要形状。真实 operator trial 必须检查 `report.json` 中的
`missing_fields`、`risky_fields`、`warnings`、`failures`、`EvidencePack`、SQL/params 和
fingerprint guard 结果，再决定是否进入 demo acceptance、real dataset pilot 和 Quality Gate。
