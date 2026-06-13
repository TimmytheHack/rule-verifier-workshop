from __future__ import annotations

import unittest
from collections import Counter

from scripts.run_demo_acceptance import (
    CASES,
    DemoCase,
    record_from_response,
)


class DemoAcceptanceScriptTest(unittest.TestCase):
    def test_case_counts_match_acceptance_scope(self) -> None:
        counts = Counter(case.domain for case in CASES)

        self.assertEqual(len(CASES), 25)
        self.assertEqual(counts["admissions"], 15)
        self.assertEqual(counts["housing"], 5)
        self.assertEqual(counts["products"], 5)

    def test_record_contains_required_report_fields(self) -> None:
        case = DemoCase(
            case_id="unit_01",
            domain="products",
            query="Audio products under 100.",
            expected_status="ok",
        )
        response = {
            "schema_version": "workbench_response.v1",
            "domain": "products",
            "domain_version": "1",
            "domain_pack_status": "approved",
            "status": "ok",
            "query": {"text": case.query},
            "answer": "Found products.",
            "result_count": 1,
            "items": [
                {
                    "item_id": "result_001",
                    "title": "Speaker Mini",
                    "subtitle": "audio",
                    "primary_attributes": [],
                    "secondary_attributes": [],
                    "matched_filters": [],
                    "raw": {},
                }
            ],
            "top_results": [{"product_name": "Speaker Mini"}],
            "executed_filters": [{"id": "e_category"}],
            "candidates_to_confirm": [],
            "confirmed_rules": [],
            "unconfirmed_candidates": [],
            "unexecuted_preferences": [],
            "no_schema_field_preferences": [],
            "rejected_confirmations": [],
            "warnings": [],
            "evidence_pack": {
                "execution_summary": {
                    "sql": "SELECT * FROM products WHERE category = ?",
                    "params": ["audio"],
                }
            },
            "debug_trace": {},
        }

        record = record_from_response(case, response)

        self.assertTrue(record["pass"])
        for key in [
            "domain",
            "query",
            "status",
            "items",
            "top_results",
            "executed_filters",
            "candidates_to_confirm",
            "unexecuted_preferences",
            "sql",
            "params",
            "evidence_pack",
            "answer",
            "pass",
        ]:
            self.assertIn(key, record)


if __name__ == "__main__":
    unittest.main()
