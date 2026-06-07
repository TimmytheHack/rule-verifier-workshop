"""Optional DeepSeek answer generators for reporting comparison.

The production-style generator accepts only an EvidencePack. The LLM-only
baseline is kept here as an evaluation comparison and is not an execution path.
"""

from __future__ import annotations

import json
from typing import Any

from src.extractors.deepseek_extractor import DeepSeekClient
from src.reporting.evidence_pack import EvidencePack, evidence_to_dict


class DeepSeekAnswerGenerator:
    """Generate a Chinese answer from verified evidence only."""

    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def generate(self, evidence_pack: EvidencePack | dict[str, Any]) -> dict[str, Any]:
        evidence = evidence_to_dict(evidence_pack)
        response = self.client.chat_json(
            system_prompt=(
                "你负责根据已验证规则管线的证据包生成中文回答。"
                "只返回严格 JSON，键名为 answer。只能使用传入的证据包，"
                "不得添加事实、推断隐藏字段、估计录取概率或查看原始 Excel。"
                "必须提到每一条未执行偏好，并保留所有安全警告。"
                "抽取结果和规则提议审查只能作为已审查证据使用。"
                "前置结果中的院校名称、院校专业组代码、专业名称、城市、专业代码、"
                "专业全称、选科要求、学费、专业组最低位次、专业最低位次和相对排位差"
                "必须按证据包原样引用。回答正文必须全部使用中文。"
            ),
            user_prompt=(
                "请基于以下证据包生成一段简明中文回答。回答必须包含：结果总数、"
                "抽取结果、规则提议审查、已执行规则、候选偏好确认、前置结果、"
                "未执行偏好和安全警告。每条前置结果如果存在这些字段，都要写出："
                "院校名称、院校专业组代码、专业名称、专业代码、专业全称、选科要求、"
                "城市、学费、专业组最低位次、专业最低位次、相对排位差。证据包 JSON："
                f"{json.dumps(evidence, ensure_ascii=False)}"
            ),
        )
        payload = response.payload
        answer = str(payload.get("answer", "")).strip()
        answer = _with_evidence_coverage(answer, evidence)
        return {
            "answer": answer,
            "deepseek_usage": response.usage,
            "raw_payload": payload,
        }


