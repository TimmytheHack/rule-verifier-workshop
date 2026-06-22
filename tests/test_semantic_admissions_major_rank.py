from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.data_warehouse import build_structured_store_from_dataset
from src.domains import DomainConfig
from src.semantic.admissions_major_rank import AdmissionsMajorRankPlanner
from tests.semantic_test_utils import new_admissions_dataset


class AdmissionsMajorRankPlannerTest(unittest.TestCase):
    def test_major_rank_plan_returns_reach_match_safety(self) -> None:
        with TemporaryDirectory() as directory:
            dataset = next(new_admissions_dataset())
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

            result = AdmissionsMajorRankPlanner(
                domain_config=DomainConfig.load("admissions"),
                database_path=database_path,
                table_name="admissions",
            ).run("广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.query_type, "admissions_major_rank")
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


if __name__ == "__main__":
    unittest.main()
