"""Verified evidence package for answer generation.

The report layer receives compact, traced evidence. It must not read raw Excel
or decide whether a preference can execute.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidencePack:
    """Serializable evidence passed to deterministic and optional LLM answers."""

    user_request: str
    executed_rules: list[dict[str, Any]]
    candidate_confirmations: list[dict[str, Any]]
    not_executed_preferences: list[dict[str, Any]]
    result_count: int
    top_k_results: list[dict[str, Any]]
    trace_summary: dict[str, Any]
    extracted_preferences: list[dict[str, Any]] = field(default_factory=list)
    attribute_grounding_summary: dict[str, Any] = field(default_factory=dict)
    proposed_rule_audit: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_verified_pipeline(
        cls,
        user_request: str,
        executed_rules: list[dict[str, Any]],
        classified_rules: dict[str, Any],
        traced_results: list[dict[str, Any]],
        top_k: int = 5,
        extracted_preferences: list[dict[str, Any]] | None = None,
        attribute_grounding: dict[str, Any] | None = None,
        proposed_rules: list[dict[str, Any]] | None = None,
    ) -> "EvidencePack":
        """Build an answer-safe evidence pack from post-execution artifacts."""

        compact_rules = [_compact_rule(rule) for rule in executed_rules]
        confirmations = _candidate_confirmations(classified_rules)
        not_executed = _not_executed_preferences(classified_rules)
        top_results = [
            _compact_result(rank, row)
            for rank, row in enumerate(traced_results[:top_k], start=1)
        ]
        trace_summary = _trace_summary(
            executed_rules=compact_rules,
            traced_results=traced_results,
            not_executed_preferences=not_executed,
            top_k=top_k,
        )
        return cls(
            user_request=user_request,
            executed_rules=compact_rules,
            candidate_confirmations=confirmations,
            not_executed_preferences=not_executed,
            result_count=len(traced_results),
            top_k_results=top_results,
            trace_summary=trace_summary,
            extracted_preferences=extracted_preferences or [],
            attribute_grounding_summary=(attribute_grounding or {}).get("summary", {}),
            proposed_rule_audit=_compact_proposed_rule_audit(proposed_rules or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_to_dict(evidence_pack: EvidencePack | dict[str, Any]) -> dict[str, Any]:
    """Normalize an evidence pack object or plain dictionary."""

    if isinstance(evidence_pack, EvidencePack):
        return evidence_pack.to_dict()
    return dict(evidence_pack)


def _compact_rule(rule: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "rule_id": rule.get("rule_id"),
        "derived_from": rule.get("derived_from"),
        "field": rule.get("field"),
        "operator": rule.get("operator"),
        "value": rule.get("value"),
    }
    for optional_key in ["confirmation", "normalization"]:
        if optional_key in rule:
            compact[optional_key] = rule[optional_key]
    compact["description"] = _rule_description(compact)
    return compact


def _compact_proposed_rule_audit(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for rule in rules:
        verification = rule.get("verification", {})
        compact.append(
            {
                "rule_id": rule.get("rule_id"),
                "source_text": rule.get("source_text"),
                "field": rule.get("field"),
                "operator": rule.get("operator"),
                "value": rule.get("value"),
                "terminal_status": verification.get("terminal_status"),
                "executable": bool(verification.get("executable")),
            }
        )
    return compact


def _candidate_confirmations(classified_rules: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_by_id = {
        rule["rule_id"]: rule for rule in classified_rules.get("candidate_rules", [])
    }
    question_source_by_id = {
        question["question_id"]: question.get("source_text")
        for question in classified_rules.get("confirmation_questions", [])
    }
    simulated = classified_rules.get("simulated_confirmations", {})
    mapping = {
        "safety_margin": "c_safety_margin",
        "tuition_threshold": "c_tuition_cap",
        "major_expansion": "c_major_expansion",
    }
    confirmations: list[dict[str, Any]] = []
    for confirmation_id, confirmation in simulated.items():
        source_rule_id = mapping.get(confirmation_id)
        source_rule = candidate_by_id.get(source_rule_id, {})
        record = {
            "confirmation_id": confirmation_id,
            "source_rule_id": source_rule_id,
            "source_text": _confirmation_source_text(
                confirmation_id=confirmation_id,
                source_rule=source_rule,
                question_source_by_id=question_source_by_id,
            ),
            "selected_label": confirmation.get("label"),
            "selected_option": confirmation.get("selected_option"),
            "status": _confirmation_status(confirmation_id, confirmation),
        }
        if confirmation.get("field"):
            record["field"] = confirmation["field"]
            record["operator"] = confirmation.get("operator")
            record["value"] = confirmation.get("value")
            record["description"] = _rule_description(record)
        if confirmation.get("expanded_terms") is not None:
            record["expanded_terms"] = confirmation["expanded_terms"]
        if confirmation.get("reason"):
            record["reason"] = _user_facing_reason(confirmation["reason"])
        confirmations.append(record)
    return confirmations


def _confirmation_source_text(
    confirmation_id: str,
    source_rule: dict[str, Any],
    question_source_by_id: dict[str, Any],
) -> str | None:
    if source_rule.get("source_text"):
        return source_rule["source_text"]
    question_id_by_confirmation = {
        "safety_margin": "q_safety_margin",
        "tuition_threshold": "q_tuition_cap",
        "major_expansion": "q_major_expansion",
    }
    question_id = question_id_by_confirmation.get(confirmation_id)
    if question_id and question_source_by_id.get(question_id):
        return str(question_source_by_id[question_id])
    if confirmation_id == "cooperation_type":
        return "不想去太贵的中外合作"
    return None


def _confirmation_status(confirmation_id: str, confirmation: dict[str, Any]) -> str:
    if confirmation.get("status") == "not_executable":
        return "not_executable"
    if confirmation_id == "major_expansion" and not confirmation.get("expanded_terms"):
        return "confirmed_without_expansion"
    return "promoted_to_executed_rule"


def _not_executed_preferences(classified_rules: dict[str, Any]) -> list[dict[str, Any]]:
    preferences: list[dict[str, Any]] = []
    seen_source_text: set[str] = set()

    for preference in classified_rules.get("non_executable_preferences", []):
        record = {
            "source_text": preference.get("source_text"),
            "status": preference.get("status", "not_executed"),
            "reason": _user_facing_reason(preference.get("reason")),
        }
        record["safety_warning"] = _not_executed_warning(record)
        preferences.append(record)
        if record["source_text"]:
            seen_source_text.add(record["source_text"])

    for part in classified_rules.get("llm_needed_parts", []):
        source_text = part.get("source_text")
        if source_text in seen_source_text:
            continue
        verification = part.get("verification", {})
        if verification.get("executable"):
            continue
        record = {
            "source_text": source_text,
            "status": part.get("status", "not_executed"),
            "reason": _user_facing_reason(part.get("reason") or part.get("trace_reason")),
            "field_id": part.get("field_id"),
        }
        record["safety_warning"] = _not_executed_warning(record)
        preferences.append(record)
    return preferences


def _not_executed_warning(preference: dict[str, Any]) -> str:
    source_text = preference.get("source_text") or "该偏好"
    reason = preference.get("reason") or "缺少可验证依据"
    return f"{source_text} 未执行：{reason}"


def _user_facing_reason(reason: Any) -> str | None:
    if reason is None:
        return None
    text = str(reason)
    replacements = {
        "Missing dedicated cooperation_type field. No text-field inference is used in this MVP.": (
            "缺少合作办学类型字段，未使用文本字段推断。"
        ),
        "Missing dedicated cooperation_type field.": "缺少合作办学类型字段。",
        "The schema registry has no dedicated cooperation_type field.": (
            "当前数据字段定义缺少合作办学类型字段。"
        ),
        "No dedicated cooperation_type field, so the preference is preserved but not executed.": (
            "缺少合作办学类型字段，因此该偏好已保留但未执行。"
        ),
        "No reviewed active school reputation field.": "当前数据中没有已审查的学校声誉字段。",
        "No reviewed active school ranking field.": "当前数据中没有已审查的学校排名字段。",
        "No reviewed active school quality field.": "当前数据中没有已审查的学校质量字段。",
        "No reviewed active school ownership field in MVP schema.": (
            "当前数据中没有已审查的办学性质字段。"
        ),
        "No employment outcome field.": "当前数据中没有就业结果字段。",
        "No home location or distance field.": "当前数据中没有家庭位置或距离字段。",
        "No reviewed active remoteness field.": "当前数据中没有已审查的偏远程度字段。",
        "No major popularity field.": "当前数据中没有专业热度字段。",
        "No admission probability field.": "当前数据中没有录取概率字段。",
        "Needs confirmed city set.": "需要确认具体城市集合。",
        "Needs confirmed Pearl River Delta city set.": "需要确认珠三角城市集合。",
        "Needs confirmed city quality proxy or city set.": (
            "需要确认城市质量代理字段或具体城市集合。"
        ),
        "Conflicts with city preference and needs confirmation.": (
            "与城市偏好可能冲突，需要确认。"
        ),
        "cooperation_type": "合作办学类型字段",
        "schema registry": "数据字段定义",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _compact_result(rank: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": rank,
        "院校名称": row.get("院校名称"),
        "院校专业组代码": row.get("院校专业组代码"),
        "专业代码": row.get("专业代码"),
        "专业名称": row.get("专业名称"),
        "专业全称": row.get("专业全称"),
        "选科要求": row.get("选科要求"),
        "城市": row.get("城市"),
        "学费": row.get("学费"),
        "专业组最低位次": row.get("专业组最低位次1"),
        "专业最低位次": row.get("最低位次1"),
        "safety_margin": _format_percent(row.get("safety_margin_pct")),
        "trace": row.get("trace", []),
    }


def _trace_summary(
    executed_rules: list[dict[str, Any]],
    traced_results: list[dict[str, Any]],
    not_executed_preferences: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for row in traced_results[:top_k]:
        for trace_item in row.get("trace", []):
            status = str(trace_item.get("status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1

    safety_warnings = [
        (
            "答案只能使用 evidence_pack 中的已验证规则、确认记录、"
            "结果摘要和 trace。"
        ),
        "候选偏好在确认或模拟确认之前不得执行。",
    ]
    safety_warnings.extend(
        preference["safety_warning"]
        for preference in not_executed_preferences
        if preference.get("safety_warning")
    )

    return {
        "executed_rule_ids": [rule.get("rule_id") for rule in executed_rules],
        "not_executed_preference_count": len(not_executed_preferences),
        "traced_result_count": len(traced_results),
        "top_k": min(top_k, len(traced_results)),
        "top_k_trace_status_counts": status_counts,
        "safety_warnings": safety_warnings,
    }


def _rule_description(rule: dict[str, Any]) -> str:
    field = rule.get("field")
    operator = rule.get("operator")
    value = rule.get("value")
    if operator == "eq":
        return f"{field} 等于 {_format_value(value)}"
    if operator == "neq":
        return f"{field} 不等于 {_format_value(value)}"
    if operator == "contains":
        return f"{field} 包含 {_format_value(value)}"
    if operator in {"in_contains", "contains_any"}:
        return f"{field} 包含任一：{_format_value(value)}"
    if operator == "in":
        return f"{field} 属于：{_format_value(value)}"
    if operator == "not_in":
        return f"{field} 不属于：{_format_value(value)}"
    if operator == "satisfies_subject_requirement":
        return f"{field} 满足已选再选科目：{_format_value(value)}"
    if operator == ">=":
        if field == "专业组最低位次1":
            return (
                f"{field} 在 {_format_value(value)} 名及以后"
                f"（数值 >= {_format_value(value)}）"
            )
        return f"{field} 不低于 {_format_value(value)}"
    if operator == "<=":
        if field == "专业组最低位次1":
            return (
                f"{field} 在 {_format_value(value)} 名以内"
                f"（数值 <= {_format_value(value)}）"
            )
        return f"{field} 不高于 {_format_value(value)}"
    if operator == "between":
        if field == "专业组最低位次1":
            return f"{field} 位于 {_format_rank_window(value)}的窗口内"
        return f"{field} 位于 {_format_value(value)} 之间"
    return f"{field} {operator} {_format_value(value)}"


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


def _format_percent(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return None
