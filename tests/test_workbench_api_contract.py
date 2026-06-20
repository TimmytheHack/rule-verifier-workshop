from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from scripts.generate_domain_pack import generate_domain_pack
from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import (
    run_workbench_with_domain_warehouse,
    run_workbench_with_test_warehouse,
)
from tests.workbench_contract_utils import (
    FRONTEND_TOP_RESULT_KEYS,
    assert_workbench_contract,
)


OK_PROMPT = "广东物理，排位32000，想学计算机，广深优先。"
JIKE_PROMPT = "广东物理，物化生，排位32000，想学计科，广深优先。"
PRD_PROMPT = "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。"
NO_RESULTS_PROMPT = "广东物理，排位90000，想学网络安全，深圳。"
HOUSING_FIXTURE = "domains/housing/fixtures/housing.csv"


def _run(prompt: str, confirmed: list[str] | None = None) -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=prompt,
            extractor="regex",
            soft_preferences={"prompt": prompt},
            confirmed_candidates=confirmed or [],
        )
    )


def _candidate_id(result: dict[str, object], source_text: str) -> str:
    for candidate in result["confirmation_candidates"]:
        if candidate["source_text"] == source_text:
            return str(candidate["candidate_id"])
    raise AssertionError(f"Missing candidate for {source_text}")


def _contract_snapshot(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": result["status"],
        "result_count": result["result_count"],
        "top_count": len(result["top_results"]),
        "executed_filter_ids": [
            item["id"] for item in result["executed_filters"]
        ],
        "candidate_sources": [
            item["source_text"] for item in result["candidates_to_confirm"]
        ],
        "confirmed_rule_ids": [
            item["id"] for item in result["confirmed_rules"]
        ],
        "rejected_reason_codes": [
            item.get("reason_code")
            for item in result["rejected_confirmations"]
        ],
    }


