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
