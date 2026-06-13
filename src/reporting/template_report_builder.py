"""Deterministic Chinese answer builder for verified evidence packs."""

from __future__ import annotations

from typing import Any

from src.domains import DomainConfig
from src.reporting.evidence_pack import EvidencePack, evidence_to_dict


class TemplateReportBuilder:
    """Builds a natural-language answer without calling an LLM."""

    def __init__(self, domain_config: DomainConfig | None = None) -> None:
        self.domain_config = domain_config or DomainConfig.load()

    def build(self, evidence_pack: EvidencePack | dict[str, Any]) -> str:
        evidence = evidence_to_dict(evidence_pack)
        lines = [
            "根据已验证规则生成结果：",
            "",
            f"用户需求：{evidence['user_request']}",
            f"共筛选到 {evidence['result_count']} 条符合已执行规则的结果。",
        ]
        if evidence.get("extracted_preferences"):
            lines.extend(["", "抽取与结构化结果："])
            lines.extend(
                _extracted_preference_line(preference)
                for preference in evidence["extracted_preferences"]
            )

        if evidence.get("proposed_rule_audit"):
            lines.extend(["", "规则提议审查："])
            lines.extend(
                _proposed_rule_line(rule, self.domain_config)
                for rule in evidence["proposed_rule_audit"]
            )

        if evidence.get("attribute_explanations"):
            lines.extend(["", "字段值审计解释："])
            lines.extend(
                _attribute_explanation_line(explanation)
                for explanation in evidence["attribute_explanations"]
            )

        lines.extend(["", "已执行规则："])
        lines.extend(
            f"- {rule['rule_id']}：{rule['description']}"
            for rule in evidence["executed_rules"]
        )

        lines.extend(["", "候选偏好确认记录："])
        lines.extend(
            _confirmation_line(confirmation)
            for confirmation in evidence["candidate_confirmations"]
        )
        if evidence.get("confirmed_rules") or evidence.get("unconfirmed_candidates"):
            lines.extend(["", "candidate_id 确认状态："])
            if evidence.get("confirmed_rules"):
                lines.extend(
                    _confirmed_rule_line(rule, evidence)
                    for rule in evidence["confirmed_rules"]
                )
            if evidence.get("unconfirmed_candidates"):
                lines.extend(
                    _unconfirmed_candidate_line(candidate)
                    for candidate in evidence["unconfirmed_candidates"]
                )
        if evidence.get("rejected_confirmations"):
            lines.extend(["", "被拒绝的确认："])
            lines.extend(
                f"- {item.get('candidate_id')}：{item.get('reason')}"
                for item in evidence["rejected_confirmations"]
            )
        if evidence.get("no_schema_field_preferences"):
            lines.extend(["", "缺少字段，不能确认执行："])
            lines.extend(
                _no_schema_candidate_line(candidate)
                for candidate in evidence["no_schema_field_preferences"]
            )

        lines.extend(["", "未执行但已保留的偏好："])
        if evidence["not_executed_preferences"]:
            lines.extend(
                _not_executed_line(preference)
                for preference in evidence["not_executed_preferences"]
            )
        else:
            lines.append("- 无。")

        lines.extend(["", f"前 {len(evidence['top_k_results'])} 条结果："])
        lines.extend(
            _result_line(row, self.domain_config)
            for row in evidence["top_k_results"]
        )

        safety_warnings = evidence.get("trace_summary", {}).get("safety_warnings", [])
        if safety_warnings:
            lines.extend(["", "安全说明："])
            lines.extend(f"- {warning}" for warning in safety_warnings)

        return "\n".join(lines)


def _confirmation_line(confirmation: dict[str, Any]) -> str:
    source_text = confirmation.get("source_text") or confirmation["confirmation_id"]
    label = confirmation.get("selected_label") or "未选择可执行选项"
    status = confirmation.get("status")
    if status == "promoted_to_executed_rule":
        return (
            f"- {source_text}：已确认“{label}”，执行为 "
            f"{confirmation.get('description')}。"
        )
    if status == "confirmed_not_hard_filter":
        return (
            f"- {source_text}：已确认“{label}”，但未进入 hard filter，"
            "仅作为候选边界记录。"
        )
    if status == "confirmed_without_expansion":
        return f"- {source_text}：已确认“{label}”，未扩展专业关键词。"
    reason = confirmation.get("reason") or "缺少可执行依据"
    return f"- {source_text}：未执行，原因：{reason}。"


