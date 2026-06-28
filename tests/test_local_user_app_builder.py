from __future__ import annotations

import plistlib
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_local_user_app import (
    APP_VERSION,
    APP_SUPPORT_DIR_NAME,
    DEFAULT_APP_NAME,
    EXCLUDED_TOOL_SCHEMA_FILES,
    RUNTIME_SCRIPT_FILES,
    build_app,
)


ROOT = Path(__file__).resolve().parents[1]


class LocalUserAppBuilderTest(unittest.TestCase):
    def test_builds_macos_app_bundle_without_secrets(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            app_path = build_app(
                repo_root=ROOT,
                output_dir=output_dir,
                app_name=DEFAULT_APP_NAME,
                build_frontend=False,
                include_runtime=True,
                install_app_runtime=False,
            )

            plist_path = app_path / "Contents" / "Info.plist"
            pkg_info_path = app_path / "Contents" / "PkgInfo"
            launcher_path = app_path / "Contents" / "MacOS" / "launch"
            bootstrap_path = app_path / "Contents" / "Resources" / "bootstrap_python.txt"
            app_launcher_path = (
                app_path
                / "Contents"
                / "Resources"
                / "workbench_source"
                / "launch_app.py"
            )
            payload = plistlib.loads(plist_path.read_bytes())
            pkg_info = pkg_info_path.read_text(encoding="ascii")
            launcher_text = launcher_path.read_text(encoding="utf-8")
            bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
            app_launcher_text = app_launcher_path.read_text(encoding="utf-8")
            launcher_mode = stat.S_IMODE(launcher_path.stat().st_mode)
            serialized = b"\n".join(
                path.read_bytes()
                for path in app_path.rglob("*")
                if path.is_file() and path.name != "Info.plist"
            )

        self.assertEqual(payload["CFBundleExecutable"], "launch")
        self.assertEqual(payload["CFBundleName"], DEFAULT_APP_NAME)
        self.assertEqual(payload["CFBundleShortVersionString"], APP_VERSION)
        self.assertEqual(pkg_info, "APPL????")
        self.assertIn('SOURCE_ROOT="$RESOURCE_DIR/workbench_source"', launcher_text)
        self.assertIn('APP_ROOT="$APP_SUPPORT_DIR/runtime/workbench"', launcher_text)
        self.assertIn(f"Application Support/{APP_SUPPORT_DIR_NAME}", launcher_text)
        self.assertIn("find_bootstrap_python()", launcher_text)
        self.assertLess(
            launcher_text.index("find_bootstrap_python()"),
            launcher_text.index('BOOTSTRAP_PYTHON="$(find_bootstrap_python'),
        )
        self.assertIn('PYTHON_BIN="$APP_ROOT/.venv/bin/python"', launcher_text)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", launcher_text)
        self.assertIn("/opt/homebrew/bin/python3", bootstrap_text)
        self.assertIn("/usr/local/bin/python3", bootstrap_text)
        self.assertIn("/usr/bin/python3", bootstrap_text)
        self.assertIn("python3", bootstrap_text)
        self.assertIn('"APP_DISTRIBUTION_MODE": "user_upload_only"', app_launcher_text)
        self.assertIn('"PYTHONDONTWRITEBYTECODE": "1"', app_launcher_text)
        self.assertIn("secrets.token_urlsafe", app_launcher_text)
        self.assertIn('"DATA_ROOT": str(data_root)', app_launcher_text)
        self.assertIn('"LOCAL_SETTINGS_PATH": str(settings_path)', app_launcher_text)
        self.assertNotIn(b"repo_path.txt", serialized)
        self.assertNotIn(b"scripts/run_local_user_web.py", serialized)
        self.assertTrue(launcher_mode & stat.S_IXUSR)
        self.assertNotIn(b"operator-token", serialized)
        self.assertNotIn(b"sk-", serialized)

    def test_runtime_copy_uses_minimal_runtime_files(self) -> None:
        with TemporaryDirectory() as directory:
            app_path = build_app(
                repo_root=ROOT,
                output_dir=Path(directory),
                app_name=DEFAULT_APP_NAME,
                build_frontend=False,
                include_runtime=True,
                install_app_runtime=False,
            )

            workbench = app_path / "Contents" / "Resources" / "workbench_source"
            scripts = workbench / "scripts"
            tool_schemas = workbench / "schemas" / "tools"

            self.assertTrue((workbench / "src" / "api" / "server.py").exists())
            self.assertFalse((workbench / "domains").exists())
            self.assertFalse((workbench / "schemas" / "excel_schema_profile.json").exists())
            self.assertTrue(tool_schemas.exists())
            self.assertTrue((workbench / "frontend-user" / "dist").exists())
            self.assertFalse((workbench / ".venv").exists())
            self.assertTrue((workbench / "runtime_version.txt").exists())
            self.assertEqual(
                sorted(path.name for path in scripts.iterdir()),
                sorted(RUNTIME_SCRIPT_FILES),
            )
            self.assertFalse((scripts / "run_local_user_web.py").exists())
            self.assertFalse((scripts / "run_quality_gate.py").exists())
            self.assertFalse((scripts / "run_real_dataset_pilot.py").exists())
            schema_names = {path.name for path in tool_schemas.glob("*.json")}
            self.assertTrue(schema_names)
            self.assertFalse(schema_names & EXCLUDED_TOOL_SCHEMA_FILES)
            runtime_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in workbench.rglob("*")
                if path.is_file()
                and ".venv" not in path.parts
                and path.suffix in {".py", ".json", ".yaml", ".yml", ".html", ".js"}
            )
            self.assertNotIn("operator-token", runtime_text)
            self.assertNotIn("广东省2025年志愿填报大数据", runtime_text)

    def test_rejects_unsafe_output_and_runtime_paths(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)

            with self.assertRaises(SystemExit):
                build_app(
                    repo_root=ROOT,
                    output_dir=output_dir,
                    app_name="../bad",
                    build_frontend=False,
                    include_runtime=False,
                    install_app_runtime=False,
                )

            with self.assertRaises(SystemExit):
                build_app(
                    repo_root=ROOT,
                    output_dir=output_dir,
                    app_name=DEFAULT_APP_NAME,
                    build_frontend=False,
                    include_runtime=True,
                    install_app_runtime=True,
                    app_runtime_dir=Path(directory) / "unsafe-runtime",
                )
