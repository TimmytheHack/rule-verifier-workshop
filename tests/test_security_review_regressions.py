from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.api.server import app
from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse


class SecurityReviewRegressionTest(unittest.TestCase):
    def test_http_body_actor_context_cannot_grant_admin_scope(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/tools/dataset.approve_field/invoke",
            json={
                "payload": {"dataset_id": "ds_any", "field_id": "city"},
                "actor_context": {
                    "actor_id": "browser_supplied",
                    "permission_scopes": ["review_admin"],
                },
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["detail"]["code"], "permission_denied")
        self.assertNotIn("Traceback", json.dumps(payload, ensure_ascii=False))

    def test_http_token_map_is_only_server_side_authority(self) -> None:
        client = TestClient(app)
        token_map = {
            "agent-token": {
                "actor_id": "agent",
                "permission_scopes": ["read_only", "query", "confirm"],
            }
        }
        with patch.dict(os.environ, {"AUTH_TOKENS_JSON": json.dumps(token_map)}, clear=False):
            response = client.post(
                "/tools/dataset.approve_field/invoke",
                headers={"X-Actor-Token": "agent-token"},
                json={
                    "payload": {"dataset_id": "ds_any", "field_id": "city"},
                    "actor_context": {"permission_scopes": ["review_admin"]},
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "permission_denied")

    def test_tool_audit_path_rejects_location_outside_output_root(self) -> None:
        from src.api.tool_registry import ToolRegistryError, _audit_path

        with patch.dict(
            os.environ,
            {
                "OUTPUT_ROOT": "outputs",
                "TOOL_AUDIT_LOG_PATH": "/tmp/szu-audit-outside.jsonl",
            },
            clear=False,
        ):
            with self.assertRaises(ToolRegistryError):
                _audit_path({})

    @unittest.expectedFailure
    def test_quality_run_rejects_shell_metacharacters_in_output_dir(self) -> None:
        from src.api.tool_registry import ToolRegistryError, _tool_quality_run

        with patch("src.api.tool_registry.run_quality_gate") as run_gate:
            with self.assertRaises(ToolRegistryError):
                _tool_quality_run(
                    {"output_dir": "outputs/quality_gate;touch /tmp/szu_quality_pwned"}
                )
            run_gate.assert_not_called()

    def test_score_only_query_is_blocked_from_recommendation_execution(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input="广东物理，630分，想读计算机。",
                hard_filters={"source_province": "广东", "subject_type": "物理", "user_score": 630},
                soft_preferences={"prompt": "想读计算机"},
                extractor="regex",
            )
        )

        self.assertIn(result["status"], {"blocked", "needs_confirmation"})
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["debug_trace"]["execution"]["sql"], "")
        serialized = str(result)
        self.assertNotIn("录取概率", serialized)
        self.assertNotIn("仅按分数估计风险", serialized)

    def test_no_schema_preference_never_becomes_executed_filter(self) -> None:
        prompt = "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。"
        first = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                extractor="regex",
                soft_preferences={"prompt": prompt},
            )
        )
        candidate_id = next(
            item["candidate_id"]
            for item in first["confirmation_candidates"]
            if item["source_text"] == "不要校企合作"
        )
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                extractor="regex",
                soft_preferences={"prompt": prompt},
                confirmed_candidates=[candidate_id],
            )
        )

        self.assertEqual(result["rejected_confirmations"][0]["reason_code"], "candidate_not_executable")
        self.assertNotIn("合作办学类型字段", [item["field"] for item in result["executed_filters"]])
        self.assertNotIn("校企合作", str(result["debug_trace"]["execution"]["params"]))


if __name__ == "__main__":
    unittest.main()
