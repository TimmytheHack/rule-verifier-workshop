from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.semantic.intent_models import (
    IntentExtractionResult,
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)


class SemanticIntentModelTest(unittest.TestCase):
    def test_intent_model_accepts_recommendation_rank_and_preferences(self) -> None:
        intent = SemanticIntent(
            query_type="semantic_recommendation",
            user_context=SemanticUserContext(user_rank=15000, subject_type=None),
            preferences=[
                SemanticPreference(
                    source_text="人工智能，计算机",
                    semantic="major_name",
                    op="contains_any",
                    value=["人工智能", "计算机"],
                ),
                SemanticPreference(
                    source_text="想留在广东省",
                    semantic="school_province",
                    op="in",
                    value=["广东"],
                ),
                SemanticPreference(
                    source_text="不想去国外",
                    semantic="school_country_or_region",
                    op="not_in",
                    value=["国外", "境外", "海外"],
                ),
            ],
        )

        self.assertEqual(intent.user_context.user_rank, 15000)
        self.assertEqual(intent.preferences[0].semantic, "major_name")
        self.assertEqual(intent.preferences[0].value, ["人工智能", "计算机"])

    def test_intent_model_rejects_raw_sql_anywhere(self) -> None:
        with self.assertRaises(ValidationError):
            SemanticPreference(
                source_text="坏输入",
                semantic="major_name",
                op="contains",
                value={"raw_sql": "DROP TABLE admissions"},
            )

    def test_extraction_result_records_llm_usage(self) -> None:
        result = IntentExtractionResult(
            intent=SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_rank=15000),
                preferences=[],
            ),
            provider="deepseek",
            raw_payload={"query_type": "semantic_recommendation"},
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.usage["total_tokens"], 15)


if __name__ == "__main__":
    unittest.main()
