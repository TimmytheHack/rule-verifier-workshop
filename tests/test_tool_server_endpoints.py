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
from tests.test_uploaded_dataset_flow import (
    FakeSemanticIntentClient,
    _evidence_requirements_for_basic_recommendation,
    _queryable_uploaded_admissions,
    _semantic_recommendation_intent_without_context,
)
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
        server_module.preflight_store.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.auth_patcher.stop()

    def test_workbench_preflight_endpoint_returns_contract(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        fake_client = FakeSemanticIntentClient(
            [
                _semantic_recommendation_intent_without_context(),
                _evidence_requirements_for_basic_recommendation(),
            ]
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch.object(server_module, "dataset_service", service):
                with patch(
                    "src.api.workbench.deepseek_slot_adapter_enabled",
                    return_value=True,
                ):
                    with patch(
                        "src.api.workbench._interactive_deepseek_client",
                        return_value=fake_client,
                    ):
                        response = self.client.post(
                            "/workbench/preflight",
                            headers=_auth_headers("query-token"),
                            json={
                                "dataset_id": dataset_id,
                                "domain_name": "admissions",
                                "user_input": prompt,
                                "hard_filters": {
                                    "source_province": "广东",
                                    "subject_type": "物理",
                                    "reselected_subjects": ["化学", "生物"],
                                    "user_rank": 15000,
                                },
                                "soft_preferences": {"prompt": prompt},
                                "planner_mode": "llm_semantic",
                            },
                        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema_version"], "workbench_preflight.v1")
        self.assertEqual(payload["dataset_id"], dataset_id)
        self.assertEqual(payload["items"], [])
        fact_sources = {item["source"] for item in payload["recognized_facts"]}
        self.assertIn("hard_filters.subject_type", fact_sources)
        self.assertIn("hard_filters.reselected_subjects", fact_sources)
        self.assertNotIn("sql", json.dumps(payload, ensure_ascii=False).lower())

    def test_workbench_query_rejects_forged_preflight_confirmation(self) -> None:
        prompt = "我的排位是15000，想读人工智能，稳一点"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch.object(server_module, "dataset_service", service):
                response = self.client.post(
                    "/workbench/query",
                    headers=_auth_headers("query-token"),
                    json={
                        "dataset_id": dataset_id,
                        "domain_name": "admissions",
                        "user_input": prompt,
                        "hard_filters": {
                            "source_province": "广东",
                            "subject_type": "物理",
                            "reselected_subjects": ["化学", "生物"],
                            "user_rank": 15000,
                        },
                        "soft_preferences": {"prompt": prompt},
                        "planner_mode": "llm_semantic",
                        "preflight_id": "pf_forged",
                        "confirmed_boundaries": [
                            {
                                "confirmation_id": "pfc_forged",
                                "option_id": "rank_window_steady",
                            }
                        ],
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["detail"]["code"], "invalid_preflight")

    def test_workbench_query_accepts_current_preflight_reference(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        fake_client = FakeSemanticIntentClient(
            [
                _semantic_recommendation_intent_without_context(),
                _evidence_requirements_for_basic_recommendation(),
                _semantic_recommendation_intent_without_context(),
                _evidence_requirements_for_basic_recommendation(),
                {"criteria": []},
            ]
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch.object(server_module, "dataset_service", service):
                with patch(
                    "src.api.workbench.deepseek_slot_adapter_enabled",
                    return_value=True,
                ):
                    with patch(
                        "src.api.workbench._interactive_deepseek_client",
                        return_value=fake_client,
                    ):
                        preflight_response = self.client.post(
                            "/workbench/preflight",
                            headers=_auth_headers("query-token"),
                            json={
                                "dataset_id": dataset_id,
                                "domain_name": "admissions",
                                "user_input": prompt,
                                "hard_filters": {
                                    "source_province": "广东",
                                    "subject_type": "物理",
                                    "reselected_subjects": ["化学", "生物"],
                                    "user_rank": 15000,
                                },
                                "soft_preferences": {"prompt": prompt},
                                "planner_mode": "llm_semantic",
                            },
                        )
                        preflight = preflight_response.json()
                        response = self.client.post(
                            "/workbench/query",
                            headers=_auth_headers("query-token"),
                            json={
                                "dataset_id": dataset_id,
                                "domain_name": "admissions",
                                "user_input": prompt,
                                "hard_filters": {
                                    "source_province": "广东",
                                    "subject_type": "物理",
                                    "reselected_subjects": ["化学", "生物"],
                                    "user_rank": 15000,
                                },
                                "soft_preferences": {"prompt": prompt},
                                "planner_mode": "llm_semantic",
                                "preflight_id": preflight["preflight_id"],
                                "confirmed_boundaries": [],
                                "disabled_boundaries": [],
                            },
                        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        assert_workbench_contract(self, payload)
        self.assertIn(
            payload["status"],
            {"ok", "needs_confirmation", "no_results", "blocked"},
        )
        context = payload["evidence_pack"]["semantic_intent"]["user_context"]
        self.assertEqual(context["subject_type"], "物理")
        self.assertEqual(context["reselected_subjects"], ["化学", "生物"])

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
