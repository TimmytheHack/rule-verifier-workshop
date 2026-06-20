from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import assert_workbench_contract


class ApiWorkbenchTest(unittest.TestCase):
    def test_workbench_top_results_use_frontend_field_names(self) -> None:
        result = run_workbench_with_test_warehouse(WorkbenchConfig())

        assert_workbench_contract(self, result)
        self.assertGreater(result["result_count"], 0)
        top_result = result["top_results"][0]
        self.assertIn("university_name", top_result)
        self.assertIn("group_code", top_result)
        self.assertIn("major_name", top_result)
        self.assertNotIn("院校名称", top_result)
        self.assertIsInstance(result["natural_language_report"]["top_results"], list)
        value_index_counts = result["attribute_grounding"]["summary"].get(
            "value_index_status_counts",
            {},
        )
        self.assertTrue(value_index_counts)
        self.assertTrue(
            any(
                record.get("value_index")
                for record in result["attribute_grounding"]["attributes"]
            )
        )
        execution = result["execution"]
        self.assertEqual(execution["executor"], "duckdb")
        self.assertIn("sql", execution)
        self.assertIsInstance(execution["params"], list)
        self.assertGreater(execution["input_row_count"], 0)
        self.assertGreaterEqual(execution["filtered_row_count"], result["result_count"])
        self.assertEqual(execution["top_k"], 5)
        self.assertTrue(execution["sort_key"])

    def test_workbench_rank_desc_sort_mode_uses_controlled_override(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(soft_preferences={"sort_mode": "rank_desc"})
        )

        assert_workbench_contract(self, result)
        execution = result["execution"]
        self.assertEqual(execution["executor"], "duckdb")
        self.assertTrue(execution["sort_key"][0].endswith("DESC NULLS LAST"))


if __name__ == "__main__":
    unittest.main()
