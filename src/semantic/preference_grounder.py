from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.semantic.intent_models import SemanticPreference
from src.semantic.reviewed_mapping import ReviewedMappingRegistry


@dataclass(frozen=True)
class GroundedPreferences:
    filters: list[dict[str, Any]] = field(default_factory=list)
    not_executed_preferences: list[dict[str, Any]] = field(default_factory=list)
    answerable_intents: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)


class PreferenceGrounder:
    """把 LLM 候选偏好约束到 reviewed mapping。"""

    def __init__(self, registry: ReviewedMappingRegistry) -> None:
        self.registry = registry

    def ground(self, preferences: list[SemanticPreference]) -> GroundedPreferences:
        filters: list[dict[str, Any]] = []
        not_executed: list[dict[str, Any]] = []
        answerable: list[dict[str, Any]] = []
        unanswerable: list[dict[str, Any]] = []
        for preference in preferences:
            field_id = preference.semantic
            if not self.registry.has_field(field_id):
                reason = (
                    self.registry.unsupported_reason(field_id)
                    or f"字段 {field_id} 未通过 review，不能执行。"
                )
                not_executed.append(_not_executed(preference, "no_schema_field", reason))
                unanswerable.append(
                    {
                        "field_id": field_id,
                        "source_text": preference.source_text,
                        "reason": "missing_field",
                        "message": reason,
                    }
                )
                continue
            if not self.registry.has_op(field_id, preference.op):
                reason = f"字段 {field_id} 不支持操作 {preference.op}。"
                not_executed.append(_not_executed(preference, "unsupported_op", reason))
                unanswerable.append(
                    {
                        "field_id": field_id,
                        "op": preference.op,
                        "source_text": preference.source_text,
                        "reason": "unsupported_op",
                        "message": reason,
                    }
                )
                continue
            filters.append(
                {
                    "field_id": field_id,
                    "op": preference.op,
                    "value": preference.value,
                    "source_text": preference.source_text,
                }
            )
            answerable.append(
                {
                    "field_id": field_id,
                    "op": preference.op,
                    "source_text": preference.source_text,
                    "reason": "grounded_preference",
                    "capability": "filter",
                }
            )
        return GroundedPreferences(
            filters=filters,
            not_executed_preferences=not_executed,
            answerable_intents=answerable,
            unanswerable_intents=unanswerable,
        )


def _not_executed(
    preference: SemanticPreference,
    match_type: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "source_text": preference.source_text,
        "field_id": preference.semantic,
        "field": "无可执行字段",
        "match_type": match_type,
        "operator": preference.op,
        "value": preference.value,
        "executable": False,
        "reason": reason,
    }
