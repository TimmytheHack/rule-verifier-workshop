from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.semantic.intent_models import (
    IntentExtractionResult,
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)
from src.semantic.llm_intent_extractor import DeepSeekSemanticIntentExtractor


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


class FakeDeepSeekClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, str]] = []

    def chat_json(self, system_prompt: str, user_prompt: str):
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt}
        )

        class Response:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload
                self.usage = {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                }

        return Response(self.payload)


class DeepSeekSemanticIntentExtractorTest(unittest.TestCase):
    def test_extracts_rank_with_copula_and_preferences(self) -> None:
        payload = {
            "query_type": "semantic_recommendation",
            "user_context": {
                "user_rank": 15000,
                "user_score": None,
                "source_province": "广东",
                "subject_type": None,
                "reselected_subjects": [],
            },
            "preferences": [
                {
                    "source_text": "人工智能，计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                    "reason": "用户明确专业方向。",
                },
                {
                    "source_text": "想留在广东省",
                    "semantic": "school_province",
                    "op": "in",
                    "value": ["广东"],
                    "reason": "用户明确院校所在地。",
                },
                {
                    "source_text": "不想去国外",
                    "semantic": "school_country_or_region",
                    "op": "not_in",
                    "value": ["国外", "境外", "海外"],
                    "reason": "需要专门字段才能执行。",
                },
            ],
            "requested_output": ["recommendations", "risk_buckets"],
        }
        extractor = DeepSeekSemanticIntentExtractor(
            client=FakeDeepSeekClient(payload)
        )

        result = extractor.extract(
            "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐",
            schema_context=[
                {
                    "field_id": "major_name",
                    "source_column": "专业",
                    "allowed_ops": ["contains_any"],
                }
            ],
        )

        self.assertEqual(result.intent.query_type, "semantic_recommendation")
        self.assertEqual(result.intent.user_context.user_rank, 15000)
        self.assertEqual(
            [item.semantic for item in result.intent.preferences],
            ["major_name", "school_province", "school_country_or_region"],
        )
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.usage["total_tokens"], 18)
        prompt = extractor.client.calls[0]["user_prompt"]
        self.assertIn("字段摘要", prompt)
        self.assertNotIn("SELECT *", prompt)

    def test_score_only_intent_preserves_missing_rank(self) -> None:
        payload = {
            "query_type": "semantic_recommendation",
            "user_context": {
                "user_rank": None,
                "user_score": 630,
                "source_province": "广东",
                "subject_type": None,
                "reselected_subjects": [],
            },
            "preferences": [
                {
                    "source_text": "人工智能，计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                }
            ],
            "requested_output": ["recommendations"],
        }
        extractor = DeepSeekSemanticIntentExtractor(
            client=FakeDeepSeekClient(payload)
        )

        result = extractor.extract(
            "假设我今年的高考分数是630分，想读人工智能，计算机，请给出推荐",
            schema_context=[],
        )

        self.assertIsNone(result.intent.user_context.user_rank)
        self.assertEqual(result.intent.user_context.user_score, 630)


if __name__ == "__main__":
    unittest.main()
