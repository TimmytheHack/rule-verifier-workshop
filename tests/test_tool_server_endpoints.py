from __future__ import annotations

import json
import unittest
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=Warning,
)

from fastapi.testclient import TestClient

from src.api.server import app
from tests.test_tool_contract import (
    _actor,
    _generated_generic_dataset,
    _queryable_generic_dataset,
)
from tests.workbench_contract_utils import assert_workbench_contract


class ToolServerEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_tools_list_filters_by_actor_permission(self) -> None:
        response = self.client.get(
            "/tools/list",
            headers={"X-Permission-Scopes": "query"},
        )
        payload = response.json()
        names = {tool["name"] for tool in payload["tools"]}

        self.assertEqual(response.status_code, 200)
        self.assertIn("workbench.query", names)
        self.assertNotIn("dataset.approve_op", names)
        self.assertNotIn("dataset.build_warehouse", names)

    def test_llm_safe_list_excludes_admin_tools(self) -> None:
        response = self.client.get("/tools/list", params={"llm_safe_only": "true"})
        names = {tool["name"] for tool in response.json()["tools"]}

        self.assertEqual(response.status_code, 200)
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
        self.assertFalse(any(name.startswith("dataset.approve") for name in names))
        self.assertNotIn("dataset.build_warehouse", names)
        self.assertNotIn("quality.run", names)
        self.assertNotIn("pilot.run", names)

    def test_tool_schema_endpoint_returns_contract(self) -> None:
        response = self.client.get("/tools/workbench.query/schema")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["name"], "workbench.query")
        self.assertIn("input_schema", payload)
        self.assertIn("output_schema", payload)

    def test_tool_invoke_permission_denied_is_structured(self) -> None:
        response = self.client.post(
            "/tools/dataset.approve_op/invoke",
            json={
                "payload": {
                    "dataset_id": "ds_missing",
                    "field_id": "city",
                    "op": "in",
                },
                "actor_context": {
                    "actor_id": "query_only",
                    "permission_scopes": ["query"],
                },
            },
        )
        payload = response.json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["detail"]["code"], "permission_denied")
        self.assertNotIn("Traceback", json.dumps(payload))

    def test_tool_invoke_error_redacts_absolute_path(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            response = self.client.post(
                "/tools/dataset.upload/invoke",
                json={
                    "payload": {
                        "filename": "missing.csv",
                        "source_path": "/Users/tz/Desktop/Projects/SZU/missing.csv",
                    },
                    "actor_context": {
                        "actor_id": "operator",
                        "permission_scopes": ["dataset_write"],
                        "dataset_root": str(root / "managed"),
                        "audit_path": str(root / "audit.jsonl"),
                    },
                },
            )
            audit_text = (root / "audit.jsonl").read_text(encoding="utf-8")
        serialized = json.dumps(response.json(), ensure_ascii=False)

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("/Users/tz", serialized)
        self.assertNotIn("Traceback", serialized)
        self.assertNotIn("/Users/tz", audit_text)

    def test_workbench_query_invoke_returns_response_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _queryable_generic_dataset(root)
            response = self.client.post(
                "/tools/workbench.query/invoke",
                json={
                    "payload": {
                        "dataset_id": dataset_id,
                        "natural_language": "Austin under 1900",
                        "deterministic_fields": {
                            "city": ["Austin"],
                            "rent_usd": 1900,
                        },
                    },
                    "actor_context": _actor(root, ["query"]),
                },
            )
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        assert_workbench_contract(self, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["items"])

    def test_admin_approve_op_invoke_writes_audit_event(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _generated_generic_dataset(root)
            actor = _actor(root, ["review_admin"])
            field_response = self.client.post(
                "/tools/dataset.approve_field/invoke",
                json={
                    "payload": {"dataset_id": dataset_id, "field_id": "city"},
                    "actor_context": actor,
                },
            )
            op_response = self.client.post(
                "/tools/dataset.approve_op/invoke",
                json={
                    "payload": {
                        "dataset_id": dataset_id,
                        "field_id": "city",
                        "op": "in",
                    },
                    "actor_context": actor,
                },
            )
            audit_lines = [
                json.loads(line)
                for line in (root / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(field_response.status_code, 200)
        self.assertEqual(op_response.status_code, 200)
        self.assertTrue(op_response.json()["ok"])
        last = audit_lines[-1]
        self.assertEqual(last["tool_name"], "dataset.approve_op")
        self.assertEqual(last["status"], "ok")
        self.assertIn("duration_seconds", last)
        self.assertIn("side_effects", last)
        self.assertIn("writes review.yaml", last["side_effects"])

    def test_audit_log_redacts_secret_and_path_material(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actor = {
                "actor_id": "operator_secret_token",
                "permission_scopes": ["read_only"],
                "dataset_root": str(root / "managed"),
                "audit_path": str(root / "audit.jsonl"),
            }
            response = self.client.post(
                "/tools/evidence.get/invoke",
                json={
                    "payload": {
                        "workbench_response": {
                            "evidence_pack": {
                                "safe": "ok",
                                "source_path": "/Users/tz/Desktop/Projects/SZU/.env",
                                "api_key": "sk-secret",
                            }
                        }
                    },
                    "actor_context": actor,
                },
            )
            audit_text = (root / "audit.jsonl").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("operator_secret_token", audit_text)
        self.assertNotIn("/Users/tz", audit_text)
        self.assertNotIn("sk-secret", audit_text)
        self.assertNotIn("api_key", audit_text)


if __name__ == "__main__":
    unittest.main()
