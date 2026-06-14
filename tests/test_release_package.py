from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.validate_release_package import validate_release_package


ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTest(unittest.TestCase):
    def test_release_package_validator_passes(self) -> None:
        with TemporaryDirectory() as directory:
            report = validate_release_package(output_dir=Path(directory))

        self.assertEqual(report["status"], "pass")
        failed = [check for check in report["checks"] if check["status"] == "fail"]
        self.assertFalse(failed, failed)

    def test_manifest_references_existing_sample_artifacts(self) -> None:
        manifest = json.loads(
            (ROOT / "release_manifest.json").read_text(encoding="utf-8")
        )
        for group in ("sample_data", "sample_outputs", "docs"):
            with self.subTest(group=group):
                for item in manifest[group]:
                    path = ROOT / item["path"]
                    self.assertTrue(path.exists(), item["path"])
                    if group.startswith("sample"):
                        self.assertLess(path.stat().st_size, 250_000, item["path"])
                    if group == "sample_outputs" and path.suffix == ".json":
                        json.loads(path.read_text(encoding="utf-8"))

    def test_release_manifest_lists_safe_tool_server_contract_versions(self) -> None:
        manifest = json.loads(
            (ROOT / "release_manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["api_version"], "api.v1")
        self.assertEqual(
            manifest["workbench_schema_version"],
            "workbench_response.v1",
        )
        self.assertEqual(manifest["tool_contract_version"], "tools.v1")
        commands = {item["name"] for item in manifest["commands"]}
        self.assertIn("quality", commands)
        self.assertIn("release-check", commands)


if __name__ == "__main__":
    unittest.main()
