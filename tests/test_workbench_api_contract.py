from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import assert_workbench_contract


OK_PROMPT = "广东物理，排位32000，想学计算机，广深优先。"
JIKE_PROMPT = "广东物理，物化生，排位32000，想学计科，广深优先。"
PRD_PROMPT = "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。"
NO_RESULTS_PROMPT = "广东物理，排位90000，想学网络安全，深圳。"


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
    def test_ok_contract_shape_and_top_result_keys(self) -> None:
        result = _run(OK_PROMPT)

        assert_workbench_contract(self, result)
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
        self.assertIn("sql", result["evidence_pack"]["execution_summary"])

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
        self.assertIn("workbench_error", [w["code"] for w in result["warnings"]])


if __name__ == "__main__":
    unittest.main()