def _confirmed_rule_line(
    rule: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    source = _confirmation_source_for_rule(rule, evidence)
    executed = rule.get("rule_id") in set(
        evidence.get("executed_after_confirmation") or []
    )
    status = "已确认并进入 hard filter" if executed else "已确认但未执行"
    return (
        f"- {source.get('candidate_id')}：{status}；来源："
        f"{source.get('source_text')}；执行为 {rule.get('description')}。"
    )


def _confirmation_source_for_rule(
    rule: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = rule.get("derived_from")
    for source in evidence.get("confirmation_source") or []:
        if source.get("candidate_id") == candidate_id:
            return source
    return {"candidate_id": candidate_id, "source_text": "未知候选"}


def _unconfirmed_candidate_line(candidate: dict[str, Any]) -> str:
    return (
        f"- {candidate.get('candidate_id')}：{candidate.get('source_text')} "
        f"仍待确认，未进入 hard filter；候选为 {candidate.get('label')}。"
    )


def _no_schema_candidate_line(candidate: dict[str, Any]) -> str:
    return (
        f"- {candidate.get('source_text')}：{candidate.get('reason')}；"
        "即使提交该 candidate_id 也不能执行。"
    )


def _extracted_preference_line(preference: dict[str, Any]) -> str:
    value = preference.get("value")
    if isinstance(value, list):
        value = "、".join(str(item) for item in value)
    return (
        f"- {preference.get('slot')}：{value}；"
        f"状态：{preference.get('status')}；来源：{preference.get('source_span')}"
    )


def _proposed_rule_line(
    rule: dict[str, Any],
    domain_config: DomainConfig,
) -> str:
    value = rule.get("value")
    if isinstance(value, list):
        value = "、".join(str(item) for item in value)
    return (
        f"- {rule.get('rule_id')}："
        f"{_rule_text(rule.get('field'), rule.get('operator'), value, domain_config)}；"
        f"审查状态：{_status_text(rule.get('terminal_status'))}"
    )


def _attribute_explanation_line(explanation: dict[str, Any]) -> str:
    label = {
        "executed": "已执行",
        "confirmed_executed": "确认执行",
        "executable": "可执行",
        "needs_confirmation": "需确认",
        "not_executed": "未执行",
    }.get(str(explanation.get("action")), str(explanation.get("action")))
    matched = explanation.get("matched_values") or []
    matched_text = f"；索引命中：{'、'.join(str(item) for item in matched)}" if matched else ""
    return (
        f"- [{label}] {explanation.get('source_text')} -> "
        f"{explanation.get('field')}：{explanation.get('match_type')}"
        f"{matched_text}；{explanation.get('reason')}"
    )


def _not_executed_line(preference: dict[str, Any]) -> str:
    source_text = preference.get("source_text") or "未命名偏好"
    reason = preference.get("reason") or "缺少可验证依据"
    return f"- {source_text}：未执行，未参与筛选。原因：{reason}"


def _result_line(row: dict[str, Any], domain_config: DomainConfig) -> str:
    parts = []
    for spec in domain_config.answer_templates.get("result_line_fields") or []:
        key = spec.get("evidence_key") or spec.get("label") or spec.get("key")
        value = row.get(str(key))
        if spec.get("optional") and value in (None, ""):
            continue
        if spec.get("rank_prefix"):
            parts.append(f"{row['rank']}. {value}")
            continue
        label = spec.get("label") or key
        if spec.get("format") == "money":
            value = _money(value)
        parts.append(f"{label}：{value}")
    return "- " + "；".join(parts) + "。"


def _money(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)} 元/年"
    if isinstance(value, int):
        return f"{value} 元/年"
    return f"{value} 元/年"


def _operator_text(operator: Any) -> str:
    labels = {
        "eq": "等于",
        "neq": "不等于",
        "contains": "包含",
        "in_contains": "包含任一",
        "contains_any": "包含任一",
        "in": "属于",
        "not_in": "不属于",
        "<=": "不高于",
        ">=": "不低于",
        "between": "位于区间",
        "satisfies_subject_requirement": "满足选科要求",
    }
    return labels.get(str(operator), str(operator))


def _rule_text(
    field: Any,
    operator: Any,
    value: Any,
    domain_config: DomainConfig | None = None,
) -> str:
    domain_config = domain_config or DomainConfig.load()
    if domain_config.is_rank_field(field) and operator == ">=":
        return f"{field} 在 {value} 名及以后（数值 >= {value}）"
    if domain_config.is_rank_field(field) and operator == "<=":
        return f"{field} 在 {value} 名以内（数值 <= {value}）"
    if domain_config.is_rank_field(field) and operator == "between":
        return f"{field} 位于 {_format_rank_window(value)}的窗口内"
    return f"{field} {_operator_text(operator)} {value}"


def _format_rank_window(value: Any) -> str:
    if isinstance(value, list) and len(value) == 2:
        return f"{value[0]}-{value[1]} 名"
    return f"{value} 名"


def _status_text(status: Any) -> str:
    labels = {
        "executable": "验证通过，可执行",
        "confirmable": "可确认后执行",
        "context_only": "仅作为上下文",
        "rejected_missing_schema": "拒绝：缺少字段",
        "rejected_invalid_operator": "拒绝：操作符不允许",
        "rejected_invalid_value": "拒绝：值无效",
        "blocked": "阻塞",
    }
    return labels.get(str(status), str(status))
