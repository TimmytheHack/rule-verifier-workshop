from __future__ import annotations

import json
import os
import subprocess
import unittest
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=Warning,
)

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from scripts.export_tool_manifest import MANIFEST_SCHEMA
from src.api.server import app


ROOT = Path(__file__).resolve().parents[1]


class ServerDeploymentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_ready_version(self) -> None:
        health = self.client.get("/healthz")
        ready = self.client.get("/readyz")
        version = self.client.get("/version")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "ok")
        self.assertTrue(ready.json()["checks"])
        self.assertEqual(version.status_code, 200)
        payload = version.json()
        self.assertIn("git_commit", payload)
        self.assertEqual(payload["schema_version"], "workbench_response.v1")
        self.assertEqual(payload["api_version"], "api.v1")
        self.assertEqual(payload["tool_contract_version"], "tools.v1")

    def test_openapi_and_tool_manifest_can_be_generated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            openapi_path = root / "openapi.json"
            manifest_path = root / "tool_manifest.json"
            openapi = subprocess.run(
                [
                    ".venv/bin/python",
                    "scripts/export_openapi.py",
                    "--output-path",
                    str(openapi_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            manifest = subprocess.run(
                [
                    ".venv/bin/python",
                    "scripts/export_tool_manifest.py",
                    "--output-path",
                    str(manifest_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(openapi.returncode, 0, openapi.stderr)
            self.assertEqual(manifest.returncode, 0, manifest.stderr)
            openapi_payload = json.loads(openapi_path.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn("/tools/{tool_name}/invoke", openapi_payload["paths"])
        Draft202012Validator(MANIFEST_SCHEMA).validate(manifest_payload)
        self.assertEqual(manifest_payload["tool_contract_version"], "tools.v1")
        self.assertGreaterEqual(len(manifest_payload["tools"]), 14)

    def test_makefile_targets_are_defined(self) -> None:
        content = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in [
            "bootstrap",
            "test",
            "quality",
            "pilot",
            "demo",
            "serve",
            "frontend",
            "clean-artifacts",
        ]:
            self.assertRegex(content, rf"(?m)^{target}:")

    def test_env_example_has_no_real_secret(self) -> None:
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in [
            "DATA_ROOT=",
            "OUTPUT_ROOT=",
            "UPLOAD_MAX_MB=",
            "AUTH_TOKENS_JSON=",
            "ENABLE_LLM=false",
            "DEEPSEEK_API_KEY=",
            "TOOL_AUDIT_LOG_PATH=",
            "TOOL_AUDIT_MAX_BYTES=",
            "TOOL_AUDIT_BACKUPS=",
            "FRONTEND_ORIGIN=",
            "LOG_LEVEL=",
        ]:
            self.assertIn(key, content)
        self.assertNotIn("sk-", content)
        self.assertNotIn("replace_with", content)
        self.assertRegex(content, r"(?m)^DEEPSEEK_API_KEY=$")

    def test_llm_settings_status_does_not_return_secret(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "operator-token": {
                                "actor_id": "operator",
                                "permission_scopes": ["read_only", "diagnostics"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                response = self.client.post(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                    json={
                        "enabled": True,
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "api_url": "https://api.deepseek.com/chat/completions",
                        "api_key": "secret-test-key",
                    },
                )
                status = self.client.get(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status.status_code, 200)
        payload = status.json()
        self.assertTrue(payload["api_key_configured"])
        self.assertNotIn("api_key", payload)
        self.assertNotIn("secret-test-key", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