class LLMOnlyAnswerBaseline:
    """Schema/sample/user-input answer baseline with no verified evidence pack."""

    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def generate(
        self,
        user_request: str,
        schema_fields: dict[str, Any],
        sample_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        schema_summary = {
            field_id: {
                "source_column": spec.get("source_column"),
                "status": spec.get("status", "active"),
                "allowed_ops": spec.get("allowed_ops", []),
            }
            for field_id, spec in schema_fields.items()
        }
        response = self.client.chat_json(
            system_prompt=(
                "你是评估用的纯 LLM 回答基线。只返回严格 JSON，键名为 answer。"
                "你会收到用户输入、字段摘要和样例投影行，但没有符号验证器、"
                "没有已执行规则，也没有证据包。评估器会检查不受支持的断言和"
                "规则边界违规。回答必须全部使用中文。"
            ),
            user_prompt=(
                "请只根据用户输入、字段摘要和样例行写一段中文回答。"
                "除非输入中明确包含已验证执行证据，否则不要声称规则已经验证或执行。"
                f"用户输入：{user_request}。"
                f"字段摘要：{json.dumps(schema_summary, ensure_ascii=False)}。"
                f"样例行：{json.dumps(sample_results, ensure_ascii=False)}。"
            ),
        )
        payload = response.payload
        answer = str(payload.get("answer", "")).strip()
        return {
            "answer": answer,
            "deepseek_usage": response.usage,
            "raw_payload": payload,
        }


def _with_evidence_coverage(answer: str, evidence: dict[str, Any]) -> str:
    appendix = _evidence_coverage_appendix(evidence)
    if not answer:
        return appendix
    return f"{answer}\n\n{appendix}"


def _evidence_coverage_appendix(evidence: dict[str, Any]) -> str:
    lines = [
        "证据覆盖清单：",
        f"- 结果总数：{evidence['result_count']}",
        "- 抽取结果：",
    ]
    if evidence.get("extracted_preferences"):
        lines.extend(
            f"  - {preference.get('slot')}：{preference.get('value')}；"
            f"状态：{preference.get('status')}"
            for preference in evidence["extracted_preferences"]
        )
    else:
        lines.append("  - 无。")

    lines.extend(["- 规则提议审查："])
    if evidence.get("proposed_rule_audit"):
        lines.extend(
            f"  - {rule.get('rule_id')}："
            f"{_rule_text(rule.get('field'), rule.get('operator'), rule.get('value'))}；"
            f"审查状态：{_status_text(rule.get('terminal_status'))}"
            for rule in evidence["proposed_rule_audit"]
        )
    else:
        lines.append("  - 无。")

    lines.extend(["- 已执行规则："])
    lines.extend(
        f"  - {rule['rule_id']}：{rule['description']}"
        for rule in evidence["executed_rules"]
    )
    lines.extend(["- 候选偏好确认："])
    lines.extend(
        f"  - {_confirmation_text(confirmation)}"
        for confirmation in evidence["candidate_confirmations"]
    )
    lines.extend(["- 前置结果："])
    lines.extend(_top_result_text(row) for row in evidence["top_k_results"])
    lines.extend(["- 未执行偏好："])
    if evidence["not_executed_preferences"]:
        lines.extend(
            f"  - {preference.get('source_text')}：未执行，未参与筛选。"
            f"原因：{preference.get('reason')}"
            for preference in evidence["not_executed_preferences"]
        )
    else:
        lines.append("  - 无。")

    warnings = evidence.get("trace_summary", {}).get("safety_warnings", [])
    if warnings:
        lines.extend(["- 安全说明："])
        lines.extend(f"  - {warning}" for warning in warnings)
    return "\n".join(lines)


def _confirmation_text(confirmation: dict[str, Any]) -> str:
    source_text = confirmation.get("source_text") or confirmation["confirmation_id"]
    status = confirmation.get("status")
    if status == "promoted_to_executed_rule":
        return f"{source_text} 已确认并执行为 {confirmation.get('description')}"
    if status == "confirmed_without_expansion":
        return f"{source_text} 已确认不扩展专业关键词"
    reason = confirmation.get("reason") or "缺少可执行依据"
    return f"{source_text} 未执行，原因：{reason}"


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


def _rule_text(field: Any, operator: Any, value: Any) -> str:
    if field == "专业组最低位次1" and operator == ">=":
        return f"{field} 在 {value} 名及以后（数值 >= {value}）"
    if field == "专业组最低位次1" and operator == "<=":
        return f"{field} 在 {value} 名以内（数值 <= {value}）"
    if field == "专业组最低位次1" and operator == "between":
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


def _top_result_text(row: dict[str, Any]) -> str:
    parts = [
        f"{row['rank']}. {row.get('院校名称')}",
        f"院校专业组代码：{row.get('院校专业组代码')}",
        f"专业代码：{row.get('专业代码')}",
        f"专业名称：{row.get('专业名称')}",
        f"专业全称：{row.get('专业全称')}",
        f"选科要求：{row.get('选科要求')}",
        f"城市：{row.get('城市')}",
        f"学费：{_format_money(row.get('学费'))}",
        f"专业组最低位次：{row.get('专业组最低位次')}",
    ]
    if row.get("专业最低位次") not in (None, ""):
        parts.append(f"专业最低位次：{row.get('专业最低位次')}")
    if row.get("safety_margin"):
        parts.append(f"相对排位差：{row['safety_margin']}")
    return "  - " + "；".join(parts) + "。"


def _format_money(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)} 元/年"
    if isinstance(value, int):
        return f"{value} 元/年"
    return f"{value} 元/年"
