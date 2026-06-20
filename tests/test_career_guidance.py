from __future__ import annotations

import unittest

from src.domains import DomainConfig
from src.extractors.regex_extractor import RegexExtractor
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


ADMISSIONS_DOMAIN = DomainConfig.load("admissions")


class CareerGuidanceExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SchemaRegistry.from_domain(
            ADMISSIONS_DOMAIN,
            [
                "生源地",
                "科类",
                "专业名称",
                "城市",
                "学费",
                "专业组最低位次1",
                "选科要求",
            ],
        )

    def test_regex_extracts_family_resource_and_employment_slots(self) -> None:
        slots = RegexExtractor().extract("家里没有资源，想选一个好就业的专业。")

        self.assertEqual(slots["preferences"]["family_resource_raw"], "家里没有资源")
        self.assertEqual(slots["preferences"]["employment_preference_raw"], "好就业")
        self.assertIsNone(slots["preferences"]["career_goal_raw"])
        self.assertEqual(
            slots["raw_sources"]["preferences.family_resource_raw"],
            "家里没有资源",
        )
        self.assertEqual(
            slots["raw_sources"]["preferences.employment_preference_raw"],
            "好就业",
        )

    def test_family_resource_is_context_and_employment_is_no_schema(self) -> None:
        slots = RegexExtractor().extract("家里在医疗系统有资源，想选好就业专业。")

        grounding = AttributeGrounder(self.registry).ground(slots)
        by_path = {
            item["slot_path"]: item
            for item in grounding["attributes"]
        }

        self.assertEqual(
            by_path["preferences.family_resource_raw"]["status"],
            "context_only",
        )
        self.assertFalse(
            by_path["preferences.family_resource_raw"]["can_become_executable_rule"]
        )
        self.assertEqual(
            by_path["preferences.employment_preference_raw"]["status"],
            "missing_schema",
        )
        self.assertFalse(
            by_path["preferences.employment_preference_raw"]["can_become_executable_rule"]
        )


if __name__ == "__main__":
    unittest.main()
