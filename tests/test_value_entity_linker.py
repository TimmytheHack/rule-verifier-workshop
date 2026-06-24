from __future__ import annotations

import unittest

from src.adapters.data_warehouse import SchemaValueIndex
from src.schema.schema_registry import SchemaRegistry
from src.schema.value_entity_linker import ReviewedValueEntityLinker


class ReviewedValueEntityLinkerTest(unittest.TestCase):
    def test_university_exact_span_suppresses_city_substring(self) -> None:
        result = _link("我想进深圳大学，目前排位15000")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.accepted_links],
            [("university_name", "深圳大学")],
        )
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.suppressed_links],
            [("city", "深圳")],
        )
        self.assertEqual(result.ambiguous_links, [])
        self.assertEqual(result.not_executed_links, [])
        self.assertEqual(len(result.proposed_rules), 1)
        self.assertEqual(result.proposed_rules[0]["field_id"], "university_name")
        self.assertEqual(result.proposed_rules[0]["operator"], "eq")
        self.assertEqual(result.proposed_rules[0]["value"], "深圳大学")
        self.assertEqual(result.proposed_rules[0]["semantic_type"], "explicit_user_fact")

    def test_city_expression_executes_city_not_university(self) -> None:
        result = _link("我想去深圳的大学，目前排位15000")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.accepted_links],
            [("city", "深圳")],
        )
        self.assertEqual(result.suppressed_links, [])
        self.assertEqual(result.ambiguous_links, [])
        self.assertEqual(len(result.proposed_rules), 1)
        self.assertEqual(result.proposed_rules[0]["field_id"], "city")
        self.assertEqual(result.proposed_rules[0]["operator"], "in_contains")
        self.assertEqual(result.proposed_rules[0]["value"], ["深圳"])

    def test_nearby_expression_is_not_executed(self) -> None:
        result = _link("想找深圳大学附近的学校")

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["source_text"], "深圳大学附近")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "附近/周边表达需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。",
        )

    def test_same_span_exact_match_on_two_fields_is_ambiguous(self) -> None:
        result = _link(
            "想去南方学院",
            extra_registry_fields={
                "college_name": {
                    "source_column": "学院名称",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                }
            },
            extra_index_fields={
                "college_name": {
                    "source_column": "学院名称",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                    "lookup_complete": True,
                    "lookup_values": ["南方学院"],
                }
            },
            university_values=["南方学院"],
        )

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(len(result.ambiguous_links), 2)
        self.assertEqual(
            sorted((link["field_id"], link["value"]) for link in result.ambiguous_links),
            [("college_name", "南方学院"), ("university_name", "南方学院")],
        )
        self.assertEqual(
            len({link["span"] for link in result.ambiguous_links}),
            1,
        )
        self.assertEqual(result.proposed_rules, [])

    def test_incomplete_lookup_does_not_execute_by_default(self) -> None:
        result = _link("我想进深圳大学", university_lookup_complete=False)

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["field_id"], "university_name")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "字段值索引不完整，不能直接执行实体筛选。",
        )

    def test_missing_value_index_fails_closed(self) -> None:
        registry = _registry()
        result = ReviewedValueEntityLinker(registry, None).link("我想进深圳大学")

        self.assertEqual(result.status, "value_index_unavailable")
        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.suppressed_links, [])
        self.assertEqual(result.ambiguous_links, [])
        self.assertEqual(result.not_executed_links, [])
        self.assertEqual(result.proposed_rules, [])

    def test_negated_university_entity_does_not_become_positive_rule(self) -> None:
        result = _link("不要深圳大学")

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["field_id"], "university_name")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "否定/排除上下文不能直接执行为正向实体筛选。",
        )

    def test_distance_context_does_not_become_city_filter(self) -> None:
        for text in ("离深圳近一点", "不要离深圳太远"):
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(result.accepted_links, [])
                self.assertEqual(result.proposed_rules, [])
                self.assertEqual(result.not_executed_links[0]["field_id"], "city")
                self.assertEqual(
                    result.not_executed_links[0]["reason"],
                    "距离/模糊地理边界需要地理距离或用户确认边界，不能直接执行为城市筛选。",
                )

    def test_household_registration_context_does_not_become_city_filter(self) -> None:
        result = _link("深圳户籍考生")

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["field_id"], "city")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "身份/户籍上下文不能直接执行为城市筛选。",
        )

    def test_index_field_without_explicit_active_flag_fails_closed(self) -> None:
        result = _link(
            "深圳的大学",
            extra_index_fields={
                "city": {
                    "source_column": "城市",
                    "type": "string",
                    "allowed_ops": ["contains", "in_contains"],
                    "lookup_complete": True,
                    "lookup_values": ["深圳"],
                }
            },
        )

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])

    def test_cross_field_same_span_with_incomplete_lookup_does_not_execute(self) -> None:
        result = _link(
            "想去南方学院",
            university_values=["南方学院"],
            university_lookup_complete=False,
            extra_registry_fields={
                "college_name": {
                    "source_column": "学院名称",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                }
            },
            extra_index_fields={
                "college_name": {
                    "source_column": "学院名称",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                    "lookup_complete": True,
                    "lookup_values": ["南方学院"],
                }
            },
        )

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])

    def test_multiple_city_values_merge_into_one_rule_in_source_order(self) -> None:
        result = _link(
            "我想去广州或者深圳的大学",
            city_values=["深圳", "广州"],
        )

        self.assertEqual(len(result.proposed_rules), 1)
        self.assertEqual(result.proposed_rules[0]["field_id"], "city")
        self.assertEqual(result.proposed_rules[0]["operator"], "in_contains")
        self.assertEqual(result.proposed_rules[0]["value"], ["广州", "深圳"])

    def test_trailing_negated_university_entity_does_not_execute(self) -> None:
        for text in (
            "深圳大学不要",
            "深圳大学不考虑",
            "深圳大学，不考虑",
            "深圳大学 不考虑",
        ):
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(result.accepted_links, [])
                self.assertEqual(result.proposed_rules, [])
                self.assertEqual(result.not_executed_links[0]["field_id"], "university_name")
                self.assertEqual(
                    result.not_executed_links[0]["reason"],
                    "否定/排除上下文不能直接执行为正向实体筛选。",
                )

    def test_common_negation_terms_do_not_execute_entities(self) -> None:
        cases = [
            ("不是深圳的高校", "city"),
            ("除了深圳大学", "university_name"),
        ]
        for text, field_id in cases:
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(result.accepted_links, [])
                self.assertEqual(result.proposed_rules, [])
                self.assertEqual(result.not_executed_links[0]["field_id"], field_id)
                self.assertEqual(
                    result.not_executed_links[0]["reason"],
                    "否定/排除上下文不能直接执行为正向实体筛选。",
                )

    def test_distance_context_blocks_university_entity(self) -> None:
        result = _link("离深圳大学近一点")

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["field_id"], "university_name")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "距离/模糊地理边界需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。",
        )

    def test_malformed_lookup_complete_fails_closed(self) -> None:
        result = _link("我想进深圳大学", university_lookup_complete="false")

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["field_id"], "university_name")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "字段值索引不完整，不能直接执行实体筛选。",
        )

    def test_extra_code_fields_are_not_auto_linked_as_entities(self) -> None:
        result = _link(
            "目前排位15000",
            extra_registry_fields={
                "major_code": {
                    "source_column": "专业代码",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                }
            },
            extra_index_fields={
                "major_code": {
                    "source_column": "专业代码",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                    "lookup_complete": True,
                    "lookup_values": ["150"],
                }
            },
        )

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])

    def test_recent_word_does_not_block_clear_city_expression(self) -> None:
        result = _link("最近想去深圳的大学")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.accepted_links],
            [("city", "深圳")],
        )
        self.assertEqual(len(result.proposed_rules), 1)
        self.assertEqual(result.proposed_rules[0]["field_id"], "city")
        self.assertEqual(result.proposed_rules[0]["value"], ["深圳"])

    def test_common_exclusion_terms_do_not_execute_positive_rules(self) -> None:
        cases = [
            ("不报深圳大学", "university_name"),
            ("不选深圳大学", "university_name"),
            ("避免深圳大学", "university_name"),
            ("不在深圳读大学", "city"),
        ]
        for text, field_id in cases:
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(result.accepted_links, [])
                self.assertEqual(result.proposed_rules, [])
                self.assertEqual(result.not_executed_links[0]["field_id"], field_id)
                self.assertEqual(
                    result.not_executed_links[0]["reason"],
                    "否定/排除上下文不能直接执行为正向实体筛选。",
                )

    def test_trailing_cost_negation_does_not_block_city_preference(self) -> None:
        for text in ("想去深圳的大学，不要太贵", "想去深圳的大学不要太贵"):
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(
                    [(link["field_id"], link["value"]) for link in result.accepted_links],
                    [("city", "深圳")],
                )
                self.assertEqual(len(result.proposed_rules), 1)
                self.assertEqual(result.proposed_rules[0]["field_id"], "city")
                self.assertEqual(result.proposed_rules[0]["value"], ["深圳"])

    def test_nearby_boundary_does_not_swallow_other_valid_city_preference(self) -> None:
        result = _link("想找深圳大学附近的学校，也可以广州的大学")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.accepted_links],
            [("city", "广州")],
        )
        self.assertEqual(len(result.proposed_rules), 1)
        self.assertEqual(result.proposed_rules[0]["field_id"], "city")
        self.assertEqual(result.proposed_rules[0]["value"], ["广州"])
        self.assertIn(
            ("深圳大学附近", "附近/周边表达需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。"),
            [
                (link["source_text"], link["reason"])
                for link in result.not_executed_links
            ],
        )

    def test_special_adverb_does_not_trigger_single_character_negation(self) -> None:
        university_result = _link("特别想去深圳大学")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in university_result.accepted_links],
            [("university_name", "深圳大学")],
        )
        self.assertEqual(len(university_result.proposed_rules), 1)
        self.assertEqual(university_result.proposed_rules[0]["field_id"], "university_name")
        self.assertEqual(university_result.proposed_rules[0]["operator"], "eq")
        self.assertEqual(university_result.proposed_rules[0]["value"], "深圳大学")

        city_result = _link("特别想去深圳的大学")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in city_result.accepted_links],
            [("city", "深圳")],
        )
        self.assertEqual(len(city_result.proposed_rules), 1)
        self.assertEqual(city_result.proposed_rules[0]["field_id"], "city")
        self.assertEqual(city_result.proposed_rules[0]["operator"], "in_contains")
        self.assertEqual(city_result.proposed_rules[0]["value"], ["深圳"])

    def test_trailing_cost_negation_does_not_block_university_preference(self) -> None:
        for text in ("想去深圳大学，不要太贵", "想去深圳大学不要太贵"):
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(
                    [(link["field_id"], link["value"]) for link in result.accepted_links],
                    [("university_name", "深圳大学")],
                )
                self.assertEqual(len(result.proposed_rules), 1)
                self.assertEqual(result.proposed_rules[0]["field_id"], "university_name")
                self.assertEqual(result.proposed_rules[0]["operator"], "eq")
                self.assertEqual(result.proposed_rules[0]["value"], "深圳大学")

    def test_preposed_single_character_negation_does_not_execute(self) -> None:
        cases = [
            ("别去深圳大学", "university_name"),
            ("别去读深圳大学", "university_name"),
            ("别报深圳大学", "university_name"),
            ("别报考深圳大学", "university_name"),
            ("别选深圳大学", "university_name"),
            ("别选报深圳大学", "university_name"),
            ("别考虑深圳大学", "university_name"),
            ("别去深圳的大学", "city"),
            ("别考虑去深圳的大学", "city"),
        ]
        for text, field_id in cases:
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(result.accepted_links, [])
                self.assertEqual(result.proposed_rules, [])
                self.assertEqual(result.not_executed_links[0]["field_id"], field_id)
                self.assertEqual(
                    result.not_executed_links[0]["reason"],
                    "否定/排除上下文不能直接执行为正向实体筛选。",
                )

    def test_trailing_fee_negation_does_not_block_entity_preference(self) -> None:
        cases = [
            ("想去深圳大学，不要学费太贵", "university_name", "深圳大学"),
            ("想去深圳大学不想学费太高", "university_name", "深圳大学"),
            ("想去深圳的大学，不要学费太贵", "city", "深圳"),
            ("想去深圳的大学不想学费太高", "city", "深圳"),
        ]
        for text, field_id, value in cases:
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(
                    [(link["field_id"], link["value"]) for link in result.accepted_links],
                    [(field_id, value)],
                )
                self.assertEqual(len(result.proposed_rules), 1)
                self.assertEqual(result.proposed_rules[0]["field_id"], field_id)

    def test_preposed_fee_negation_does_not_block_entity_preference(self) -> None:
        cases = [
            ("不想学费太高，深圳大学可以", "university_name", "深圳大学"),
            ("不要学费太贵，深圳的大学可以", "city", "深圳"),
        ]
        for text, field_id, value in cases:
            with self.subTest(text=text):
                result = _link(text)

                self.assertEqual(
                    [(link["field_id"], link["value"]) for link in result.accepted_links],
                    [(field_id, value)],
                )
                self.assertEqual(len(result.proposed_rules), 1)
                self.assertEqual(result.proposed_rules[0]["field_id"], field_id)


