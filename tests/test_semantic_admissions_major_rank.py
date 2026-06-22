from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.generate_domain_pack import load_source_dataset
from src.adapters.data_warehouse import build_structured_store_from_dataset
from src.domains import DomainConfig
from src.semantic.admissions_major_rank import AdmissionsMajorRankPlanner
from tests.semantic_test_utils import NEW_ADMISSIONS_ROWS


class AdmissionsMajorRankPlannerTest(unittest.TestCase):
    def test_major_rank_plan_returns_reach_match_safety(self) -> None:
        result = self._run("广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.query_type, "admissions_major_rank")
        self.assertIn("物理类", result.execution_summary["params"])
        self.assertEqual([item["档位"] for item in result.rows], ["冲", "稳", "保"])
        self.assertEqual(result.rows[0]["院校名称"], "中山大学")
        self.assertEqual(result.rows[0]["专业"], "预防医学")
        self.assertEqual(result.rows[0]["最低录取排名"], 9850)
        self.assertEqual(result.rows[1]["院校名称"], "深圳大学")
        self.assertEqual(result.rows[1]["最低录取排名"], 10257)
        self.assertEqual(result.rows[2]["院校名称"], "暨南大学")
        self.assertEqual(result.rows[2]["最低录取排名"], 16212)
        self.assertNotIn("电子科技大学", [item["院校名称"] for item in result.rows])
        self.assertIn("city", [item["field_id"] for item in result.unanswerable_intents])
        self.assertIn(
            "tuition_yuan_per_year",
            [item["field_id"] for item in result.unanswerable_intents],
        )

    def test_major_rank_plan_filters_incompatible_subject_requirement(self) -> None:
        incompatible_row = {
            **NEW_ADMISSIONS_ROWS[0],
            "院校名称": "政治要求大学",
            "院校代码": "19999",
            "专业": "智能科学",
            "专业代码": "080907",
            "所属专业组": "（299）",
            "专业备注": "（普通类）",
            "选科要求": "首选物理，再选政治",
            "最低分数": 631,
            "最低位次": 9900,
            "是否985": "否",
            "是否211": "否",
        }

        result = self._run(
            "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名",
            extra_rows=[incompatible_row],
        )

        self.assertEqual(result.status, "ok")
        self.assertNotIn("政治要求大学", [item["院校名称"] for item in result.rows])
        self.assertEqual(result.rows[0]["院校名称"], "中山大学")
        self.assertEqual(result.rows[0]["最低录取排名"], 9850)

    def test_history_request_does_not_execute_physics_query(self) -> None:
        result = self._run("广东历史，10000名，列出冲稳保的次序，以及每个专业的最低录取排名")

        self.assertIn(result.status, {"blocked", "needs_confirmation"})
        self.assertFalse(result.execution_summary["sql"])
        self.assertIsNone(result.execution_summary["executor"])
        self.assertIn(
            "subject_type",
            [item["field_id"] for item in result.unanswerable_intents],
        )
        self.assertIn(
            "subject_type",
            [item.get("field_id") for item in result.warnings],
        )

    def test_missing_subject_context_requires_confirmation(self) -> None:
        result = self._run("广东，10000名，列出冲稳保的次序，以及每个专业的最低录取排名")

        self.assertEqual(result.status, "needs_confirmation")
        self.assertFalse(result.execution_summary["sql"])
        self.assertIsNone(result.execution_summary["executor"])
        self.assertIn(
            "subject_type",
            [item["field_id"] for item in result.unanswerable_intents],
        )

    def _run(
        self,
        user_request: str,
        extra_rows: list[dict[str, object]] | None = None,
    ):
        with TemporaryDirectory() as directory:
            rows = [dict(row) for row in NEW_ADMISSIONS_ROWS]
            rows.extend(extra_rows or [])
            source_path = Path(directory) / "new_admissions.xlsx"
            pd.DataFrame(rows).to_excel(source_path, index=False)
            dataset = load_source_dataset(source_path)
            database_path = Path(directory) / "admissions.duckdb"
            index_path = Path(directory) / "schema_value_index.json"
            build_structured_store_from_dataset(
                dataset=dataset,
                schema_path=DomainConfig.load("admissions").schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name="admissions",
                source_path=dataset.workbook_path,
            )

            return AdmissionsMajorRankPlanner(
                domain_config=DomainConfig.load("admissions"),
                database_path=database_path,
                table_name="admissions",
            ).run(user_request)


if __name__ == "__main__":
    unittest.main()
