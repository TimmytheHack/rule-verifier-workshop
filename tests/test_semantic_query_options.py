from __future__ import annotations

import unittest

from src.semantic.query_options import SemanticQueryOptionsBuilder
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry


class SemanticQueryOptionsBuilderTest(unittest.TestCase):
    def test_builds_options_from_reviewed_mapping(self) -> None:
        registry = ReviewedMappingRegistry(
            active_fields={
                "major_name": ReviewedFieldMapping(
                    field_id="major_name",
                    source_column="专业",
                    field_type="string",
                    allowed_ops=("contains_any", "contains"),
                    required_for=("filter", "display"),
                ),
                "school_province": ReviewedFieldMapping(
                    field_id="school_province",
                    source_column="学校所在",
                    field_type="enum_or_category",
                    allowed_ops=("in", "eq"),
                    required_for=("filter", "display"),
                ),
                "major_min_rank": ReviewedFieldMapping(
                    field_id="major_min_rank",
                    source_column="最低位次",
                    field_type="number",
                    allowed_ops=("between", "sort"),
                    required_for=("rank_analysis", "display"),
                ),
            },
            unsupported_fields={
                "school_country_or_region": (
                    "当前数据缺少境外办学字段，不能执行该排除条件。"
                )
            },
        )

        options = SemanticQueryOptionsBuilder(registry).build()

        self.assertEqual(options["required_user_context"], ["user_rank"])
        self.assertIn("semantic_recommendation", options["query_types"])
        self.assertEqual(
            options["filters"]["major_name"]["source_column"],
            "专业",
        )
        self.assertEqual(
            options["unsupported_fields"]["school_country_or_region"],
            "当前数据缺少境外办学字段，不能执行该排除条件。",
        )


if __name__ == "__main__":
    unittest.main()
