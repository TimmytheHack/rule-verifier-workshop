from importlib import import_module
from typing import Any

from src.semantic.query_ast import (
    QueryAST,
    QueryFilter,
    QuerySort,
    QueryVerificationIssue,
    VerifiedQueryPlan,
)
from src.semantic.ranking_plan import RankingCriterion, RankingPlan
from src.semantic.ranking_verifier import RankingVerifier, RankingVerificationResult
from src.semantic.intent_models import (
    IntentExtractionResult,
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)

_LAZY_EXPORTS = {
    "DeepSeekSemanticIntentExtractor": (
        "src.semantic.llm_intent_extractor",
        "DeepSeekSemanticIntentExtractor",
    ),
    "DeepSeekSemanticCandidateGenerator": (
        "src.semantic.llm_semantic_candidates",
        "DeepSeekSemanticCandidateGenerator",
    ),
    "SemanticCandidateGenerationResult": (
        "src.semantic.llm_semantic_candidates",
        "SemanticCandidateGenerationResult",
    ),
    "DeepSeekEvidenceRequirementClassifier": (
        "src.semantic.evidence_requirements",
        "DeepSeekEvidenceRequirementClassifier",
    ),
    "EvidenceRequirement": (
        "src.semantic.evidence_requirements",
        "EvidenceRequirement",
    ),
    "EvidenceRequirementResult": (
        "src.semantic.evidence_requirements",
        "EvidenceRequirementResult",
    ),
    "EvidenceRequirementGate": (
        "src.semantic.evidence_requirement_gate",
        "EvidenceRequirementGate",
    ),
    "EvidenceRequirementGateResult": (
        "src.semantic.evidence_requirement_gate",
        "EvidenceRequirementGateResult",
    ),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "IntentExtractionResult",
    "DeepSeekEvidenceRequirementClassifier",
    "DeepSeekSemanticIntentExtractor",
    "DeepSeekSemanticCandidateGenerator",
    "EvidenceRequirement",
    "EvidenceRequirementGate",
    "EvidenceRequirementGateResult",
    "EvidenceRequirementResult",
    "QueryAST",
    "QueryFilter",
    "QuerySort",
    "QueryVerificationIssue",
    "RankingCriterion",
    "RankingPlan",
    "RankingVerifier",
    "RankingVerificationResult",
    "SemanticCandidateGenerationResult",
    "SemanticIntent",
    "SemanticPreference",
    "SemanticUserContext",
    "VerifiedQueryPlan",
]