class WorkbenchApiContractTest(unittest.TestCase):
    def test_admissions_ok_contract_shape_and_top_result_keys(self) -> None:
        result = _run(OK_PROMPT)

        assert_workbench_contract(self, result)
        self.assertIn("decision_guidance", result["evidence_pack"])
        self.assertEqual(
            result["evidence_pack"]["decision_guidance"]["execution_effect"],
            "does_not_change_sql_or_results",
        )
        self.assertEqual(result["schema_version"], "workbench_response.v1")
        self.assertEqual(result["domain"], "admissions")
        self.assertEqual(result["domain_pack_status"], "approved")
        self.assertTrue(result["items"])
        self.assertEqual(
            _contract_snapshot(result),
            {
                "status": "ok",
                "result_count": 149,
                "top_count": 5,
                "executed_filter_ids": [
                    "e_source_province",
                    "e_subject_type",
                    "e_major_keyword",
                    "e_city",
                ],
                "candidate_sources": [],
                "confirmed_rule_ids": [],
                "rejected_reason_codes": [],
            },
        )
        top_result = result["top_results"][0]
        self.assertIn("rank_2024", top_result)
        self.assertIn("plan_count", top_result)
        self.assertNotIn("院校名称", top_result)
        self.assertTrue(FRONTEND_TOP_RESULT_KEYS <= set(top_result))
        self.assertEqual(result["items"][0]["title"], top_result["university_name"])
        self.assertTrue(result["items"][0]["matched_filters"])
        self.assertIn("sql", result["evidence_pack"]["execution_summary"])

    def test_controlled_rank_window_enters_hard_filter(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input="广东物理，排位32000，计算机，广州。",
                hard_filters={
                    "source_province": "广东",
                    "subject_type": "物理",
                    "reselected_subjects": ["化学", "生物"],
                    "user_rank": 32000,
                    "major_keyword": "计算机",
                    "preferred_cities": ["广州"],
                    "tuition_cap_yuan": 20000,
                },
                soft_preferences={
                    "prompt": "",
                    "rank_window_label": "保底",
                    "rank_window_lower_percent": 0,
                    "rank_window_upper_percent": 50,
                    "tuition_cap_yuan": 20000,
                },
                extractor="regex",
            )
        )

        assert_workbench_contract(self, result)
        self.assertIn("e_safety_margin", result["execution"]["hard_rule_ids"])
        self.assertIn("e_tuition_cap_explicit", result["execution"]["hard_rule_ids"])
        self.assertNotIn(32000.0, result["execution"]["params"])
        self.assertIn(48000.0, result["execution"]["params"])
        confirmations = {
            item["confirmation_id"]: item
            for item in result["evidence_pack"]["candidate_confirmations"]
        }
        self.assertEqual(
            confirmations["safety_margin"]["status"],
            "promoted_to_executed_rule",
        )
        self.assertEqual(
            confirmations["safety_margin"]["selected_label"],
            "保底（后 50% 以内）",
        )
        self.assertEqual(confirmations["safety_margin"]["operator"], "<=")
        self.assertEqual(confirmations["safety_margin"]["value"], 48000)
        self.assertNotIn(
            "本次没有确认位次窗口规则",
            "\n".join(result["natural_language_report"]["warnings"]),
        )
        self.assertGreater(result["result_count"], 0)
        self.assertTrue(result["top_results"])
        for item in result["top_results"]:
            self.assertLessEqual(item["group_min_rank"], 48000)

    def test_needs_confirmation_keeps_partial_out_of_executed_filters(self) -> None:
        result = _run(JIKE_PROMPT)

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn("计科", [c["source_text"] for c in result["candidates_to_confirm"]])
        self.assertNotIn(
            "e_major_keyword",
            [item["id"] for item in result["executed_filters"]],
        )
        self.assertEqual(result["confirmed_rules"], [])
        self.assertFalse(
            any(
                item["id"].startswith("e_confirmed_")
                for item in result["executed_filters"]
            )
        )
        self.assertIn("needs_confirmation", [w["code"] for w in result["warnings"]])

    def test_confirmed_rerun_promotes_candidate_by_id_only(self) -> None:
        first = _run(JIKE_PROMPT)
        candidate_id = _candidate_id(first, "计科")
        result = _run(JIKE_PROMPT, [candidate_id])

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["confirmed_rules"][0]["candidate_id"], candidate_id)
        self.assertTrue(result["confirmed_rules"][0]["executed"])
        self.assertIn(
            result["confirmed_rules"][0]["id"],
            [item["id"] for item in result["executed_filters"]],
        )
        self.assertIn(
            result["confirmed_rules"][0]["id"],
            result["evidence_pack"]["execution_summary"]["hard_rule_ids"],
        )

    def test_no_results_contract_does_not_fabricate_recommendations(self) -> None:
        result = _run(NO_RESULTS_PROMPT)

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["top_results"], [])
        self.assertEqual(result["evidence_pack"]["top_k_results"], [])
        self.assertIn("共筛选到 0 条", result["answer"])
        self.assertIn("no_results", [warning["code"] for warning in result["warnings"]])
        self.assertEqual(result["items"], [])

    def test_blocked_contract_does_not_execute_sql(self) -> None:
        result = _run(PRD_PROMPT, ["cand_forged"])

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["top_results"], [])
        self.assertEqual(result["debug_trace"]["execution"]["executor"], None)
        self.assertEqual(result["debug_trace"]["execution"]["sql"], "")
        self.assertEqual(result["debug_trace"]["execution"]["params"], [])
        self.assertEqual(
            result["rejected_confirmations"][0]["reason_code"],
            "candidate_id_not_current_query",
        )

    def test_no_schema_confirmation_is_rejected_but_not_executed(self) -> None:
        first = _run(PRD_PROMPT)
        candidate_id = _candidate_id(first, "不要校企合作")
        result = _run(PRD_PROMPT, [candidate_id])

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(
            result["rejected_confirmations"][0]["reason_code"],
            "candidate_not_executable",
        )
        self.assertFalse(result["rejected_confirmations"][0]["blocks_execution"])
        self.assertIn(
            "不要校企合作",
            [
                item["source_text"]
                for item in result["no_schema_field_preferences"]
            ],
        )
        self.assertNotIn(
            "合作办学类型字段",
            [item["field"] for item in result["executed_filters"]],
        )

    def test_error_contract_hides_traceback(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(extractor="not-supported")
        )

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["top_results"], [])
        self.assertEqual(result["debug_trace"]["execution"]["sql"], "")
        self.assertNotIn("Traceback", result["answer"])
        self.assertNotIn("Traceback", str(result["warnings"]))
        self.assertIn("workbench_error", [w["code"] for w in result["warnings"]])

    def test_housing_returns_generic_items_and_domain_top_results(self) -> None:
        result = run_workbench_with_domain_warehouse(
            WorkbenchConfig(
                domain_name="housing",
                user_input="Austin, at least 2 bedrooms, under 1900.",
                hard_filters={
                    "city": ["Austin"],
                    "bedrooms_min": 2,
                    "rent_cap": 1900,
                    "property_types": ["apartment", "townhouse"],
                },
                soft_preferences={
                    "prompt": "Austin, at least 2 bedrooms, under 1900."
                },
                extractor="regex",
            )
        )

        assert_workbench_contract(self, result)
        self.assertEqual(result["domain"], "housing")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result_count"], 3)
        self.assertEqual(result["items"][0]["item_id"], "result_001")
        self.assertEqual(result["items"][0]["title"], "14")
        self.assertIn("rent_usd", result["top_results"][0])
        self.assertNotIn("university_name", result["top_results"][0])

    def test_products_returns_generic_items_and_domain_top_results(self) -> None:
        result = run_workbench_with_domain_warehouse(
            WorkbenchConfig(
                domain_name="products",
                user_input="audio products under 100",
                hard_filters={
                    "categories": ["audio"],
                    "price_cap": 100,
                },
                soft_preferences={"prompt": "audio products under 100"},
                extractor="regex",
            )
        )

        assert_workbench_contract(self, result)
        self.assertEqual(result["domain"], "products")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["items"][0]["title"], "Speaker Mini")
        self.assertEqual(result["top_results"][0]["product_name"], "Speaker Mini")
        self.assertEqual(result["top_results"][0]["price_usd"], 49)

    def test_draft_domain_pack_is_blocked_before_sql(self) -> None:
        with TemporaryDirectory() as directory:
            generated = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="draft_contract",
                output_root=directory,
            )
            result = run_workbench_with_domain_warehouse(
                WorkbenchConfig(
                    domain_name="draft_contract",
                    domain_path=str(generated.domain_dir),
                    user_input="Austin under 1900",
                    hard_filters={"city": ["Austin"], "rent_cap": 1900},
                    soft_preferences={"prompt": "Austin under 1900"},
                    extractor="regex",
                )
            )

        assert_workbench_contract(self, result)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["domain_pack_status"], "draft")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["debug_trace"]["execution"]["sql"], "")
        self.assertIn(
            "domain_pack_not_approved",
            [warning["code"] for warning in result["warnings"]],
        )

    def test_available_options_include_rank_windows_and_sort_modes(self) -> None:
        from src.api.workbench import available_options

        options = available_options()

        self.assertIn("rank_windows", options)
        self.assertIn("sort_modes", options)
        self.assertEqual(
            [item["value"] for item in options["rank_windows"]],
            ["reach", "steady", "safe"],
        )
        self.assertEqual(
            [
                (
                    item["rank_window_lower_percent"],
                    item["rank_window_upper_percent"],
                )
                for item in options["rank_windows"]
            ],
            [(0, 0), (0, 15), (0, 50)],
        )
        self.assertEqual(
            [item["value"] for item in options["sort_modes"]],
            ["rank_asc", "rank_desc", "school_rank_asc"],
        )

    def test_available_options_rank_windows_are_isolated_from_mutation(
        self,
    ) -> None:
        from src.api.workbench import available_options

        options = available_options()
        first_window = options["rank_windows"][0]
        original_value = first_window["value"]
        original_upper_percent = first_window["rank_window_upper_percent"]

        try:
            first_window["value"] = "mutated"
            first_window["rank_window_upper_percent"] = 99

            fresh_options = available_options()

            self.assertEqual(fresh_options["rank_windows"][0]["value"], "reach")
            self.assertEqual(
                fresh_options["rank_windows"][0]["rank_window_upper_percent"],
                0,
            )
        finally:
            first_window["value"] = original_value
            first_window["rank_window_upper_percent"] = original_upper_percent


if __name__ == "__main__":
    unittest.main()
