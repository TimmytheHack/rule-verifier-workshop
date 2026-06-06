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
                "You generate Chinese answers for a verified rule pipeline. "
                "Return strict JSON only with key answer. Use only the supplied "
                "evidence_pack. Do not add facts, infer hidden fields, estimate "
                "admission probability, or inspect raw Excel. You must mention "
                "every not_executed_preferences item and preserve every "
                "trace_summary.safety_warnings item. For each top_k_results item, "
                "copy the school name, professional group code, major name, city, "
                "tuition, group minimum rank, available major minimum rank, and "
                "safety margin exactly as supplied."
            ),
            user_prompt=(
                "Generate one concise Chinese answer from this evidence_pack. "
                "The answer must include result_count, executed_rules, "
                "candidate_confirmations, top_k_results, not_executed_preferences, "
                "and safety warnings. For every top result, include these fields "
                "when present: 院校名称、院校专业组代码、专业名称、"
                "城市、学费、"
                "专业组最低位次、专业最低位次、safety_margin. Evidence pack JSON: "
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
                "You are an LLM-only answer baseline for evaluation. Return strict "
                "JSON only with key answer. You receive user input, schema summary, "
                "and sample projected rows, but no symbolic verifier, no executed "
                "rules, and no evidence pack. The evaluator will check unsupported "
                "claims and rule-boundary violations."
            ),
            user_prompt=(
                "Write a Chinese answer for this college application planning "
                "request using only the user input, schema summary, and sample "
                "rows. Do not claim verified execution unless it is present in "
                "the input. "
                f"User input: {user_request}. "
                f"Schema summary: {json.dumps(schema_summary, ensure_ascii=False)}. "
                f"Sample rows: {json.dumps(sample_results, ensure_ascii=False)}."
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
        "- 已执行规则：",
    ]
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


def _top_result_text(row: dict[str, Any]) -> str:
    parts = [
        f"{row['rank']}. {row.get('院校名称')}",
        f"院校专业组代码：{row.get('院校专业组代码')}",
        f"专业名称：{row.get('专业名称')}",
        f"城市：{row.get('城市')}",
        f"学费：{_format_money(row.get('学费'))}",
        f"专业组最低位次：{row.get('专业组最低位次')}",
    ]
    if row.get("专业最低位次") not in (None, ""):
        parts.append(f"专业最低位次：{row.get('专业最低位次')}")
    if row.get("safety_margin"):
        parts.append(f"safety margin：{row['safety_margin']}")
    return "  - " + "；".join(parts) + "。"


def _format_money(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)} 元/年"
    if isinstance(value, int):
        return f"{value} 元/年"
    return f"{value} 元/年"
