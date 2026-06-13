from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig, run_workbench


class ApiWorkbenchTest(unittest.TestCase):
    def test_workbench_top_results_use_frontend_field_names(self) -> None:
        result = run_workbench(WorkbenchConfig())

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


if __name__ == "__main__":
    unittest.main()
