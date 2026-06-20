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
| recommendation query | 630 分、AI/计算机、广东、不去国外 | `query_type=recommendation`；只有分数无位次时必须为 `status=needs_confirmation`、`result_count=0`、SQL 为空，并带 `score_without_rank` warning。 |
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
- `manual_checkpoints`
- `failure_playbook`
- `operation_cards`
- `warnings`
- `failures`

`source_path`、`warehouse_path`、`operation_cards`、`manual_checkpoints` 和 `artifacts`
里的 path-like 字段应为相对路径或文件名，不应出现本机绝对路径。

## 人工卡点处理

`manual_checkpoints` 是报告中面向人工收敛的摘要层。operator 应逐项确认：

| checkpoint | 必做动作 | 不通过处理 |
|---|---|---|
| `sheet_header` | 核对 selected sheet、sheet summary、`detected_header_row` 和原表是否一致。 | 换 `--sheet-name`、清理说明行或重新上传。 |
| `schema_profile` | 核对 dtype、空值率、唯一值数量、样例值和数值范围。 | 标记字段为 needs-review；明显错型时先修源表或补 schema mapping。 |
| `review_approval` | 核对 missing/risky fields、safe auto suggestions 和 manual approval fixture。 | missing 必须补映射或记录 blocker；risky 必须 approve/block。 |
| `warehouse` | 核对 warehouse 状态、fingerprint 和 schema/value index。 | 非 queryable 或 fingerprint 不一致时重建；仍失败则重新上传。 |
| `target_queries` | 核对两条目标 query 的 `query_type`、SQL/params、result_count 和 EvidencePack。 | blocked/error 或结果不符合人工预期时阻断发布。 |
| `trial_closeout` | 汇总可接受 warnings、必须修复 warnings、owner 和下一步结论。 | 未给出人工结论前不进入 release tag。 |

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

## 常见失败处理

| 现象 | 可能原因 | 处理建议 |
|---|---|---|
| `header_detection_status` 不是 `ok`。 | 表头前存在标题、说明、合并单元格或空行。 | 人工确认表头行；必要时清理源表或用 `--sheet-name` 指定正确 sheet 后重跑。 |
| `missing_fields` 非空。 | 源列名无法映射到 admissions canonical field。 | 补字段映射或记录 blocker；不能强行 `approve-domain`。 |
| `risky_fields` 非空。 | 字段存在 PII、高基数、自由文本或特殊计划语义。 | 逐字段 approve/block；未审查字段不能成为 hard filter。 |
| `approve_domain` 失败。 | required checks 未满足或 review.yaml 不完整。 | 查看 `review_blockers`，补 title/primary/sort/field approval 后重跑。 |
| warehouse fingerprint 不一致。 | 源文件被替换、warehouse 过期或构建中断。 | 重新 build；仍失败时重新上传并完整重跑 review。 |
| recommendation 没有 `score_without_rank` warning。 | 只有分数无位次时仍试图做风险判断。 | 阻断发布，修 admissions recommendation guard 和测试。 |
| 答案声称录取概率。 | Answer/EvidencePack 口径越界。 | 阻断发布，修模板或 evidence-only answer guard。 |
| `no_schema_field_preferences` 被执行。 | verifier 或 confirmation guard 失效。 | 阻断发布，补测试并修 RuleVerifier / confirmation flow。 |
| 报告包含 secret、环境变量或 stack trace。 | 错误净化不完整。 | 不共享报告，先修 redaction，再重新生成。 |

## 试运行结论

operator 应在反馈模板中记录：

- 是否允许进入下一步 demo acceptance / quality gate；
- 哪些字段需要人工映射或 block；
- 哪些 warnings 可以接受；
- 哪些 failures 必须修复；
- 是否需要重新上传、换 sheet、修正表头或更新 domain pack review。
