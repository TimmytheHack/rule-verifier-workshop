from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_agent_tool_acceptance import run_acceptance


ROOT = Path(__file__).resolve().parents[1]


class AgentToolAcceptanceTest(unittest.TestCase):
    def test_run_acceptance_report_passes(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "agent_acceptance"
            report = run_acceptance(output_dir)
            loaded = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "report.md").read_text(encoding="utf-8")

        self.assertEqual(report["status"], "pass")
        self.assertEqual(loaded["status"], "pass")
        self.assertIn("Agent Tool Acceptance", markdown)
        check_names = {check["name"] for check in report["checks"]}
        self.assertEqual(
            check_names,
            {
                "list_tools",
                "profile",
                "review_summary",
                "query",
                "confirm_rejects_forged_candidate",
                "evidence",
                "admin_permission_denied",
            },
        )

    def test_cli_writes_report(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "agent_acceptance_cli"
            completed = subprocess.run(
                [
                    ".venv/bin/python",
                    "scripts/run_agent_tool_acceptance.py",
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(report["status"], "pass")
        self.assertIn("Agent tool acceptance: pass", completed.stdout)


if __name__ == "__main__":
    unittest.main()
