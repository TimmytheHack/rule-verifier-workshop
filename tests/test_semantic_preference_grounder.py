from __future__ import annotations

import unittest

from src.semantic.intent_models import SemanticPreference
from src.semantic.preference_grounder import PreferenceGrounder
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry


def _registry() -> ReviewedMappingRegistry:
    return ReviewedMappingRegistry(
        active_fields={
            "major_name": ReviewedFieldMapping(
                field_id="major_name",
                source_column="专业",
                field_type="string",
                allowed_ops=("contains_any", "contains", "eq"),
                required_for=("filter", "display"),
            ),
            "school_province": ReviewedFieldMapping(
                field_id="school_province",
                source_column="学校所在",
                field_type="enum_or_category",
                allowed_ops=("in", "eq"),
                required_for=("filter", "display"),
            ),
        },
        unsupported_fields={
            "school_country_or_region": (
                "当前数据缺少境外办学字段，不能执行该排除条件。"
            )
        },
    )


class PreferenceGrounderTest(unittest.TestCase):
    def test_splits_executable_and_missing_schema_preferences(self) -> None:
        preferences = [
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
        ]

        result = PreferenceGrounder(_registry()).ground(preferences)

        self.assertEqual(
            [item["field_id"] for item in result.filters],
            ["major_name", "school_province"],
        )
        self.assertEqual(result.filters[0]["op"], "contains_any")
        self.assertEqual(result.not_executed_preferences[0]["source_text"], "不想去国外")
        self.assertEqual(
            result.not_executed_preferences[0]["match_type"],
            "no_schema_field",
        )
        self.assertFalse(result.not_executed_preferences[0]["executable"])

    def test_unsupported_op_is_not_executed(self) -> None:
        result = PreferenceGrounder(_registry()).ground(
            [
                SemanticPreference(
                    source_text="专业排除计算机",
                    semantic="major_name",
                    op="not_in",
                    value=["计算机"],
                )
            ]
        )

        self.assertEqual(result.filters, [])
        self.assertEqual(
            result.not_executed_preferences[0]["match_type"],
            "unsupported_op",
        )


if __name__ == "__main__":
    unittest.main()
