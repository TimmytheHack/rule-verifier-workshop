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
                "You are an intentionally unconstrained baseline for evaluation. "
                "Return strict JSON only. The downstream evaluator will check whether "
                "your output violates rule-verification guardrails."
            ),
            user_prompt=(
                "Given this Chinese college application preference, output JSON with keys: "
                "deterministic_rules, candidate_rules, llm_needed_parts, final_executable_rules, notes. "
                "Each rule should include source_text, field, operator, value if applicable. "
                f"Input: {text}"
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
                "You are a schema-aware LLM-only baseline for evaluation. "
                "Return strict JSON only. You receive schema context, but there is "
                "no symbolic verifier. The evaluator will check whether you still "
                "over-promote vague or unsupported preferences."
            ),
            user_prompt=(
                "Given the schema and this Chinese college application preference, output JSON with keys: "
                "deterministic_rules, candidate_rules, llm_needed_parts, final_executable_rules, notes, trace. "
                "Each rule should include source_text, field, operator, value if applicable. "
                "Do not execute fields whose schema status is missing. "
                f"Schema: {schema_summary}. "
                f"Input: {text}"
            ),
        )
        payload = response.payload
        payload["deepseek_usage"] = response.usage
        return payload
