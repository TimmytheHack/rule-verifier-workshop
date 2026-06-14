# 合作办学与境外培养说明

status: approved

招生数据中如果没有经过审查的 `cooperation_type`、`school_country_or_region`
或同等字段，系统不能执行“排除中外合作”“不要境外培养”“不想去国外”之类的
hard filter。此类偏好应进入 `no_schema_field_preferences`，只能作为未执行说明
或人工审查线索。

如果后续 domain pack 增加并批准了合作办学类型、培养地点或境外培养字段，才能由
RuleVerifier 校验 operator 和 value 后进入参数化 SQL。
