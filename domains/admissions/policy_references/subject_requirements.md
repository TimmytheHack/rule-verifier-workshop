# 选科要求说明

status: approved

招生专业通常会设置首选科目和再选科目要求。结构化查询只能使用 domain pack 中
已审核的 `subject_type`、`subject_requirement` 或等价 canonical field。用户没有提供
科类或再选科目时，系统应返回 warning，并说明结果未按这些条件过滤。

自然语言中的“物理类”“化学”“生物”等词可以作为 slot 或 candidate 进入审查流程，
但不能绕过 RuleVerifier 直接改变 SQL。
