from __future__ import annotations

import json
import os
import stat
import subprocess
import unittest
import warnings
from inspect import signature
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
from src.api.dataset_service import DatasetService
from src.extractors.deepseek_extractor import env_value
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

    def test_distribution_mode_status(self) -> None:
        with patch.dict(
            os.environ,
            {"APP_DISTRIBUTION_MODE": "user_upload_only"},
            clear=False,
        ):
            response = self.client.get("/version")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["distribution_mode"], "user_upload_only")

    def test_uploaded_dataset_llm_model_defaults_to_local_settings(self) -> None:
        query_default = signature(DatasetService.query).parameters["model"].default
        preflight_default = signature(DatasetService.preflight).parameters[
            "model"
        ].default

        self.assertEqual(query_default, "")
        self.assertEqual(preflight_default, "")

    def test_user_upload_only_requires_dataset_for_workbench_query(self) -> None:
        token_map = {
            "local-token": {
                "actor_id": "local_app",
                "permission_scopes": ["query"],
            }
        }
        with patch.dict(
            os.environ,
            {
                "APP_DISTRIBUTION_MODE": "user_upload_only",
                "AUTH_TOKENS_JSON": json.dumps(token_map),
            },
            clear=False,
        ):
            response = self.client.post(
                "/workbench/query",
                headers={"X-Actor-Token": "local-token"},
                json={"user_input": "看看内置 admissions"},
            )
            tool_response = self.client.post(
                "/tools/workbench.query/invoke",
                headers={"X-Actor-Token": "local-token"},
                json={"payload": {"natural_language": "看看内置 admissions"}},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "dataset_id_required")
        self.assertEqual(tool_response.status_code, 400)
        self.assertEqual(
            tool_response.json()["detail"]["code"],
            "invalid_tool_request",
        )
        self.assertIn("dataset_id", tool_response.json()["detail"]["message"])

    def test_user_upload_only_hides_dev_tools_and_domain_templates(self) -> None:
        token_map = {
            "local-token": {
                "actor_id": "local_app",
                "permission_scopes": [
                    "read_only",
                    "query",
                    "confirm",
                    "dataset_write",
                    "review_admin",
                    "warehouse_admin",
                    "diagnostics",
                ],
            }
        }
        with patch.dict(
            os.environ,
            {
                "APP_DISTRIBUTION_MODE": "user_upload_only",
                "AUTH_TOKENS_JSON": json.dumps(token_map),
            },
            clear=False,
        ):
            tools_response = self.client.get(
                "/tools/list",
                headers={"X-Actor-Token": "local-token"},
            )
            schema_response = self.client.get("/tools/quality.run/schema")
            template_response = self.client.post(
                "/tools/dataset.generate_domain_pack/invoke",
                headers={"X-Actor-Token": "local-token"},
                json={
                    "payload": {
                        "dataset_id": "uploaded_table",
                        "template_id": "admissions_schema_v1",
                    }
                },
            )

        names = {tool["name"] for tool in tools_response.json()["tools"]}
        self.assertEqual(tools_response.status_code, 200)
        self.assertNotIn("quality.run", names)
        self.assertNotIn("pilot.run", names)
        self.assertEqual(schema_response.status_code, 400)
        self.assertEqual(template_response.status_code, 400)
        self.assertIn(
            "domain templates",
            template_response.json()["detail"]["message"],
        )

    def test_frontend_user_dist_is_served_without_auth(self) -> None:
        with TemporaryDirectory() as directory:
            dist = Path(directory)
            assets = dist / "assets"
            assets.mkdir()
            (dist / "index.html").write_text(
                "<!doctype html><div id='app'>本地表格工作台</div>",
                encoding="utf-8",
            )
            (assets / "app.js").write_text("console.log('ok');", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "FRONTEND_USER_DIST": str(dist),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "operator-token": {
                                "actor_id": "operator",
                                "permission_scopes": ["read_only", "diagnostics"],
                            }
                        }
                    ),
                    "LOCAL_USER_AUTO_AUTH_TOKEN": "operator-token",
                },
                clear=False,
            ):
                anonymous = TestClient(app)
                protected_api = anonymous.get("/datasets")
                home = self.client.get("/")
                asset = self.client.get("/assets/app.js")
                datasets = self.client.get("/datasets")
                settings = self.client.get("/settings/llm")
                unknown_api = self.client.get("/api/not-found")

        self.assertEqual(protected_api.status_code, 403)
        self.assertEqual(home.status_code, 200)
        self.assertIn("本地表格工作台", home.text)
        cookie_header = home.headers.get("set-cookie", "")
        self.assertIn("actor_token=operator-token", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=lax", cookie_header)
        self.assertEqual(self.client.cookies.get("actor_token"), "operator-token")
        self.assertEqual(asset.status_code, 200)
        self.assertIn("console.log", asset.text)
        self.assertEqual(datasets.status_code, 200)
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(unknown_api.status_code, 404)

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
            "serve-user",
            "macos-app",
            "macos-dmg",
            "frontend",
            "frontend-user-build",
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
            "LLM_PROVIDER=deepseek",
            "LLM_API_KEY=",
            "LLM_MODEL=deepseek-chat",
            "LLM_API_URL=https://api.deepseek.com/chat/completions",
            "DEEPSEEK_API_KEY=",
            "TOOL_AUDIT_LOG_PATH=",
            "TOOL_AUDIT_MAX_BYTES=",
            "TOOL_AUDIT_BACKUPS=",
            "FRONTEND_ORIGIN=",
            "FRONTEND_USER_DIST=",
            "LOCAL_USER_AUTO_AUTH_TOKEN=",
            "LOG_LEVEL=",
        ]:
            self.assertIn(key, content)
        self.assertNotIn("sk-", content)
        self.assertNotIn("replace_with", content)
        self.assertRegex(content, r"(?m)^LLM_API_KEY=$")
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

    def test_llm_settings_accepts_qwen_provider_template(self) -> None:
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
                        "provider": "qwen",
                        "model": "qwen-plus",
                        "api_url": (
                            "https://dashscope.aliyuncs.com/compatible-mode/v1/"
                            "chat/completions"
                        ),
                        "api_key": "secret-test-key",
                    },
                )
                status = self.client.get(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                )
                provider = env_value("LLM_PROVIDER")
                api_key = env_value("LLM_API_KEY")

        self.assertEqual(response.status_code, 200)
        payload = status.json()
        self.assertEqual(payload["provider"], "qwen")
        self.assertEqual(payload["model"], "qwen-plus")
        self.assertEqual(
            payload["api_url"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
        self.assertEqual(provider, "qwen")
        self.assertEqual(api_key, "secret-test-key")

    def test_llm_settings_requires_authorized_scopes(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "reader-token": {
                                "actor_id": "reader",
                                "permission_scopes": ["read_only"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                anonymous_get = self.client.get("/settings/llm")
                anonymous_post = self.client.post(
                    "/settings/llm",
                    json={"enabled": True, "provider": "deepseek"},
                )
                reader_get = self.client.get(
                    "/settings/llm",
                    headers={"X-Actor-Token": "reader-token"},
                )
                reader_post = self.client.post(
                    "/settings/llm",
                    headers={"X-Actor-Token": "reader-token"},
                    json={"enabled": True, "provider": "deepseek"},
                )

        self.assertEqual(anonymous_get.status_code, 403)
        self.assertEqual(anonymous_post.status_code, 403)
        self.assertEqual(reader_get.status_code, 200)
        self.assertEqual(reader_post.status_code, 403)

    def test_llm_settings_rejects_provider_without_echoing_value(self) -> None:
        invalid_provider = "secret-provider-value"
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
                                "permission_scopes": ["diagnostics"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                response = self.client.post(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                    json={"enabled": True, "provider": invalid_provider},
                )

        serialized = json.dumps(response.json(), ensure_ascii=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持的 LLM provider", serialized)
        self.assertNotIn(invalid_provider, serialized)

    def test_llm_settings_rejects_invalid_api_urls_without_echoing_value(self) -> None:
        invalid_urls = [
            "http://api.deepseek.com/chat/completions",
            "https://example.com/chat/completions",
            "https://api.deepseek.com/v1/chat/completions",
            "https://api.deepseek.com/chat/completions?x=1",
            "https://user:pass@api.deepseek.com/chat/completions",
            "https://api.deepseek.com:444/chat/completions",
        ]
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
                                "permission_scopes": ["diagnostics"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                responses = [
                    self.client.post(
                        "/settings/llm",
                        headers={"X-Actor-Token": "operator-token"},
                        json={"enabled": True, "provider": "deepseek", "api_url": url},
                    )
                    for url in invalid_urls
                ]

        for response, invalid_url in zip(responses, invalid_urls, strict=True):
            serialized = json.dumps(response.json(), ensure_ascii=False)
            self.assertEqual(response.status_code, 400)
            self.assertIn(
                response.json()["detail"]["message"],
                {
                    "不支持的 LLM api_url",
                    "LLM api_url 与 provider 不匹配",
                    "LLM api_url path 与 provider 模板不匹配",
                },
            )
            self.assertNotIn(invalid_url, serialized)

    def test_llm_settings_blank_api_key_preserves_existing_key(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            env = {
                "LOCAL_SETTINGS_PATH": str(settings_path),
                "AUTH_TOKENS_JSON": json.dumps(
                    {
                        "operator-token": {
                            "actor_id": "operator",
                            "permission_scopes": ["read_only", "diagnostics"],
                        }
                    }
                ),
            }
            with patch.dict(os.environ, env, clear=False):
                initial = self.client.post(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                    json={
                        "enabled": True,
                        "provider": "deepseek",
                        "api_key": "secret-test-key",
                    },
                )
                blank_key = self.client.post(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                    json={
                        "enabled": True,
                        "provider": "deepseek",
                        "api_key": "   ",
                    },
                )
                status = self.client.get(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                )

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(blank_key.status_code, 200)
        self.assertEqual(status.status_code, 200)
        payload = status.json()
        self.assertTrue(payload["api_key_configured"])
        self.assertNotIn("api_key", payload)
        self.assertNotIn("secret-test-key", json.dumps(payload))

    def test_llm_settings_corrupt_file_falls_back_safely(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            settings_path.write_text("{not-json", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "reader-token": {
                                "actor_id": "reader",
                                "permission_scopes": ["read_only"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                response = self.client.get(
                    "/settings/llm",
                    headers={"X-Actor-Token": "reader-token"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["api_key_configured"])
        self.assertFalse(payload["enabled"])

    def test_llm_settings_file_mode_is_restrictive_on_posix(self) -> None:
        if os.name != "posix":
            self.skipTest("file mode check applies to POSIX only")

        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings" / "llm.json"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "operator-token": {
                                "actor_id": "operator",
                                "permission_scopes": ["diagnostics"],
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
                        "api_key": "secret-test-key",
                    },
                )
                mode = stat.S_IMODE(settings_path.stat().st_mode)
                parent_mode = stat.S_IMODE(settings_path.parent.stat().st_mode)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mode, 0o600)
        self.assertEqual(parent_mode, 0o700)

    def test_llm_settings_existing_parent_mode_is_not_changed_on_posix(self) -> None:
        if os.name != "posix":
            self.skipTest("file mode check applies to POSIX only")

        with TemporaryDirectory() as directory:
            settings_dir = Path(directory) / "custom"
            settings_dir.mkdir()
            os.chmod(settings_dir, 0o755)
            settings_path = settings_dir / "llm.json"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "operator-token": {
                                "actor_id": "operator",
                                "permission_scopes": ["diagnostics"],
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
                        "api_key": "secret-test-key",
                    },
                )
                parent_mode = stat.S_IMODE(settings_dir.stat().st_mode)
                file_mode = stat.S_IMODE(settings_path.stat().st_mode)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(parent_mode, 0o755)
        self.assertEqual(file_mode, 0o600)

    def test_llm_settings_rejects_symlink_path_on_posix(self) -> None:
        if os.name != "posix":
            self.skipTest("symlink check applies to POSIX only")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "llm.json"
            target_path = root / "target.json"
            target_content = "target-unchanged-secret"
            target_path.write_text(target_content, encoding="utf-8")
            try:
                settings_path.symlink_to(target_path)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "operator-token": {
                                "actor_id": "operator",
                                "permission_scopes": ["diagnostics"],
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
                        "api_key": "secret-test-key",
                    },
                )
                target_after = target_path.read_text(encoding="utf-8")

        serialized = json.dumps(response.json(), ensure_ascii=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(target_after, target_content)
        self.assertIn("本机 LLM 设置路径不安全", serialized)
        self.assertNotIn(str(settings_path), serialized)
        self.assertNotIn(str(target_path), serialized)
        self.assertNotIn("secret-test-key", serialized)

    def test_llm_settings_unauthorized_malformed_post_checks_auth_first(self) -> None:
        secret_value = "secret-malformed-value"
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
                                "permission_scopes": ["diagnostics"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                response = self.client.post(
                    "/settings/llm",
                    content=f'{{"api_key":"{secret_value}"',
                    headers={"Content-Type": "application/json"},
                )

        serialized = json.dumps(response.json(), ensure_ascii=False)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(secret_value, serialized)

    def test_llm_settings_authorized_malformed_post_is_generic_400(self) -> None:
        secret_value = "secret-malformed-value"
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
                                "permission_scopes": ["diagnostics"],
                            }
                        }
                    ),
                },
                clear=False,
            ):
                response = self.client.post(
                    "/settings/llm",
                    content=f'{{"api_key":"{secret_value}"',
                    headers={
                        "Content-Type": "application/json",
                        "X-Actor-Token": "operator-token",
                    },
                )

        serialized = json.dumps(response.json(), ensure_ascii=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid_llm_settings", serialized)
        self.assertNotIn(secret_value, serialized)

    def test_env_value_reads_enabled_local_settings(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                    "DEEPSEEK_API_KEY": "",
                    "AUTH_TOKENS_JSON": json.dumps(
                        {
                            "operator-token": {
                                "actor_id": "operator",
                                "permission_scopes": ["diagnostics"],
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
                value = env_value("DEEPSEEK_API_KEY")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(value, "secret-test-key")

    def test_env_value_local_disabled_overrides_dotenv_enable_llm(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "llm.json"
            dotenv_path = root / ".env"
            settings_path.write_text(
                json.dumps({"enabled": False, "provider": "deepseek"}),
                encoding="utf-8",
            )
            dotenv_path.write_text("ENABLE_LLM=true\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"LOCAL_SETTINGS_PATH": str(settings_path)},
                clear=True,
            ), patch(
                "src.extractors.deepseek_extractor._dotenv_paths",
                return_value=[dotenv_path],
            ):
                value = env_value("ENABLE_LLM")

        self.assertEqual(value, "false")

    def test_env_value_shell_enable_llm_wins_over_local_disabled(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            settings_path.write_text(
                json.dumps({"enabled": False, "provider": "deepseek"}),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "ENABLE_LLM": "true",
                    "LOCAL_SETTINGS_PATH": str(settings_path),
                },
                clear=True,
            ):
                value = env_value("ENABLE_LLM")

        self.assertEqual(value, "true")


if __name__ == "__main__":
    unittest.main()
