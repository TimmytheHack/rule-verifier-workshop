"""Verified evidence package for answer generation.

The report layer receives compact, traced evidence. It must not read raw Excel
or decide whether a preference can execute.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.domains import DomainConfig


def _default_decision_guidance() -> dict[str, Any]:
    return {
        "status": "reference_only",
        "execution_effect": "does_not_change_sql_or_results",
        "executable": False,
        "matched_rules": [],
        "information_requests": [],
        "no_schema_field_preferences": [],
    }


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
    execution_summary: dict[str, Any] = field(default_factory=dict)
    attribute_explanations: list[dict[str, Any]] = field(default_factory=list)
    confirmed_rules: list[dict[str, Any]] = field(default_factory=list)
    confirmation_source: list[dict[str, Any]] = field(default_factory=list)
    executed_after_confirmation: list[str] = field(default_factory=list)
    unconfirmed_candidates: list[dict[str, Any]] = field(default_factory=list)
    no_schema_field_preferences: list[dict[str, Any]] = field(default_factory=list)
    rejected_confirmations: list[dict[str, Any]] = field(default_factory=list)
    policy_references: list[dict[str, Any]] = field(default_factory=list)
    decision_guidance: dict[str, Any] = field(
        default_factory=_default_decision_guidance
    )
    answerable_intents: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)
    verified_query_plan: dict[str, Any] = field(default_factory=dict)
    capability_graph_summary: dict[str, Any] = field(default_factory=dict)
    entity_linking: dict[str, Any] = field(default_factory=dict)

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
        execution_summary: dict[str, Any] | None = None,
        confirmation_state: dict[str, Any] | None = None,
        domain_config: DomainConfig | None = None,
        policy_references: list[dict[str, Any]] | None = None,
        decision_guidance: dict[str, Any] | None = None,
        entity_linking: dict[str, Any] | None = None,
    ) -> "EvidencePack":
        """Build an answer-safe evidence pack from post-execution artifacts."""

        domain_config = domain_config or DomainConfig.load()
        compact_rules = [_compact_rule(rule, domain_config) for rule in executed_rules]
        execution = execution_summary or {}
        confirmation = confirmation_state or classified_rules.get("confirmation_state") or {}
        guidance = decision_guidance or _default_decision_guidance()
        base_no_schema_preferences = confirmation.get(
            "no_schema_field_preferences",
            [],
        )
        guidance_no_schema_preferences = _guidance_no_schema_preferences(
            guidance,
            existing_preferences=base_no_schema_preferences,
        )
        guidance_not_executed = _guidance_not_executed_preferences(
            guidance,
            guidance_no_schema_preferences,
        )
        confirmations = _candidate_confirmations(
            classified_rules,
            execution,
            domain_config,
        )
        not_executed = (
            _not_executed_preferences(classified_rules)
            + guidance_not_executed
        )
        top_results = [
            _compact_result(rank, row, domain_config)
            for rank, row in enumerate(traced_results[:top_k], start=1)
        ]
        trace_summary = _trace_summary(
            executed_rules=compact_rules,
            traced_results=traced_results,
            not_executed_preferences=not_executed,
            top_k=top_k,
        )
        explanations = _attribute_explanations(
            attribute_grounding=attribute_grounding or {},
            executed_rules=compact_rules,
            confirmation_state=confirmation,
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
            execution_summary=execution,
            attribute_explanations=explanations,
            confirmed_rules=[
                _compact_rule(rule, domain_config)
                for rule in confirmation.get("confirmed_rules", [])
            ],
            confirmation_source=confirmation.get("confirmation_source", []),
            executed_after_confirmation=confirmation.get(
                "executed_after_confirmation",
                [],
            ),
            unconfirmed_candidates=confirmation.get("unconfirmed_candidates", []),
            no_schema_field_preferences=(
                base_no_schema_preferences
                + guidance_no_schema_preferences
            ),
            rejected_confirmations=confirmation.get("rejected_candidates", []),
            policy_references=policy_references or [],
            decision_guidance=guidance,
            answerable_intents=[
                {
                    "intent": "verified_rules",
                    "answerable": bool(compact_rules),
                }
            ],
            unanswerable_intents=[],
            verified_query_plan={},
            capability_graph_summary={},
            entity_linking=entity_linking or {"status": "not_applicable"},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_to_dict(evidence_pack: EvidencePack | dict[str, Any]) -> dict[str, Any]:
    """Normalize an evidence pack object or plain dictionary."""

    if isinstance(evidence_pack, EvidencePack):
        return evidence_pack.to_dict()
    return dict(evidence_pack)


def _guidance_not_executed_preferences(
    guidance: dict[str, Any],
    no_schema_preferences: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    items = []
    for index, item in enumerate(
        no_schema_preferences
        if no_schema_preferences is not None
        else guidance.get("no_schema_field_preferences") or [],
        start=1,
    ):
        source_text = str(item.get("source_text") or "就业偏好")
        reason = str(item.get("reason") or "当前数据中没有可执行字段。")
        items.append(
            {
                "id": f"career_guidance_not_exec_{index}",
                "source_text": source_text,
                "preference": source_text,
                "display": f"{source_text}未执行：{reason}",
                "reason": reason,
                "missing_field": (
                    item.get("field")
                    or item.get("field_id")
                    or "缺少已审查数据字段"
                ),
                "source_span": source_text,
            }
        )
    return items


def _guidance_no_schema_preferences(
    guidance: dict[str, Any],
    existing_preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _records_without_existing_preference_keys(
        guidance.get("no_schema_field_preferences") or [],
        existing_preferences,
    )


def _records_without_existing_preference_keys(
    records: list[dict[str, Any]],
    existing_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = {
        key
        for item in existing_records
        if (key := _preference_record_key(item)) is not None
    }
    output = []
    for item in records:
        key = _preference_record_key(item)
        if key is not None and key in seen:
            continue
        output.append(item)
        if key is not None:
            seen.add(key)
    return output


def _preference_record_key(item: dict[str, Any]) -> tuple[str, str] | None:
    source_text = item.get("source_text") or item.get("source_span")
    if source_text in (None, ""):
        source_text = item.get("preference")
    if source_text in (None, ""):
        return None
    field_id = item.get("field_id")
    if field_id not in (None, ""):
        return (str(field_id), str(source_text))
    return ("source_text", str(source_text))


def _compact_rule(
    rule: dict[str, Any],
    domain_config: DomainConfig | None = None,
) -> dict[str, Any]:
    domain_config = domain_config or DomainConfig.load()
    compact = {
        "rule_id": rule.get("rule_id"),
        "derived_from": rule.get("derived_from"),
        "field": rule.get("field"),
        "operator": rule.get("operator"),
        "value": rule.get("value"),
    }
    for optional_key in ["confirmation", "confirmation_source", "normalization"]:
        if optional_key in rule:
            compact[optional_key] = rule[optional_key]
    compact["description"] = _rule_description(compact, domain_config)
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


def _attribute_explanations(
    attribute_grounding: dict[str, Any],
    executed_rules: list[dict[str, Any]],
    confirmation_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    executed_fields = {
        rule.get("field")
        for rule in executed_rules
        if rule.get("field")
    }
    confirmed_source_texts = {
        str(source.get("source_text"))
        for source in (confirmation_state or {}).get("confirmation_source", [])
        if source.get("source_text")
    }
    explanations = []
    seen: set[tuple[str, str, str]] = set()
    for record in attribute_grounding.get("attributes", []):
        category = _attribute_match_category(record)
        if category is None:
            continue
        source_text = _display_source_text(record.get("source_text"))
        value = record.get("value")
        field = record.get("source_column") or record.get("field_id") or "无可执行字段"
        key = (category, str(field), _stable_value(value))
        if key in seen:
            continue
        seen.add(key)
        action = _attribute_action(
            category=category,
            field=field,
            executed_fields=executed_fields,
            source_text=source_text,
            confirmed_source_texts=confirmed_source_texts,
        )
        explanations.append(
            {
                "source_text": source_text,
                "slot_path": record.get("slot_path"),
                "field": field,
                "value": value,
                "match_type": category,
                "action": action,
                "matched_values": _matched_values(record),
                "reason": _attribute_reason(record, category, action),
            }
        )
    return explanations


def _attribute_match_category(record: dict[str, Any]) -> str | None:
    status = record.get("status")
    audit = record.get("value_index_audit") or {}
    audit_status = audit.get("status")
    if status == "context_only":
        return None
    if (
        status in {"missing_schema", "ignored_not_schema_mapped", "unmapped_attribute"}
        or not record.get("field_exists_in_excel_schema")
        or audit_status == "field_inactive"
    ):
        return "no_schema_field"
    if status == "confirmable" or record.get("requires_human_confirmation"):
        return "partial_match"
    if audit_status in {
        "partial_match",
        "not_found",
        "not_found_in_partial_index",
        "partial_numeric_profile",
        "outside_numeric_profile",
    }:
        return "partial_match"
    if status == "schema_grounded":
        return "exact_match"
    return None


def _attribute_action(
    category: str,
    field: str,
    executed_fields: set[Any],
    source_text: str,
    confirmed_source_texts: set[str],
) -> str:
    if category == "exact_match":
        return "executed" if field in executed_fields else "executable"
    if category == "partial_match":
        if source_text in confirmed_source_texts:
            return "confirmed_executed"
        return "needs_confirmation"
    return "not_executed"


def _attribute_reason(
    record: dict[str, Any],
    category: str,
    action: str,
) -> str:
    field = record.get("source_column") or record.get("field_id") or "无可执行字段"
    if category == "exact_match" and action == "executed":
        return f"已匹配字段“{field}”，并已进入 hard filter。"
    if category == "exact_match":
        return f"已匹配字段“{field}”，可执行但本次未作为 hard filter 使用。"
    if category == "partial_match" and action == "confirmed_executed":
        return f"已通过 candidate_id 确认，并已进入字段“{field}”的 hard filter。"
    if category == "partial_match":
        reason = _user_facing_reason(record.get("reason")) or "需要确认具体边界。"
        return f"{reason}未进入 hard filter。"
    reason = _user_facing_reason(record.get("reason")) or "缺少可执行字段。"
    return f"{reason}原文已保留，未进入 hard filter。"


def _matched_values(record: dict[str, Any]) -> list[str]:
    audit = record.get("value_index_audit") or {}
    matched = []
    for check in audit.get("checks") or []:
        for value in check.get("matched_values") or []:
            text = str(value)
            if text not in matched:
                matched.append(text)
    return matched[:5]


def _display_source_text(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _stable_value(value: Any) -> str:
    if isinstance(value, list):
        if len(value) == 1:
            return str(value[0])
        return "list:" + "|".join(str(item) for item in value)
    return str(value)


def _candidate_confirmations(
    classified_rules: dict[str, Any],
    execution_summary: dict[str, Any],
    domain_config: DomainConfig,
) -> list[dict[str, Any]]:
    candidate_by_id = {
        rule["rule_id"]: rule for rule in classified_rules.get("candidate_rules", [])
    }
    question_source_by_id = {
        question["question_id"]: question.get("source_text")
        for question in classified_rules.get("confirmation_questions", [])
    }
    simulated = classified_rules.get("simulated_confirmations", {})
    mapping = {
        "recommendation_rank_floor": "c_recommendation_rank_floor",
        "safety_margin": "c_safety_margin",
        "tuition_threshold": "c_tuition_cap",
        "major_expansion": "c_major_expansion",
    }
    promoted_rule_ids = {
        "recommendation_rank_floor": "e_recommendation_rank_floor",
        "safety_margin": "e_safety_margin",
        "tuition_threshold": "e_tuition_cap",
    }
    skipped_soft_rule_ids = set(execution_summary.get("skipped_soft_rule_ids") or [])
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
            "status": _confirmation_status(
                confirmation_id=confirmation_id,
                confirmation=confirmation,
                promoted_rule_id=promoted_rule_ids.get(confirmation_id),
                skipped_soft_rule_ids=skipped_soft_rule_ids,
            ),
        }
        if confirmation.get("field"):
            record["field"] = confirmation["field"]
            record["operator"] = confirmation.get("operator")
            record["value"] = confirmation.get("value")
            record["description"] = _rule_description(record, domain_config)
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
        "recommendation_rank_floor": "q_recommendation_rank_floor",
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


def _confirmation_status(
    confirmation_id: str,
    confirmation: dict[str, Any],
    promoted_rule_id: str | None,
    skipped_soft_rule_ids: set[str],
) -> str:
    if confirmation.get("status") == "not_executable":
        return "not_executable"
    if promoted_rule_id in skipped_soft_rule_ids:
        return "confirmed_not_hard_filter"
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
        "No reviewed active school country or overseas study field.": (
            "当前数据中没有已审查的国家或境外办学字段。"
        ),
        "No dedicated school country or overseas study field.": (
            "缺少国家或境外办学字段。"
        ),
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


def _compact_result(
    rank: int,
    row: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    compact = {"rank": rank}
    for spec in domain_config.answer_templates.get("result_line_fields") or []:
        key = spec.get("evidence_key") or spec.get("label") or spec.get("key")
        if spec.get("key"):
            value = row.get(spec["key"])
        else:
            value = row.get(domain_config.source_column(spec["field_id"]))
        if spec.get("optional") and value in (None, ""):
            continue
        compact[str(key)] = value
    if "safety_margin" not in compact:
        compact["safety_margin"] = _format_percent(row.get("safety_margin_pct"))
    compact["trace"] = row.get("trace", [])
    return compact


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


def _rule_description(
    rule: dict[str, Any],
    domain_config: DomainConfig | None = None,
) -> str:
    domain_config = domain_config or DomainConfig.load()
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
        if domain_config.is_rank_field(field):
            return (
                f"{field} 在 {_format_value(value)} 名及以后"
                f"（数值 >= {_format_value(value)}）"
            )
        return f"{field} 不低于 {_format_value(value)}"
    if operator == "<=":
        if domain_config.is_rank_field(field):
            return (
                f"{field} 在 {_format_value(value)} 名以内"
                f"（数值 <= {_format_value(value)}）"
            )
        return f"{field} 不高于 {_format_value(value)}"
    if operator == "between":
        if domain_config.is_rank_field(field):
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
