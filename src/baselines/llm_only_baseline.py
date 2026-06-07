"""LLM-only baseline for evaluation.

This baseline is intentionally not used for deterministic execution. It exists
only to compare what an LLM might propose without the symbolic verifier.
"""

from __future__ import annotations

from typing import Any

from src.extractors.deepseek_extractor import DeepSeekClient


class LLMOnlyBaseline:
    """Asks DeepSeek to produce rule-like output without symbolic verification."""

    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def propose(self, text: str) -> dict[str, Any]:
        response = self.client.chat_json(
            system_prompt=(
                "你是评估用的非约束 LLM 基线。只返回严格 JSON。"
                "下游评估器会检查你的输出是否违反规则验证边界。"
                "所有解释性文本必须使用中文。"
            ),
            user_prompt=(
                "请根据这个中文高考志愿偏好输出 JSON，键包括："
                "deterministic_rules、candidate_rules、llm_needed_parts、"
                "final_executable_rules、notes。每条规则如适用需包含 "
                "source_text、field、operator、value。"
                f"用户输入：{text}"
            ),
        )
        payload = response.payload
        payload["deepseek_usage"] = response.usage
        return payload


class SchemaAwareLLMOnlyBaseline:
    """A stronger LLM-only baseline that receives schema context but no verifier.

    This is still intentionally not used for deterministic execution. It tests
    whether prompting the model with schema information is enough to prevent
    unsafe promotion without symbolic checks.
    """

    def __init__(self, schema_fields: dict[str, Any], client: DeepSeekClient | None = None) -> None:
        self.schema_fields = schema_fields
        self.client = client or DeepSeekClient()

    def propose(self, text: str) -> dict[str, Any]:
        schema_summary = {
            field_id: {
                "source_column": spec.get("source_column"),
                "status": spec.get("status", "active"),
                "allowed_ops": spec.get("allowed_ops", []),
                "notes": spec.get("notes", ""),
            }
            for field_id, spec in self.schema_fields.items()
        }
        response = self.client.chat_json(
            system_prompt=(
                "你是评估用的字段感知纯 LLM 基线。只返回严格 JSON。"
                "你会收到字段上下文，但没有符号验证器。评估器会检查你是否仍然"
                "过度提升模糊或不受支持的偏好。所有解释性文本必须使用中文。"
            ),
            user_prompt=(
                "请根据字段摘要和中文高考志愿偏好输出 JSON，键包括："
                "deterministic_rules、candidate_rules、llm_needed_parts、"
                "final_executable_rules、notes、trace。每条规则如适用需包含 "
                "source_text、field、operator、value。字段状态为 missing 的字段不得执行。"
                f"字段摘要：{schema_summary}。"
                f"用户输入：{text}"
            ),
        )
        payload = response.payload
        payload["deepseek_usage"] = response.usage
        return payload
