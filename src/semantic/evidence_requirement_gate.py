from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.semantic.evidence_requirements import (
    DeepSeekEvidenceRequirementClassifier,
    EvidenceRequirement,
    EvidenceRequirementResult,
)
from src.semantic.intent_models import SemanticIntent, SemanticPreference


NON_EXECUTABLE_REQUIREMENT_TYPES = {
    "knowledge_base_or_reviewed_field",
    "reviewed_ranking_policy",
    "user_boundary",
    "unsupported",
}


class EvidenceRequirementClassifierProtocol(Protocol):
    def classify(
        self,
        *,
        text: str,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementResult:
        """返回 evidence requirement 分类结果。"""


@dataclass(frozen=True)
class EvidenceRequirementGateResult:
    filtered_intent: SemanticIntent
    requirements: list[dict[str, Any]] = field(default_factory=list)
    excluded_preferences: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)
    rejected_requirements: list[dict[str, Any]] = field(default_factory=list)
    planner: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)


class EvidenceRequirementGate:
    """把 evidence requirement 分类结果转成可执行 preference 子集。"""

    def __init__(
        self,
        classifier: EvidenceRequirementClassifierProtocol | None = None,
    ) -> None:
        self.classifier = classifier or DeepSeekEvidenceRequirementClassifier()

    def apply(
        self,
        *,
        text: str,
        intent: SemanticIntent,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementGateResult:
        classification = self.classifier.classify(
            text=text,
            schema_context=schema_context,
            query_options=query_options,
        )
        return apply_evidence_requirement_result(intent, classification)


def apply_evidence_requirement_result(
    intent: SemanticIntent,
    classification: EvidenceRequirementResult,
) -> EvidenceRequirementGateResult:
    requirements = [
        requirement.model_dump()
        for requirement in classification.requirements
    ]
    excluded_by_index: dict[int, dict[str, Any]] = {}
    unanswerable: list[dict[str, Any]] = []

    for requirement in classification.requirements:
        if requirement.requirement_type not in NON_EXECUTABLE_REQUIREMENT_TYPES:
            continue
        index = _matching_preference_index(requirement, intent.preferences)
        if index is None:
            continue
        preference = intent.preferences[index]
        excluded = _excluded_preference(preference, requirement)
        excluded_by_index[index] = excluded
        unanswerable.append(_unanswerable_intent(excluded))

    filtered_preferences = [
        preference
        for index, preference in enumerate(intent.preferences)
        if index not in excluded_by_index
    ]
    excluded_preferences = list(excluded_by_index.values())
    usage = dict(classification.usage or {})
    planner = {
        "status": "classified",
        "provider": "deepseek",
        "called": True,
        "fallback_used": False,
        "token_usage": usage,
        "requirements": requirements,
        "excluded_preferences": excluded_preferences,
        "rejected_requirements": list(classification.rejected_requirements),
    }
    return EvidenceRequirementGateResult(
        filtered_intent=intent.model_copy(
            update={"preferences": filtered_preferences}
        ),
        requirements=requirements,
        excluded_preferences=excluded_preferences,
        unanswerable_intents=unanswerable,
        rejected_requirements=list(classification.rejected_requirements),
        planner=planner,
        usage=usage,
    )


def _matching_preference_index(
    requirement: EvidenceRequirement,
    preferences: list[SemanticPreference],
) -> int | None:
    for index, preference in enumerate(preferences):
        if preference.source_text == requirement.source_text:
            return index
    source = _normalized_text(requirement.source_text)
    for index, preference in enumerate(preferences):
        preference_text = _normalized_text(preference.source_text)
        if source and preference_text and (
            source in preference_text or preference_text in source
        ):
            return index
    return None


def _excluded_preference(
    preference: SemanticPreference,
    requirement: EvidenceRequirement,
) -> dict[str, Any]:
    field_id = requirement.candidate_semantic or preference.semantic
    return {
        "source_text": preference.source_text,
        "field_id": field_id,
        "semantic": preference.semantic,
        "candidate_semantic": requirement.candidate_semantic,
        "requirement_type": requirement.requirement_type,
        "match_type": "evidence_requirement_gate",
        "executable": False,
        "reason": _reason(requirement),
    }


def _unanswerable_intent(excluded: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_id": excluded.get("field_id"),
        "intent": excluded.get("semantic"),
        "source_text": excluded.get("source_text"),
        "answerable": False,
        "reason": excluded.get("reason"),
        "requirement_type": excluded.get("requirement_type"),
    }


def _reason(requirement: EvidenceRequirement) -> str:
    if requirement.requirement_type == "knowledge_base_or_reviewed_field":
        return requirement.rationale or "需要 reviewed KB 或已审核结构化字段，当前未执行。"
    if requirement.requirement_type == "reviewed_ranking_policy":
        return requirement.rationale or "需要 reviewed ranking policy，当前未执行。"
    if requirement.requirement_type == "user_boundary":
        return requirement.rationale or "需要用户确认边界，当前未执行。"
    return requirement.rationale or "当前偏好不支持执行。"


def _normalized_text(value: str | None) -> str:
    return "".join(str(value or "").split())


__all__ = [
    "EvidenceRequirementGate",
    "EvidenceRequirementGateResult",
    "apply_evidence_requirement_result",
]
