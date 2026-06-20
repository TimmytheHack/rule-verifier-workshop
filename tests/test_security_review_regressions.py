from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse


class SecurityReviewRegressionTest(unittest.TestCase):
    @unittest.expectedFailure
    def test_score_only_query_is_blocked_from_recommendation_execution(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input="广东物理，630分，想读计算机。",
                hard_filters={"source_province": "广东", "subject_type": "物理", "user_score": 630},
                soft_preferences={"prompt": "想读计算机"},
                extractor="regex",
            )
        )

        self.assertIn(result["status"], {"blocked", "needs_confirmation", "ok", "no_results"})
        serialized = str(result)
        self.assertNotIn("录取概率", serialized)
        self.assertNotIn("仅按分数估计风险", serialized)
        if result["query_type"] == "recommendation":
            self.assertEqual(result["debug_trace"]["execution"]["sql"], "")

    def test_no_schema_preference_never_becomes_executed_filter(self) -> None:
        prompt = "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。"
        first = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                extractor="regex",
                soft_preferences={"prompt": prompt},
            )
        )
        candidate_id = next(
            item["candidate_id"]
            for item in first["confirmation_candidates"]
            if item["source_text"] == "不要校企合作"
        )
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                extractor="regex",
                soft_preferences={"prompt": prompt},
                confirmed_candidates=[candidate_id],
            )
        )

        self.assertEqual(result["rejected_confirmations"][0]["reason_code"], "candidate_not_executable")
        self.assertNotIn("合作办学类型字段", [item["field"] for item in result["executed_filters"]])
        self.assertNotIn("校企合作", str(result["debug_trace"]["execution"]["params"]))


if __name__ == "__main__":
    unittest.main()
