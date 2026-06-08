"""Row-level trace generation."""

from __future__ import annotations

from typing import Any


class TraceGenerator:
    """Adds audit traces to result rows."""

    def add_traces(
        self,
        rows: list[dict[str, Any]],
        executable_rules: list[dict[str, Any]] | None = None,
        not_executed_preferences: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        traced = []
        for row in rows:
            output_row = dict(row)
            output_row["trace"] = _rule_traces(row, executable_rules or [])
            output_row["trace"].extend(
                _not_executed_traces(not_executed_preferences or [])
            )
            traced.append(output_row)
        return traced


def _rule_traces(
    row: dict[str, Any],
    executable_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    traces = []
    for rule in executable_rules:
        traces.append(
            {
                "rule_id": rule.get("rule_id"),
                "status": "pass",
                "reason": _rule_reason(row, rule),
            }
        )
    return traces


def _rule_reason(row: dict[str, Any], rule: dict[str, Any]) -> str:
    field = rule.get("field")
    operator = rule.get("operator")
    value = rule.get("value")
    actual = row.get(str(field))
    if operator == "eq":
        return f"{field} 等于 {_format_value(value)}"
    if operator == "neq":
        return f"{field} 不等于 {_format_value(value)}"
    if operator == "contains":
        return f"{field} 包含 {_format_value(value)}"
    if operator in {"in_contains", "contains_any"}:
        return f"{field} 包含任一：{_format_value(value)}；命中 {actual}"
    if operator == "in":
        return f"{field} 属于：{_format_value(value)}"
    if operator == "not_in":
        return f"{field} 不属于：{_format_value(value)}"
    if operator == "satisfies_subject_requirement":
        return f"{field} {actual or '不限'}；已选再选科目：{_format_value(value)}"
    if operator == ">=":
        if field == "专业组最低位次1":
            return (
                f"{field} {_format_number(actual)} 在 {_format_value(value)} 名及以后"
                f"（数值 >= {_format_value(value)}）"
            )
        return f"{field} {_format_number(actual)} 不低于 {_format_value(value)}"
    if operator == "<=":
        if field == "专业组最低位次1":
            return (
                f"{field} {_format_number(actual)} 在 {_format_value(value)} 名以内"
                f"（数值 <= {_format_value(value)}）"
            )
        return f"{field} {_format_number(actual)} 不高于 {_format_value(value)}"
    if operator == "between":
        if field == "专业组最低位次1":
            return (
                f"{field} {_format_number(actual)} 位于 "
                f"{_format_rank_window(value)}的窗口内"
            )
        return f"{field} {_format_number(actual)} 位于 {_format_value(value)} 之间"
    return f"{field} {operator} {_format_value(value)}"


def _not_executed_traces(
    not_executed_preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    traces = []
    for index, preference in enumerate(not_executed_preferences, start=1):
        source_text = preference.get("source_text") or "该偏好"
        reason = _sanitize_reason(preference.get("reason") or "缺少可执行依据")
        traces.append(
            {
                "rule_id": preference.get("part_id") or f"not_executed_{index}",
                "status": "not_executed",
                "reason": f"{source_text} 未执行：{reason}",
            }
        )
    return traces


def _format_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _format_rank_window(value: Any) -> str:
    if isinstance(value, list) and len(value) == 2:
        return f"{_format_value(value[0])}-{_format_value(value[1])} 名"
    return f"{_format_value(value)} 名"


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sanitize_reason(reason: Any) -> str:
    text = str(reason)
    replacements = {
        "Missing dedicated cooperation_type field. No text-field inference is used in this MVP.": (
            "缺少合作办学类型字段，未使用文本字段推断。"
        ),
        "Missing dedicated cooperation_type field.": "缺少合作办学类型字段。",
        "No dedicated school country or overseas study field.": (
            "缺少国家或境外办学字段。"
        ),
        "cooperation_type": "合作办学类型字段",
        "school_country_or_region": "国家或境外办学字段",
        "schema": "数据字段定义",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text
