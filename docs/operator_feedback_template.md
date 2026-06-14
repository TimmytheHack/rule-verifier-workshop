# Operator Feedback Template

用于记录一次真实招生 Excel/CSV operator trial 的人工结论。请不要粘贴密钥、环境变量、完整原始表格或未脱敏个人信息。

## 基本信息

- trial run_id：
- operator：
- 日期：
- source 文件名：
- sheet_name：
- dataset_id：
- source_fingerprint：
- report 路径：

## 上传与表头

- sheet list 是否符合预期：
- selected sheet 是否正确：
- detected_header_row 是否正确：
- 是否存在合并单元格 warning：
- 是否存在隐藏行列 warning：
- 是否存在公式单元格 warning：
- 是否存在重复列名 / 空列 / 全空行：
- 处理意见：

## Profile 审查

- row_count / column_count：
- dtype 判断是否明显错误：
- 数值范围是否合理：
- 高空值字段：
- 高基数字段：
- 自由文本字段：
- PII / 敏感字段：
- 处理意见：

## Admissions 必需字段

| canonical field | 状态 | 备注 |
|---|---|---|
| `year` |  |  |
| `university_name` |  |  |
| `group_code` |  |  |
| `major_code` |  |  |
| `major_name` |  |  |
| `school_location` / `city` |  |  |
| `group_min_score` |  |  |
| `major_min_score` |  |  |
| `group_min_rank` |  |  |
| `major_min_rank` |  |  |

## 风险字段

- `中外合作` / `国际班` / `境外培养`：
- `校企合作`：
- `地方专项` / `专项计划`：
- 其他 special plan 字段：
- 是否 approved：
- 未 approved 时是否进入 `no_schema_field_preferences`：

## Approve / Block 记录

- approved_fields：
- approved_ops：
- blocked_fields：
- blocked_ops：
- default safe sort：
- 人工审批备注：

## Warehouse

- warehouse_path：
- warehouse_fingerprint：
- schema_value_index_path：
- fingerprint guard 是否通过：
- 是否需要重建：

## 目标查询

### group_detail_report

- query：
- status：
- result_count：
- metric：
- group_by：
- sort：
- nested_result_count：
- SQL/params 是否存在且参数化：
- 结果是否符合人工预期：
- 问题：

### recommendation

- query：
- status：
- result_count：
- 是否有 `score_without_rank` warning：
- 是否避免“录取概率”表述：
- `no_schema_field_preferences` 是否正确保留：
- 中外合作/境外培养等偏好是否只在 approved 字段存在时执行：
- 冲/稳/保分组是否可解释：
- 问题：

## Warnings / Failures

- 可接受 warnings：
- 必须修复 warnings：
- failures：
- blocked 原因：
- 是否需要重新上传：

## 常见失败处理记录

| 现象 | 是否出现 | 处理结论 | owner |
|---|---|---|---|
| `header_detection_status` 不是 `ok` |  |  |  |
| selected sheet 不正确 |  |  |  |
| `missing_fields` 非空 |  |  |  |
| `risky_fields` 未 approve/block |  |  |  |
| `approve_domain` 失败 |  |  |  |
| warehouse fingerprint 不一致 |  |  |  |
| recommendation 缺少 `score_without_rank` warning |  |  |  |
| 答案声称录取概率 |  |  |  |
| `no_schema_field_preferences` 被执行 |  |  |  |
| 报告包含 secret / 环境变量 / stack trace |  |  |  |

## 人工卡点结论

| checkpoint | 状态 | 人工结论 | 后续动作 |
|---|---|---|---|
| `sheet_header` |  |  |  |
| `schema_profile` |  |  |  |
| `review_approval` |  |  |  |
| `warehouse` |  |  |  |
| `target_queries` |  |  |  |
| `trial_closeout` |  |  |  |

## 结论

- 是否通过 operator trial：
- 是否允许进入 demo acceptance：
- 是否允许进入 Quality Gate：
- 是否允许进入 production use：
- 下一步 owner：
- 截止时间：
