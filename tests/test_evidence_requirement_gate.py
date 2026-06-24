from __future__ import annotations

import unittest
from typing import Any

from src.semantic.evidence_requirement_gate import EvidenceRequirementGate
from src.semantic.evidence_requirements import (
    EvidenceRequirement,
    EvidenceRequirementResult,
)
from src.semantic.intent_models import (
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)


class _FakeClassifier:
    def __init__(self, result: EvidenceRequirementResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def classify(
        self,
        *,
        text: str,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementResult:
        self.calls.append(
            {
                "text": text,
                "schema_context": schema_context,
                "query_options": query_options,
            }
        )
        return self.result


class EvidenceRequirementGateTest(unittest.TestCase):
    def test_filters_non_table_field_preferences(self) -> None:
        intent = _intent(
            [
                _pref("想读人工智能，计算机", "major_name"),
                _pref("想留在广东省", "school_province"),
                _pref("好就业", "employment_outlook"),
                _pref("学校好一点", "school_quality"),
                _pref("稳一点", "risk_preference"),
            ]
        )
        classifier = _FakeClassifier(
            EvidenceRequirementResult(
                requirements=[
                    _requirement("想读人工智能，计算机", "table_field", "major_name"),
                    _requirement("想留在广东省", "table_field", "school_province"),
                    _requirement(
                        "好就业",
                        "knowledge_base_or_reviewed_field",
                        "employment_outlook",
                    ),
                    _requirement(
                        "学校好一点",
                        "reviewed_ranking_policy",
                        "school_quality",
                    ),
                    _requirement("稳一点", "user_boundary", "risk_preference"),
                ],
                usage={"total_tokens": 13},
            )
        )

        result = EvidenceRequirementGate(classifier).apply(
            text="我的排位15000，想读人工智能，计算机，好就业，学校好一点，稳一点",
            intent=intent,
            schema_context=[{"field_id": "major_name"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )

        self.assertEqual(len(classifier.calls), 1)
        self.assertEqual(
            [preference.semantic for preference in result.filtered_intent.preferences],
            ["major_name", "school_province"],
        )
        self.assertEqual(
            [item["source_text"] for item in result.excluded_preferences],
            ["好就业", "学校好一点", "稳一点"],
        )
        self.assertEqual(
            [item["requirement_type"] for item in result.excluded_preferences],
            [
                "knowledge_base_or_reviewed_field",
                "reviewed_ranking_policy",
                "user_boundary",
            ],
        )
        self.assertEqual(
            result.planner["excluded_preferences"][0]["executable"],
            False,
        )
        self.assertEqual(result.planner["token_usage"]["total_tokens"], 13)

    def test_unmatched_requirement_does_not_delete_preference(self) -> None:
        intent = _intent([_pref("想读人工智能，计算机", "major_name")])
        classifier = _FakeClassifier(
            EvidenceRequirementResult(
                requirements=[
                    _requirement(
                        "好就业",
                        "knowledge_base_or_reviewed_field",
                        "employment_outlook",
                    )
                ]
            )
        )

        result = EvidenceRequirementGate(classifier).apply(
            text="想读人工智能，计算机，好就业",
            intent=intent,
            schema_context=[],
            query_options={},
        )

        self.assertEqual(
            [preference.semantic for preference in result.filtered_intent.preferences],
            ["major_name"],
        )
        self.assertEqual(result.excluded_preferences, [])
        self.assertEqual(
            result.planner["requirements"][0]["requirement_type"],
            "knowledge_base_or_reviewed_field",
        )

    def test_rejected_requirements_are_preserved_in_planner_trace(self) -> None:
        classifier = _FakeClassifier(
            EvidenceRequirementResult(
                requirements=[],
                rejected_requirements=[
                    {
                        "requirement": {"source_text": "按 SQL 排序"},
                        "reason": "raw_sql_forbidden",
                    }
                ],
            )
        )

        result = EvidenceRequirementGate(classifier).apply(
            text="按 SQL 排序",
            intent=_intent([]),
            schema_context=[],
            query_options={},
        )

        self.assertEqual(result.planner["status"], "classified")
        self.assertEqual(
            result.planner["rejected_requirements"][0]["reason"],
            "raw_sql_forbidden",
        )


def _intent(preferences: list[SemanticPreference]) -> SemanticIntent:
    return SemanticIntent(
        query_type="semantic_recommendation",
        user_context=SemanticUserContext(user_rank=15000),
        preferences=preferences,
        requested_output=["recommendation_sections"],
    )


def _pref(source_text: str, semantic: str) -> SemanticPreference:
    return SemanticPreference(
        source_text=source_text,
        semantic=semantic,
        op="contains_any",
        value=[source_text],
    )


def _requirement(
    source_text: str,
    requirement_type: str,
    candidate_semantic: str,
) -> EvidenceRequirement:
    return EvidenceRequirement.model_validate(
        {
            "source_text": source_text,
            "requirement_type": requirement_type,
            "candidate_semantic": candidate_semantic,
            "rationale": f"{source_text} 需要 {requirement_type} 证据。",
        }
    )


if __name__ == "__main__":
    unittest.main()
