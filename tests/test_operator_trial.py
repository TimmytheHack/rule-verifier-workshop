from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_operator_trial import run_operator_trial
from tests.test_real_dataset_pilot import _write_real_like_workbook


ROOT = Path(__file__).resolve().parents[1]


class OperatorTrialTest(unittest.TestCase):
    def test_operator_trial_report_contains_full_flow(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = _write_real_like_workbook(root)
            report = run_operator_trial(
                source_path=source,
                output_root=root / "operator_trial",
                run_id="20260614_fixture",
            )
            report_dir = root / "operator_trial/20260614_fixture"
            loaded = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
            markdown = (report_dir / "report.md").read_text(encoding="utf-8")
            serialized = json.dumps(loaded, ensure_ascii=False)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(loaded["status"], "pass")
        self.assertEqual(loaded["run_id"], "20260614_fixture")
        self.assertIn("# Operator Trial 报告", markdown)
        self.assertEqual(loaded["sheet_name"], "招生数据")
        self.assertEqual(loaded["detected_header_row"], 3)
        self.assertEqual(len(loaded["target_query_results"]), 2)
        self.assertTrue(loaded["approved_fields"])
        self.assertIn("upload", _operation_stages(loaded))
        self.assertIn("profile", _operation_stages(loaded))
        self.assertIn("review_summary", _operation_stages(loaded))
        self.assertIn("approve_domain", _operation_stages(loaded))
        self.assertIn("build_warehouse", _operation_stages(loaded))
        self.assertIn("target_query_1", _operation_stages(loaded))
        self.assertIn("target_query_2", _operation_stages(loaded))
        self.assertEqual(
            {
                "sheet_header",
                "schema_profile",
                "review_approval",
                "warehouse",
                "target_queries",
                "trial_closeout",
            },
            _checkpoint_stages(loaded),
        )
        self.assertTrue(loaded["failure_playbook"])
        self.assertIn("人工检查卡点", markdown)
        self.assertIn("常见失败处理", markdown)
        self.assertNotIn(str(root), serialized)
        self.assertNotIn(str(root), markdown)
        self.assertFalse(Path(str(loaded["warehouse_path"])).is_absolute())
        self.assertFalse(loaded["failures"])

    def test_operator_trial_records_review_blockers(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "missing_fields.csv"
            source.write_text(
                "年份,院校名称,专业名称,专业组最低分1\n"
                "2025,深圳大学,人工智能,634\n",
                encoding="utf-8",
            )
            report = run_operator_trial(
                source_path=source,
                output_root=root / "operator_trial",
                run_id="missing_fields",
            )

        self.assertEqual(report["status"], "fail")
        self.assertTrue(report["review_blockers"])
        self.assertTrue(report["missing_fields"])
        self.assertIn("review_blockers", _operation_stages(report))
        review_checkpoint = _checkpoint_by_stage(report, "review_approval")
        self.assertEqual(review_checkpoint["status"], "fail")

    def test_operator_trial_cli_fixture_writes_date_dir(self) -> None:
        with TemporaryDirectory() as directory:
            output_root = Path(directory) / "operator_trial"
            completed = subprocess.run(
                [
                    ".venv/bin/python",
                    "scripts/run_operator_trial.py",
                    "--fixture",
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "cli_fixture",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            report_path = output_root / "cli_fixture/report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(report["status"], "pass")
        self.assertIn("Operator trial: pass", completed.stdout)


def _operation_stages(report: dict[str, object]) -> set[str]:
    return {
        str(card["stage"])
        for card in report.get("operation_cards", [])
    }


def _checkpoint_stages(report: dict[str, object]) -> set[str]:
    return {
        str(card["stage"])
        for card in report.get("manual_checkpoints", [])
    }


def _checkpoint_by_stage(
    report: dict[str, object],
    stage: str,
) -> dict[str, object]:
    for card in report.get("manual_checkpoints", []):
        if card.get("stage") == stage:
            return card
    raise AssertionError(f"missing checkpoint: {stage}")


if __name__ == "__main__":
    unittest.main()
