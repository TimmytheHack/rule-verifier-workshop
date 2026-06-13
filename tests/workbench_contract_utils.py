from __future__ import annotations

from typing import Any


CONTRACT_KEYS = {
    "schema_version",
    "domain",
    "domain_version",
    "domain_pack_status",
    "status",
    "query",
    "answer",
    "items",
    "top_results",
    "result_count",
    "executed_filters",
    "candidates_to_confirm",
    "confirmed_rules",
    "unconfirmed_candidates",
    "unexecuted_preferences",
    "no_schema_field_preferences",
    "rejected_confirmations",
    "warnings",
    "evidence_pack",
    "debug_trace",
}

STATUS_VALUES = {"ok", "needs_confirmation", "no_results", "blocked", "error"}
DOMAIN_PACK_STATUS_VALUES = {"draft", "needs_review", "approved", "blocked"}
ITEM_KEYS = {
    "item_id",
    "title",
    "subtitle",
    "primary_attributes",
    "secondary_attributes",
    "matched_filters",
    "raw",
}

FRONTEND_TOP_RESULT_KEYS = {
    "university_name",
    "group_code",
    "major_code",
    "major_name",
    "full_major_name",
    "city",
    "tuition",
    "rank_2024",
    "plan_count",
    "group_min_rank",
    "major_min_rank",
    "safety_margin",
}

CHINESE_TOP_RESULT_KEYS = {
    "院校名称",
    "院校专业组代码",
    "专业代码",
    "专业名称",
    "专业全称",
    "城市",
    "学费",
    "专业组最低位次1",
    "最低位次1",
}


def assert_workbench_contract(testcase: Any, payload: dict[str, Any]) -> None:
    testcase.assertTrue(CONTRACT_KEYS <= set(payload))
    testcase.assertEqual(payload["schema_version"], "workbench_response.v1")
    testcase.assertIsInstance(payload["domain"], str)
    testcase.assertIsInstance(payload["domain_version"], str)
    testcase.assertIn(payload["domain_pack_status"], DOMAIN_PACK_STATUS_VALUES)
    testcase.assertIn(payload["status"], STATUS_VALUES)
    testcase.assertIsInstance(payload["query"], dict)
    testcase.assertIsInstance(payload["answer"], str)
    testcase.assertIsInstance(payload["items"], list)
    testcase.assertIsInstance(payload["top_results"], list)
    testcase.assertIsInstance(payload["result_count"], int)
    testcase.assertIsInstance(payload["executed_filters"], list)
    testcase.assertIsInstance(payload["candidates_to_confirm"], list)
    testcase.assertIsInstance(payload["confirmed_rules"], list)
    testcase.assertIsInstance(payload["unconfirmed_candidates"], list)
    testcase.assertIsInstance(payload["unexecuted_preferences"], list)
    testcase.assertIsInstance(payload["no_schema_field_preferences"], list)
    testcase.assertIsInstance(payload["rejected_confirmations"], list)
    testcase.assertIsInstance(payload["warnings"], list)
    testcase.assertIsInstance(payload["evidence_pack"], dict)
    testcase.assertIsInstance(payload["debug_trace"], dict)
    for item in payload["items"]:
        testcase.assertTrue(ITEM_KEYS <= set(item))
        testcase.assertIsInstance(item["item_id"], str)
        testcase.assertIsInstance(item["title"], str)
        testcase.assertIsInstance(item["subtitle"], str)
        testcase.assertIsInstance(item["primary_attributes"], list)
        testcase.assertIsInstance(item["secondary_attributes"], list)
        testcase.assertIsInstance(item["matched_filters"], list)
        testcase.assertIsInstance(item["raw"], dict)
    for warning in payload["warnings"]:
        testcase.assertIsInstance(warning, dict)
        testcase.assertIn("code", warning)
        testcase.assertIn("message", warning)
    for result in payload["top_results"]:
        testcase.assertTrue(CHINESE_TOP_RESULT_KEYS.isdisjoint(result))
    if payload["domain"] != "admissions":
        return
    for result in payload["top_results"]:
        testcase.assertTrue(FRONTEND_TOP_RESULT_KEYS <= set(result))
        testcase.assertTrue(CHINESE_TOP_RESULT_KEYS.isdisjoint(result))
