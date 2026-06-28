from __future__ import annotations

import unittest

from src.semantic.query_options import SemanticQueryOptionsBuilder
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry
from src.schema.schema_registry import SchemaRegistry


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

    def test_falls_back_to_active_schema_fields_for_generic_domains(self) -> None:
        registry = ReviewedMappingRegistry(active_fields={}, unsupported_fields={})
        schema_registry = SchemaRegistry(
            active_fields={
                "city": {
                    "source_column": "城市",
                    "type": "enum",
                    "allowed_ops": ["in"],
                },
                "rent": {
                    "source_column": "租金",
                    "type": "number",
                    "allowed_ops": ["<=", "sort"],
                },
                "note": {
                    "source_column": "备注",
                    "type": "string",
                    "allowed_ops": [],
                },
            },
            configured_fields={},
        )

        options = SemanticQueryOptionsBuilder(
            registry,
            schema_registry=schema_registry,
        ).build()

        self.assertEqual(options["query_types"], [])
        self.assertEqual(options["required_user_context"], [])
        self.assertEqual(options["filters"]["city"]["source_column"], "城市")
        self.assertEqual(options["filters"]["rent"]["allowed_ops"], ["<=", "sort"])
        self.assertEqual(options["sort_fields"]["rent"]["source_column"], "租金")
        self.assertNotIn("note", options["filters"])


if __name__ == "__main__":
    unittest.main()
