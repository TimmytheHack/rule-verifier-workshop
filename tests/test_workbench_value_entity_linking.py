from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import assert_workbench_contract


class WorkbenchValueEntityLinkingTest(unittest.TestCase):
    def test_shenzhen_university_prompt_filters_university_not_city(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        filters = _filter_tuples(response)
        self.assertIn(("院校名称", "eq", "深圳大学"), filters)
        self.assertNotIn(("城市", "in_contains", ["深圳"]), filters)
        self.assertTrue(response["top_results"])
        self.assertTrue(
            all(item["university_name"] == "深圳大学" for item in response["top_results"])
        )

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(linking["status"], "applied")
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["accepted_links"]],
            [("university_name", "深圳大学")],
        )
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["suppressed_links"]],
            [("city", "深圳")],
        )
        self.assertEqual(
            response["debug_trace"]["entity_linking"]["accepted_links"][0]["value"],
            "深圳大学",
        )
        warning_messages = [warning["message"] for warning in response["warnings"]]
        self.assertTrue(any("缺少科类" in message for message in warning_messages))
        self.assertTrue(any("再选科目" in message for message in warning_messages))

    def test_shenzhen_city_prompt_filters_city_not_university(self) -> None:
        prompt = "我想去深圳的大学，目前排位15000，帮我看看有什么专业可以选"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        filters = _filter_tuples(response)
        self.assertIn(("城市", "in_contains", ["深圳"]), filters)
        self.assertNotIn(("院校名称", "eq", "深圳大学"), filters)
        self.assertTrue(response["top_results"])
        self.assertTrue(
            any(item["university_name"] != "深圳大学" for item in response["top_results"])
        )

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["accepted_links"]],
            [("city", "深圳")],
        )

    def test_nearby_prompt_does_not_execute_entity_or_city_substring(self) -> None:
        prompt = "我想找深圳大学附近的学校，目前排位15000"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        filters = _filter_tuples(response)
        self.assertNotIn(("院校名称", "eq", "深圳大学"), filters)
        self.assertNotIn(("城市", "in_contains", ["深圳"]), filters)

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(linking["accepted_links"], [])
        self.assertEqual(
            linking["not_executed_links"][0]["match_type"],
            "entity_linking_boundary_required",
        )
        self.assertEqual(linking["not_executed_links"][0]["source_text"], "深圳大学附近")

    def test_nearby_boundary_preserves_other_city_value_in_same_rule(self) -> None:
        prompt = "想找深圳大学附近的学校，也可以广州的大学，目前排位15000"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        filters = _filter_tuples(response)
        self.assertIn(("城市", "in_contains", ["广州"]), filters)
        self.assertNotIn(("城市", "in_contains", ["深圳"]), filters)

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["accepted_links"]],
            [("city", "广州")],
        )
        self.assertIn(
            ("深圳大学附近", "entity_linking_boundary_required"),
            [
                (link["source_text"], link["match_type"])
                for link in linking["not_executed_links"]
            ],
        )

    def test_non_executable_entity_context_blocks_regex_city_filter(self) -> None:
        cases = [
            ("不要深圳大学，目前排位15000", "否定/排除"),
            ("离深圳大学近一点，目前排位15000", "距离/模糊地理边界"),
            ("深圳户籍考生，目前排位15000", "身份/户籍"),
        ]
        for prompt, reason_fragment in cases:
            with self.subTest(prompt=prompt):
                response = _run(prompt)

                assert_workbench_contract(self, response)
                self.assertNotIn(
                    ("城市", "in_contains", ["深圳"]),
                    _filter_tuples(response),
                )
                linking = response["evidence_pack"]["entity_linking"]
                self.assertTrue(
                    any(
                        link.get("field_id") == "city"
                        and link.get("value") == "深圳"
                        and reason_fragment in link.get("reason", "")
                        for link in linking["not_executed_links"]
                    )
                )


def _run(prompt: str) -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=prompt,
            soft_preferences={"prompt": prompt},
            planner_mode="legacy",
        )
    )


def _filter_tuples(response: dict[str, object]) -> list[tuple[object, object, object]]:
    return [
        (item["field"], item["operator"], item["value"])
        for item in response["executed_filters"]
    ]


if __name__ == "__main__":
    unittest.main()
