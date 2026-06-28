from __future__ import annotations

import hashlib
import importlib.util
import zipfile
import unittest
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory


class InternalWindowsZipTest(unittest.TestCase):
    def test_build_internal_windows_zip_writes_launchers_readme_and_checksum(self) -> None:
        spec = importlib.util.find_spec("scripts.build_internal_windows_zip")
        self.assertIsNotNone(spec, "缺少 Windows zip 构建脚本。")

        from scripts.build_internal_windows_zip import (
            DEFAULT_APP_NAME,
            build_internal_windows_zip,
        )

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            artifacts = build_internal_windows_zip(
                output_dir=output_dir,
                app_name=DEFAULT_APP_NAME,
                version="9.9.9",
                build_frontend=False,
            )

            checksum_text = artifacts.checksum_path.read_text(encoding="utf-8")
            readme_text = artifacts.readme_path.read_text(encoding="utf-8")
            expected_digest = hashlib.sha256(artifacts.zip_path.read_bytes()).hexdigest()

            with zipfile.ZipFile(artifacts.zip_path) as archive:
                names = set(archive.namelist())
                launcher_text = archive.read(
                    "本地表格工作台-9.9.9-windows-internal/start_local_user_web.bat"
                ).decode("utf-8")
                app_launcher_text = archive.read(
                    "本地表格工作台-9.9.9-windows-internal/workbench_source/launch_app.py"
                ).decode("utf-8")
                serialized = b"\n".join(
                    archive.read(name)
                    for name in archive.namelist()
                    if not name.endswith("/")
                )

        self.assertTrue(artifacts.zip_path.name.endswith("-windows-internal.zip"))
        self.assertIn(expected_digest, checksum_text)
        self.assertIn(artifacts.zip_path.name, checksum_text)
        self.assertIn("Windows 内测包", readme_text)
        self.assertIn("Python 3.11+", readme_text)
        self.assertIn(expected_digest, readme_text)
        self.assertIn(
            "本地表格工作台-9.9.9-windows-internal/内测说明-Windows.md",
            names,
        )
        self.assertIn("LOCALAPPDATA", launcher_text)
        self.assertIn("where py", launcher_text)
        self.assertIn("-3.11", launcher_text)
        self.assertIn("Scripts\\python.exe", launcher_text)
        self.assertIn('"APP_DISTRIBUTION_MODE": "user_upload_only"', app_launcher_text)
        self.assertIn('"LOCAL_SETTINGS_PATH": str(settings_path)', app_launcher_text)
        forbidden_package_names = {".env", "uploaded_datasets", "local_settings", "tool_audit"}
        for name in names:
            self.assertFalse(
                set(PurePosixPath(name).parts) & forbidden_package_names,
                f"Windows zip 包含禁止发布路径：{name}",
            )
        self.assertNotIn(b"operator-token", serialized)
        self.assertNotIn(b"sk-", serialized)


if __name__ == "__main__":
    unittest.main()
