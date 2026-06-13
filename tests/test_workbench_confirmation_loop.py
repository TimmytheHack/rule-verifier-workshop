from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse


PRD_PROMPT = "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。"
JIKE_PROMPT = "广东物理，物化生，排位32000，想学计科，广深优先。"


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
            return candidate["candidate_id"]
    raise AssertionError(f"Missing candidate for {source_text}")


class WorkbenchConfirmationLoopTest(unittest.TestCase):
    def test_pearl_river_delta_without_confirmation_does_not_execute(self) -> None:
        result = _run(PRD_PROMPT)

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn("珠三角", [c["source_text"] for c in result["confirmation_candidates"]])
        self.assertNotIn("e_city", result["execution"]["hard_rule_ids"])
        self.assertFalse(
            any(rule_id.startswith("e_confirmed_") for rule_id in result["execution"]["hard_rule_ids"])
        )
        self.assertNotIn("珠三角", result["execution"]["params"])
        self.assertEqual(result["result_count"], 749)

    def test_pearl_river_delta_confirmation_executes_city_candidate(self) -> None:
        first = _run(PRD_PROMPT)
        candidate_id = _candidate_id(first, "珠三角")
        result = _run(PRD_PROMPT, [candidate_id])

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn(candidate_id, result["confirmation_state"]["accepted_candidate_ids"])
        self.assertIn(
            f"e_confirmed_{candidate_id.replace('cand_', '')}",
            result["execution"]["hard_rule_ids"],
        )
        self.assertIn("广州", result["execution"]["params"])
        self.assertIn("深圳", result["execution"]["params"])
        self.assertIn("佛山", result["execution"]["params"])
        self.assertNotIn("珠三角", result["execution"]["params"])
        self.assertEqual(result["result_count"], 199)

    def test_jike_confirmation_executes_major_candidate(self) -> None:
        first = _run(JIKE_PROMPT)
        candidate_id = _candidate_id(first, "计科")
        result = _run(JIKE_PROMPT, [candidate_id])

        self.assertEqual(first["status"], "needs_confirmation")
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("e_major_keyword", first["execution"]["hard_rule_ids"])
        self.assertEqual(first["result_count"], 3962)
        self.assertIn(candidate_id, result["confirmation_state"]["accepted_candidate_ids"])
        self.assertIn(
            f"e_confirmed_{candidate_id.replace('cand_', '')}",
            result["execution"]["hard_rule_ids"],
        )
        self.assertIn("计算机", result["execution"]["params"])
        self.assertEqual(result["result_count"], 149)

    def test_unconfirmed_candidate_does_not_execute(self) -> None:
        result = _run(JIKE_PROMPT)

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(
            result["execution"]["hard_rule_ids"],
            ["e_source_province", "e_subject_type", "e_subject_requirement", "e_city"],
        )
        self.assertEqual(result["confirmation_state"]["accepted_candidate_ids"], [])
        self.assertEqual(result["confirmation_state"]["executed_after_confirmation"], [])

    def test_forged_candidate_id_is_rejected(self) -> None:
        result = _run(PRD_PROMPT, ["cand_forged"])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["confirmation_state"]["accepted_candidate_ids"], [])
        self.assertEqual(
            result["confirmation_state"]["rejected_candidates"][0]["candidate_id"],
            "cand_forged",
        )
        self.assertTrue(
            result["confirmation_state"]["rejected_candidates"][0]["blocks_execution"]
        )
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["execution"]["sql"], "")

    def test_candidate_id_from_other_query_is_rejected(self) -> None:
        first = _run(PRD_PROMPT)
        stale_candidate_id = _candidate_id(first, "珠三角")
        result = _run("广东物理，排位32000，想学计算机，广深优先。", [stale_candidate_id])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["confirmation_state"]["accepted_candidate_ids"], [])
        self.assertEqual(
            result["confirmation_state"]["rejected_candidates"][0]["candidate_id"],
            stale_candidate_id,
        )
        self.assertTrue(
            result["confirmation_state"]["rejected_candidates"][0]["blocks_execution"]
        )
        self.assertEqual(result["execution"]["hard_rule_ids"], [])
        self.assertEqual(result["execution"]["sql"], "")

    def test_no_schema_candidate_confirmation_never_executes(self) -> None:
        first = _run(PRD_PROMPT)
        candidate_id = _candidate_id(first, "不要校企合作")
        result = _run(PRD_PROMPT, [candidate_id])

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["confirmation_state"]["accepted_candidate_ids"], [])
        self.assertEqual(
            result["confirmation_state"]["rejected_candidates"][0]["candidate_id"],
            candidate_id,
        )
        self.assertIn(
            "不要校企合作",
            [
                item["source_text"]
                for item in result["evidence_pack"]["no_schema_field_preferences"]
            ],
        )
        self.assertNotIn("校企合作", result["execution"]["params"])

    def test_evidence_pack_records_confirmation_source(self) -> None:
        first = _run(PRD_PROMPT)
        candidate_id = _candidate_id(first, "珠三角")
        result = _run(PRD_PROMPT, [candidate_id])
        evidence = result["evidence_pack"]

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(evidence["confirmation_source"][0]["candidate_id"], candidate_id)
        self.assertEqual(evidence["confirmation_source"][0]["source_text"], "珠三角")
        self.assertEqual(
            evidence["confirmed_rules"][0]["confirmation_source"]["candidate_id"],
            candidate_id,
        )
        self.assertEqual(
            evidence["executed_after_confirmation"],
            [evidence["confirmed_rules"][0]["rule_id"]],
        )
        self.assertIn(
            "[确认执行] 珠三角 -> 城市：partial_match",
            result["natural_language_report"]["full_text"],
        )


if __name__ == "__main__":
    unittest.main()
