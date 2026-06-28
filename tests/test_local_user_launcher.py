from __future__ import annotations

import json
import socket
import stat
import subprocess
import unittest
from pathlib import Path

from scripts.run_local_user_web import (
    DEFAULT_DEV_OPERATOR_TOKEN,
    _choose_port,
    launcher_environment,
)


ROOT = Path(__file__).resolve().parents[1]


class LocalUserLauncherTest(unittest.TestCase):
    def test_launcher_sets_dev_cookie_only_without_custom_auth(self) -> None:
        env = launcher_environment({}, ROOT / "frontend-user/dist", host="127.0.0.1")
        auth_tokens = json.loads(env["AUTH_TOKENS_JSON"])

        self.assertIn(DEFAULT_DEV_OPERATOR_TOKEN, auth_tokens)
        self.assertEqual(
            env["LOCAL_USER_AUTO_AUTH_TOKEN"],
            DEFAULT_DEV_OPERATOR_TOKEN,
        )
        self.assertEqual(env["APP_DISTRIBUTION_MODE"], "user_upload_only")
        self.assertEqual(env["FRONTEND_USER_DIST"], str(ROOT / "frontend-user/dist"))

        custom = launcher_environment(
            {"AUTH_TOKENS_JSON": '{"real-token":{"permission_scopes":["read_only"]}}'},
            ROOT / "frontend-user/dist",
            host="0.0.0.0",
        )

        self.assertNotIn("LOCAL_USER_AUTO_AUTH_TOKEN", custom)
        self.assertEqual(
            custom["AUTH_TOKENS_JSON"],
            '{"real-token":{"permission_scopes":["read_only"]}}',
        )

    def test_launcher_rejects_dev_token_on_non_loopback_host(self) -> None:
        with self.assertRaises(SystemExit):
            launcher_environment({}, ROOT / "frontend-user/dist", host="0.0.0.0")

    def test_launcher_auto_port_skips_occupied_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            occupied_port = sock.getsockname()[1]

            selected = _choose_port("127.0.0.1", occupied_port, True)

        self.assertNotEqual(selected, occupied_port)
        self.assertGreater(selected, occupied_port)

    def test_dry_run_does_not_print_token_values(self) -> None:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "scripts/run_local_user_web.py",
                "--dry-run",
                "--skip-build",
                "--no-open",
                "--port",
                "8123",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://127.0.0.1:8123", result.stdout)
        self.assertNotIn(DEFAULT_DEV_OPERATOR_TOKEN, result.stdout)
        self.assertNotIn("AUTH_TOKENS_JSON", result.stdout)

    def test_macos_launcher_is_executable(self) -> None:
        launcher = ROOT / "start_local_user_web.command"
        content = launcher.read_text(encoding="utf-8")
        mode = stat.S_IMODE(launcher.stat().st_mode)

        self.assertIn("scripts/run_local_user_web.py", content)
        self.assertTrue(mode & stat.S_IXUSR)
