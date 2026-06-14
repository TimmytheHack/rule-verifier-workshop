# Real Dataset Pilot

`scripts/run_real_dataset_pilot.py` 用于在真实招生 CSV/Excel 进入生产前，跑一遍可审计的上传、审查、建仓和查询验收流程。它不接 Qwen、BGE 或向量库，也不会把自然语言直接变成 hard filter。

在 functional tool layer 中，同一能力通过 `pilot.run` 暴露为 diagnostics tool。`pilot.run` 不是 LLM-safe tool；它会写报告和临时 uploaded dataset artifacts，必须由具备 `diagnostics` 权限的调用方触发。发布前建议顺序为：`make demo` -> `make pilot` -> `make quality`。pilot 通过不等于 production 可用；最终仍以 Quality Gate 和人工 review/approval 结果为准。

## 命令

使用真实文件：

```bash
python scripts/run_real_dataset_pilot.py path/to/admissions.xlsx
```

使用内置 real-like fixture：

```bash
python scripts/run_real_dataset_pilot.py --fixture
```

也可以通过发布入口运行：

```bash
make pilot
```

可选指定 sheet：

```bash
python scripts/run_real_dataset_pilot.py path/to/admissions.xlsx --sheet-name 招生数据
```

输出固定为：

```text
outputs/real_dataset_pilot/report.md
outputs/real_dataset_pilot/report.json
```

面向 operator 的人工试运行使用相同 uploaded dataset、review、warehouse 和 Workbench
能力，但报告按一次操作会话分目录保存，并额外记录操作卡点：

```bash
python scripts/run_operator_trial.py path/to/admissions.xlsx
make operator-trial
```

输出为：

```text
outputs/operator_trial/<run_id>/report.md
outputs/operator_trial/<run_id>/report.json
```

operator trial 适合真实 Excel 第一次接入前人工检查 sheet/header/profile/review/approve/build/query
链路；real dataset pilot 适合发布前固定验收。

## 流程

pilot 按顺序执行：

```text
upload
-> profile
-> generate draft domain pack
-> review summary
-> safe auto-suggest approvals
-> manual approval fixture
-> build warehouse
-> run target admissions queries
-> generate pilot report
```

`safe auto-suggest approvals` 只是报告里的审查建议，不会把 generator seed ops 自动提升为 executable hard filters。真实执行仍依赖已审查 admissions template、`approve-domain`、DuckDB warehouse 和 fingerprint guard。

## Excel ingestion hardening

上传 Excel 时，ingestion 会返回：

- 所有 sheet 的 `row_count`、`column_count`、`non_empty_cells` 和 `selected`；
- 默认选择第一个非空 sheet；
- `detected_header_row` 和 `header_detection_status`；
- 重复列名安全化后的 `original_column_mapping`；
- 空列、全空行、列名换行、首尾空格、中文括号清理结果；
- 合并单元格、隐藏行列、公式单元格 structured warnings；
- 文件过大、列过多、行过多的 structured warning/error。

如果表头检测不确定，会返回 `header_row_detection_needs_review`，后续审查页面应要求人工确认。

## Admissions 字段审计

schema profiling 会记录 admissions 语义候选，包括：

- `score`、`min_score`、`group_min_score`、`major_min_score`；
- `rank`、`min_rank`、`group_min_rank`、`major_min_rank`；
- `university_name`、`college_name`；
- `school_location`、`admission_province`；
- `中外合作`、`国际班`、`境外培养`、`合作办学`、`校企合作`、`地方专项`、`专项计划` 等字段风险。

这些只用于 review 和 planner guard。字段没有进入 approved schema 时，不能执行对应 hard filter。

## 目标查询

pilot 固定跑两条 admissions query：

```text
列出25年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数
```

该查询应返回 `query_type=group_detail_report`。`EvidencePack.execution_summary` 必须记录参数化 SQL、params、`group_by`、`metric`、`sort` 和 `nested_result_count`。

```text
假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐
```

该查询应返回 `query_type=recommendation`。如果只有分数没有位次，必须给出 `score_without_rank` warning，并且回答不能声称录取概率。`不想去国外`、`中外合作`、`境外培养`、`专项计划` 等偏好只有在对应已审核字段存在时才执行，否则进入 `no_schema_field_preferences`。

## 报告字段

`report.json` 顶层包含：

- `status`
- `source_path`
- `dataset_id`
- `source_fingerprint`
- `sheet_name`
- `row_count` / `column_count`
- `detected_header_row`
- `schema_profile_summary`
- `risky_fields`
- `required_fields`
- `missing_fields`
- `safe_auto_suggest_approvals`
- `manual_approval_fixture`
- `approved_fields`
- `blocked_fields`
- `warehouse_path`
- `warehouse_fingerprint`
- `target_query_results`
- `warnings`
- `failures`

任何目标 query 返回 `error`、缺少必要 warning，或报告出现 failure 时，pilot 退出码为非 0。
