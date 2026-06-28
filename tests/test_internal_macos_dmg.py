from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.build_internal_macos_dmg import (
    DEFAULT_APP_NAME,
    build_internal_dmg,
    _validate_staging,
)


class InternalMacosDmgTest(unittest.TestCase):
    def test_build_internal_dmg_writes_readme_and_checksum(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            app_path = output_dir / f"{DEFAULT_APP_NAME}.app"
            contents = app_path / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_text("plist", encoding="utf-8")

            def fake_create_dmg(
                _staging_dir: Path,
                dmg_path: Path,
                *,
                app_name: str,
                version: str,
            ) -> None:
                self.assertEqual(app_name, DEFAULT_APP_NAME)
                self.assertEqual(version, "9.9.9")
                dmg_path.write_bytes(b"fake dmg bytes")

            with patch(
                "scripts.build_internal_macos_dmg._create_dmg",
                side_effect=fake_create_dmg,
            ):
                artifacts = build_internal_dmg(
                    output_dir=output_dir,
                    app_name=DEFAULT_APP_NAME,
                    version="9.9.9",
                    build_app_bundle=False,
                )

            expected_digest = hashlib.sha256(b"fake dmg bytes").hexdigest()
            readme_text = artifacts.readme_path.read_text(encoding="utf-8")
            checksum_text = artifacts.checksum_path.read_text(encoding="utf-8")
            staging_path = output_dir / ".本地表格工作台-9.9.9-macos-internal-staging"
            self.assertFalse(staging_path.exists())

        self.assertTrue(artifacts.dmg_path.name.endswith("-macos-internal.dmg"))
        self.assertIn(expected_digest, checksum_text)
        self.assertIn(artifacts.dmg_path.name, checksum_text)
        self.assertIn("未签名、未 notarize", readme_text)
        self.assertIn("Python 3.11+", readme_text)
        self.assertIn(expected_digest, readme_text)

    def test_staging_validation_rejects_local_user_data(self) -> None:
        with TemporaryDirectory() as directory:
            staging = Path(directory)
            forbidden = staging / "本地表格工作台.app" / "uploaded_datasets"
            forbidden.mkdir(parents=True)

            with self.assertRaises(SystemExit):
                _validate_staging(staging)


if __name__ == "__main__":
    unittest.main()
