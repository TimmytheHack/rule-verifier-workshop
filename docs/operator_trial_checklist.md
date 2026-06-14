# Operator Trial Checklist

本文用于真实招生 Excel/CSV 接入前的人工试运行。目标不是让 LLM 自动审批，而是让 operator 按固定步骤确认上传、profile、review、approve、build warehouse 和目标查询能安全跑通。

## 运行命令

使用真实文件：

```bash
.venv/bin/python scripts/run_operator_trial.py path/to/admissions.xlsx
```

使用内置 fixture：

```bash
make operator-trial
```

输出目录：

```text
outputs/operator_trial/<run_id>/report.md
outputs/operator_trial/<run_id>/report.json
```

## 试运行步骤

| 步骤 | 检查项 | 通过标准 |
|---|---|---|
| upload | 文件扩展名、大小、sheet list、row/column summary | `operation_cards[].stage=upload` 为 `pass` 或只有可解释 warning。 |
| header detection | `detected_header_row`、`header_detection_status` | 表头行与人工观察一致；不确定时记录卡点。 |
| profile | dtype、空值率、唯一值数量、样例值、数值范围 | 字段事实可审查，没有静默丢列。 |
| review summary | required fields、missing fields、risky fields | `missing_fields` 为空或明确记录阻断原因；risky fields 已人工判断。 |
| approve domain | 只批准已审查 admissions template | 不把 generator seed ops 直接变为 executable hard filters。 |
| build warehouse | DuckDB、schema/value index、source fingerprint | `warehouse_fingerprint` 与 source 一致，状态 queryable。 |
| group detail query | 深圳大学 2025 专业组明细 | `query_type=group_detail_report`，EvidencePack 有 SQL、params、metric。 |
| recommendation query | 630 分、AI/计算机、广东、不去国外 | `query_type=recommendation`；只有分数无位次时必须有 warning。 |
| evidence | EvidencePack 和 warnings | 不暴露 stack trace、secret、环境变量或危险绝对路径。 |

## 必看字段

在 `report.json` 中重点检查：

- `source_path`
- `dataset_id`
- `source_fingerprint`
- `sheet_summaries`
- `detected_header_row`
- `schema_profile_summary`
- `review_summary`
- `review_blockers`
- `missing_fields`
- `risky_fields`
- `safe_auto_suggest_approvals`
- `manual_approval_fixture`
- `approved_fields`
- `blocked_fields`
- `warehouse_path`
- `warehouse_fingerprint`
- `target_query_results`
- `operation_cards`
- `warnings`
- `failures`

## 阻断条件

出现以下情况时，不进入生产 queryable：

- `status=fail`；
- `failures` 非空；
- `missing_fields` 包含目标 query 必需字段；
- 分数字段语义不清，无法区分 `group_min_score` / `major_min_score`；
- 位次字段缺失但 recommendation 仍声称录取概率；
- warehouse fingerprint 不一致；
- `draft` / `needs_review` domain pack 被执行 SQL；
- `no_schema_field_preferences` 被执行；
- 报告或错误中出现 stack trace、secret、环境变量或危险绝对路径。

## 试运行结论

operator 应在反馈模板中记录：

- 是否允许进入下一步 demo acceptance / quality gate；
- 哪些字段需要人工映射或 block；
- 哪些 warnings 可以接受；
- 哪些 failures 必须修复；
- 是否需要重新上传、换 sheet、修正表头或更新 domain pack review。
