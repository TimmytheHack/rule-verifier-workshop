from __future__ import annotations

import unittest

from src.extractors.extractor_pipeline import ExtractorFallbackPipeline
from src.extractors.regex_extractor import RegexExtractor


class FakeFallbackExtractor:
    def extract(self, text: str, **_kwargs: object) -> dict[str, object]:
        return {
            "input": text,
            "user_context": {
                "source_province": "广东",
                "subject_type": "物理",
                "user_rank": 12345,
            },
            "preferences": {
                "major_keyword": "环境工程",
                "major_exact_terms": ["环境工程"],
                "preferred_cities": ["广州"],
            },
            "proposed_rules": [
                {
                    "rule_id": "p_major_env",
                    "field_id": "major_name",
                    "operator": "contains",
                    "value": "环境工程",
                }
            ],
            "raw_phrases": ["环境工程"],
            "deepseek_usage": {"total_tokens": 9},
        }


class ExtractorFallbackPipelineTest(unittest.TestCase):
    def test_fallback_fills_missing_slots_without_proposed_rules(self) -> None:
        text = "广东物理类，排位12345，想学环境工程，广州。"
        slots = ExtractorFallbackPipeline(
            deterministic_extractor=RegexExtractor(),
            fallback_extractor=FakeFallbackExtractor(),
            fallback_enabled=True,
        ).extract(text)

        self.assertTrue(slots["fallback_extraction"]["used"])
        self.assertIn(
            "preferences.major_exact_terms",
            slots["fallback_extraction"]["filled_paths"],
        )
        self.assertEqual(slots["user_context"]["user_rank"], 12345)
        self.assertEqual(slots["preferences"]["major_exact_terms"], ["环境工程"])
        self.assertEqual(slots["preferences"]["preferred_cities"], ["广州"])
        self.assertEqual(slots["proposed_rules"], [])
        self.assertEqual(slots["deepseek_usage"]["total_tokens"], 9)

    def test_fallback_is_skipped_when_deterministic_slots_are_sufficient(self) -> None:
        slots = ExtractorFallbackPipeline(
            deterministic_extractor=RegexExtractor(),
            fallback_extractor=FakeFallbackExtractor(),
            fallback_enabled=True,
        ).extract("广东物理类，排位32000，想学计科，广深优先。")

        self.assertFalse(slots["fallback_extraction"]["used"])
        self.assertEqual(slots["preferences"]["major_exact_terms"], [])
        self.assertEqual(slots["preferences"]["major_expansion_raw"], "计科")
        self.assertEqual(slots["preferences"]["preferred_cities"], ["广州", "深圳"])


if __name__ == "__main__":
    unittest.main()
