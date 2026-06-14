from __future__ import annotations

import base64
import json
import os
import unittest
import warnings
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=Warning,
)

from fastapi.testclient import TestClient

from src.api import server as server_module
from src.api.server import app
from tests.test_tool_contract import (
    _actor,
    _generated_generic_dataset,
    _queryable_generic_dataset,
)
from tests.workbench_contract_utils import assert_workbench_contract


class ToolServerEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.auth_patcher = patch.dict(
            os.environ,
            {
                "AUTH_TOKENS_JSON": json.dumps(
                    {
                        "query-token": {
                            "actor_id": "query_agent",
                            "permission_scopes": ["query", "confirm"],
                        },
                        "reader-token": {
                            "actor_id": "reader",
                            "permission_scopes": ["read_only"],
                        },
                        "operator-token": {
                            "actor_id": "operator",
                            "permission_scopes": [
                                "read_only",
                                "query",
                                "confirm",
                                "dataset_write",
                                "review_admin",
                                "warehouse_admin",
                                "diagnostics",
                            ],
                        },
                    }
                )
            },
        )
        self.auth_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.auth_patcher.stop()

    def test_tools_list_filters_by_actor_permission(self) -> None:
        response = self.client.get(
            "/tools/list",
            headers=_auth_headers("query-token"),
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
            headers=_auth_headers("query-token"),
            json={
                "payload": {
                    "dataset_id": "ds_missing",
                    "field_id": "city",
                    "op": "in",
                },
                "actor_context": {"permission_scopes": ["review_admin"]},
            },
        )
        payload = response.json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["detail"]["code"], "permission_denied")
        self.assertNotIn("Traceback", json.dumps(payload))

    def test_tool_invoke_error_redacts_absolute_path(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with _server_roots(root):
                response = self.client.post(
                    "/tools/dataset.upload/invoke",
                    headers=_auth_headers("operator-token"),
                    json={
                        "payload": {
                            "filename": "missing.csv",
                            "source_path": "/Users/tz/Desktop/Projects/SZU/missing.csv",
                        },
                        "actor_context": {
                            "permission_scopes": ["dataset_write"],
                            "audit_path": "/Users/tz/Desktop/Projects/SZU/.env",
                        },
                    },
                )
                audit_text = (root / "tool_audit/audit.jsonl").read_text(encoding="utf-8")
        serialized = json.dumps(response.json(), ensure_ascii=False)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("/Users/tz", serialized)
        self.assertNotIn("Traceback", serialized)
        self.assertNotIn("/Users/tz", audit_text)

    def test_workbench_query_invoke_returns_response_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _queryable_generic_dataset(root)
            with _server_roots(root):
                response = self.client.post(
                    "/tools/workbench.query/invoke",
                    headers=_auth_headers("query-token"),
                    json={
                        "payload": {
                            "dataset_id": dataset_id,
                            "natural_language": "Austin under 1900",
                            "deterministic_fields": {
                                "city": ["Austin"],
                                "rent_usd": 1900,
                            },
                        },
                        "actor_context": {"permission_scopes": ["warehouse_admin"]},
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
            with _server_roots(root):
                field_response = self.client.post(
                    "/tools/dataset.approve_field/invoke",
                    headers=_auth_headers("operator-token"),
                    json={
                        "payload": {"dataset_id": dataset_id, "field_id": "city"},
                        "actor_context": {"permission_scopes": ["query"]},
                    },
                )
                op_response = self.client.post(
                    "/tools/dataset.approve_op/invoke",
                    headers=_auth_headers("operator-token"),
                    json={
                        "payload": {
                            "dataset_id": dataset_id,
                            "field_id": "city",
                            "op": "in",
                        },
                        "actor_context": {"permission_scopes": ["query"]},
                    },
                )
                audit_lines = [
                    json.loads(line)
                    for line in (root / "tool_audit/audit.jsonl").read_text(
                        encoding="utf-8"
                    ).splitlines()
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
            with _server_roots(root):
                response = self.client.post(
                    "/tools/evidence.get/invoke",
                    headers=_auth_headers("reader-token"),
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
                        "actor_context": {
                            "actor_id": "operator_secret_token",
                            "permission_scopes": ["warehouse_admin"],
                            "audit_path": "/Users/tz/Desktop/Projects/SZU/.env",
                        },
                    },
                )
                audit_text = (root / "tool_audit/audit.jsonl").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("operator_secret_token", audit_text)
        self.assertNotIn("/Users/tz", audit_text)
        self.assertNotIn("sk-secret", audit_text)
        self.assertNotIn("api_key", audit_text)

    def test_http_auth_ignores_browser_permission_scopes(self) -> None:
        response = self.client.post(
            "/tools/dataset.approve_op/invoke",
            json={
                "payload": {
                    "dataset_id": "ds_missing",
                    "field_id": "city",
                    "op": "in",
                },
                "actor_context": {
                    "actor_id": "browser",
                    "permission_scopes": ["review_admin"],
                },
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_legacy_workbench_run_endpoint_is_removed(self) -> None:
        response = self.client.post(
            "/api/workbench/run",
            json={"user_input": "test"},
            headers=_auth_headers("operator-token"),
        )

        self.assertEqual(response.status_code, 404)

def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def _server_roots(root: Path):
    with patch.object(server_module, "DATA_ROOT", root / "managed"):
        with patch.object(server_module, "OUTPUT_ROOT", root):
            with patch.dict(
                os.environ,
                {
                    "TOOL_AUDIT_LOG_PATH": str(root / "tool_audit/audit.jsonl"),
                    "OUTPUT_ROOT": str(root),
                },
            ):
                yield


if __name__ == "__main__":
    unittest.main()
