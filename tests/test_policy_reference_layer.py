from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from src.domains import DomainConfig
from src.reporting.policy_reference import PolicyReferenceIndex
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import assert_workbench_contract


QUERY_WITH_REFERENCE = (
    "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省"
)
QUERY_WITHOUT_REFERENCE = (
    "我今年高考分数 630，想读人工智能、计算机，想留在广东省"
)


class PolicyReferenceLayerTest(unittest.TestCase):
    def test_policy_reference_index_returns_reference_only_hits(self) -> None:
        domain_config = DomainConfig.load("admissions")

        hits = PolicyReferenceIndex.from_domain_config(domain_config).match(
            QUERY_WITH_REFERENCE
        )

        self.assertTrue(hits)
        first = hits[0]
        self.assertEqual(first["status"], "reference_only")
        self.assertEqual(first["effect"], "does_not_change_sql_or_results")
        self.assertIn("cooperation_programs.md", first["source"])
        self.assertFalse(first["source"].startswith("/"))
        self.assertIn("国外", first["matched_terms"])

    def test_policy_reference_does_not_change_execution(self) -> None:
        with_reference = _run(QUERY_WITH_REFERENCE)
        without_reference = _run(QUERY_WITHOUT_REFERENCE)

        assert_workbench_contract(self, with_reference)
        references = with_reference["evidence_pack"]["policy_references"]
        self.assertTrue(references)
        self.assertIn("参考说明（不参与筛选）", with_reference["answer"])
        self.assertEqual(
            with_reference["evidence_pack"]["execution_summary"]["sql"],
            without_reference["evidence_pack"]["execution_summary"]["sql"],
        )
        self.assertEqual(
            with_reference["evidence_pack"]["execution_summary"]["params"],
            without_reference["evidence_pack"]["execution_summary"]["params"],
        )
        self.assertEqual(with_reference["result_count"], without_reference["result_count"])
        self.assertFalse(
            [
                item
                for item in with_reference["executed_filters"]
                if "policy" in str(item).lower()
            ]
        )

    def test_non_matching_query_has_no_policy_references(self) -> None:
        result = _run(QUERY_WITHOUT_REFERENCE)

        self.assertEqual(result["evidence_pack"]["policy_references"], [])
        self.assertNotIn("参考说明（不参与筛选）", result["answer"])


def _run(prompt: str) -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=prompt,
            soft_preferences={"prompt": prompt},
            extractor="regex",
        )
    )


if __name__ == "__main__":
    unittest.main()
