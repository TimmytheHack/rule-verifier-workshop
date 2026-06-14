from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.api.mcp_tool_adapter import MCPToolAdapter
from tests.test_tool_contract import _actor, _queryable_generic_dataset
from tests.workbench_contract_utils import assert_workbench_contract


class MCPToolAdapterTest(unittest.TestCase):
    def test_default_list_tools_contains_only_llm_safe_tools(self) -> None:
        adapter = MCPToolAdapter()
        payload = adapter.list_tools()
        names = {tool["name"] for tool in payload["tools"]}

        self.assertEqual(payload["tool_contract_version"], "tools.v1")
        self.assertEqual(
            names,
            {
                "dataset.profile",
                "dataset.review_summary",
                "workbench.query",
                "workbench.confirm",
                "evidence.get",
            },
        )
        self.assertNotIn("dataset.approve_op", names)
        for tool in payload["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertIn("description", tool)

    def test_call_profile_query_confirm_and_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _queryable_generic_dataset(root)
            adapter = MCPToolAdapter()
            actor = _actor(root, ["read_only", "query", "confirm"])

            profile = adapter.call_tool(
                "dataset.profile",
                {"dataset_id": dataset_id},
                actor,
            )
            query = adapter.call_tool(
                "workbench.query",
                {
                    "dataset_id": dataset_id,
                    "natural_language": "Austin under 1900",
                    "deterministic_fields": {
                        "city": ["Austin"],
                        "rent_usd": 1900,
                    },
                },
                actor,
            )
            confirmed = adapter.call_tool(
                "workbench.confirm",
                {
                    "previous_response": query["structuredContent"],
                    "confirmed_candidate_ids": ["forged_candidate_id"],
                },
                actor,
            )
            evidence = adapter.call_tool(
                "evidence.get",
                {"workbench_response": query["structuredContent"]},
                actor,
            )

        self.assertFalse(profile["isError"])
        self.assertTrue(profile["structuredContent"]["fields"])
        self.assertFalse(query["isError"])
        assert_workbench_contract(self, query["structuredContent"])
        self.assertEqual(query["structuredContent"]["status"], "ok")
        self.assertFalse(confirmed["isError"])
        self.assertEqual(confirmed["structuredContent"]["status"], "blocked")
        self.assertTrue(confirmed["structuredContent"]["rejected_confirmations"])
        self.assertFalse(evidence["isError"])
        self.assertIn("evidence_pack", evidence["structuredContent"])

    def test_admin_tool_call_is_denied(self) -> None:
        response = MCPToolAdapter().call_tool(
            "dataset.approve_op",
            {"dataset_id": "ds_any", "field_id": "city", "op": "in"},
            {"actor_id": "agent", "permission_scopes": ["query"]},
        )
        serialized = json.dumps(response, ensure_ascii=False)

        self.assertTrue(response["isError"])
        self.assertEqual(
            response["structuredContent"]["error"]["code"],
            "tool_not_allowed",
        )
        self.assertNotIn("Traceback", serialized)
        self.assertNotIn("/Users/", serialized)


if __name__ == "__main__":
    unittest.main()
