"""Deterministic Chinese answer builder for verified evidence packs."""

from __future__ import annotations

from typing import Any

from src.reporting.evidence_pack import EvidencePack, evidence_to_dict


class TemplateReportBuilder:
    """Builds a natural-language answer without calling an LLM."""

    def build(self, evidence_pack: EvidencePack | dict[str, Any]) -> str:
        evidence = evidence_to_dict(evidence_pack)
        lines = [
            "根据已验证规则生成结果：",
            "",
            f"用户需求：{evidence['user_request']}",
            f"共筛选到 {evidence['result_count']} 条符合已执行规则的结果。",
            "",
            "已执行规则：",
        ]
        lines.extend(
            f"- {rule['rule_id']}：{rule['description']}"
            for rule in evidence["executed_rules"]
        )

        lines.extend(["", "候选偏好确认记录："])
        lines.extend(
            _confirmation_line(confirmation)
            for confirmation in evidence["candidate_confirmations"]
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
        lines.extend(_result_line(row) for row in evidence["top_k_results"])

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
    if status == "confirmed_without_expansion":
        return f"- {source_text}：已确认“{label}”，未扩展专业关键词。"
    reason = confirmation.get("reason") or "缺少可执行依据"
    return f"- {source_text}：未执行，原因：{reason}。"


def _not_executed_line(preference: dict[str, Any]) -> str:
    source_text = preference.get("source_text") or "未命名偏好"
    reason = preference.get("reason") or "缺少可验证依据"
    return f"- {source_text}：未执行，未参与筛选。原因：{reason}"


def _result_line(row: dict[str, Any]) -> str:
    parts = [
        f"{row['rank']}. {row.get('院校名称')}",
        f"专业组代码：{row.get('院校专业组代码')}",
        f"专业代码：{row.get('专业代码')}",
        f"专业名称：{row.get('专业名称')}",
        f"专业全称：{row.get('专业全称')}",
        f"城市：{row.get('城市')}",
        f"学费：{_money(row.get('学费'))}",
        f"专业组最低位次：{row.get('专业组最低位次')}",
    ]
    if row.get("专业最低位次") not in (None, ""):
        parts.append(f"专业最低位次：{row.get('专业最低位次')}")
    if row.get("safety_margin"):
        parts.append(f"safety margin：{row['safety_margin']}")
    return "- " + "；".join(parts) + "。"


def _money(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)} 元/年"
    if isinstance(value, int):
        return f"{value} 元/年"
    return f"{value} 元/年"