def _link(
    text: str,
    *,
    university_values: list[str] | None = None,
    city_values: list[str] | None = None,
    university_lookup_complete: object = True,
    extra_registry_fields: dict[str, dict[str, object]] | None = None,
    extra_index_fields: dict[str, dict[str, object]] | None = None,
):
    registry = _registry(extra_fields=extra_registry_fields)
    value_index = SchemaValueIndex(
        _value_index_payload(
            university_values=university_values or ["深圳大学"],
            city_values=city_values or ["深圳", "广州"],
            university_lookup_complete=university_lookup_complete,
            extra_fields=extra_index_fields,
        )
    )
    return ReviewedValueEntityLinker(registry, value_index).link(text)


def _registry(
    extra_fields: dict[str, dict[str, object]] | None = None,
) -> SchemaRegistry:
    configured = {
        "university_name": {
            "source_column": "院校名称",
            "type": "string",
            "allowed_ops": ["contains", "eq"],
        },
        "city": {
            "source_column": "城市",
            "type": "string",
            "allowed_ops": ["contains", "in_contains"],
        },
        **(extra_fields or {}),
    }
    active = {
        field_id: spec
        for field_id, spec in configured.items()
        if spec.get("active", True)
    }
    return SchemaRegistry(active_fields=active, configured_fields=configured)


def _value_index_payload(
    *,
    university_values: list[str],
    city_values: list[str],
    university_lookup_complete: bool,
    extra_fields: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    fields = {
        "university_name": {
            "source_column": "院校名称",
            "active": True,
            "type": "string",
            "allowed_ops": ["contains", "eq"],
            "lookup_complete": university_lookup_complete,
            "lookup_values": university_values,
        },
        "city": {
            "source_column": "城市",
            "active": True,
            "type": "string",
            "allowed_ops": ["contains", "in_contains"],
            "lookup_complete": True,
            "lookup_values": city_values,
        },
    }
    for field_id, spec in (extra_fields or {}).items():
        fields[field_id] = dict(spec)
    return {
        "source": {"fingerprint": "fixture-index"},
        "warehouse": {"row_count": 3},
        "fields": fields,
    }


if __name__ == "__main__":
    unittest.main()
