from __future__ import annotations

import json
import shlex
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.run_quality_gate import (
    CommandResult,
    QualityGateOptions,
    make_check,
    run_quality_gate,
)


class FakeRunner:
    def __init__(
        self,
        *,
        fail_command: str | None = None,
        regex_score: str = "320 / 320",
        dirty: bool = False,
        create_demo_report: bool = True,
        dirty_after_checks: bool = False,
    ) -> None:
        self.fail_command = fail_command
        self.regex_score = regex_score
        self.dirty = dirty
        self.create_demo_report = create_demo_report
        self.dirty_after_checks = dirty_after_checks
        self.demo_ran = False
        self.commands: list[str] = []

    def run(self, command: str, cwd: Path) -> CommandResult:
        self.commands.append(command)
        if "rev-parse" in command:
            return CommandResult(exit_code=0, stdout="abc123\n")
        if "status --porcelain" in command:
            if self.dirty_after_checks and self.demo_ran:
                return CommandResult(exit_code=0, stdout=" M generated.md\n")
            return CommandResult(exit_code=0, stdout=" M file.py\n" if self.dirty else "")
        if self.fail_command and self.fail_command in command:
            return CommandResult(exit_code=1, stderr=f"{self.fail_command} failed")
        if "unittest discover" in command:
            return CommandResult(exit_code=0, stderr="Ran 101 tests in 1.0s\n\nOK\n")
        if "tests.test_workbench_api_contract" in command:
            return CommandResult(exit_code=0, stderr="Ran 10 tests in 0.2s\n\nOK\n")
        if "eval_fuzzy_inputs.py" in command:
            return CommandResult(
                exit_code=0,
                stdout=(
                    "rule_regex_extractor_symbolic_verifier "
                    f"score {self.regex_score} tokens 0\n"
                ),
            )
        if "run_demo_acceptance.py" in command:
            self.demo_ran = True
            if self.create_demo_report:
                _write_demo_report(_demo_output_dir(command, cwd))
            return CommandResult(exit_code=0, stdout="Wrote demo report\n")
        return CommandResult(exit_code=0, stdout="ok\n")


class QualityGateTest(unittest.TestCase):
    def test_all_checks_pass_report_status_pass(self) -> None:
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(Path(directory))

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["regex_score"], "320/320")
        self.assertEqual(report["summary"]["demo_acceptance"]["passed"], 25)
        self.assertEqual(_check_by_name(report, "frontend_build")["status"], "pass")

    def test_required_check_failure_marks_report_fail(self) -> None:
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(
                Path(directory),
                runner=FakeRunner(fail_command="py_compile"),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("python_syntax", _failed_check_names(report))

    def test_non_fail_fast_continues_after_failure(self) -> None:
        runner = FakeRunner(fail_command="py_compile")
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(Path(directory), runner=runner)

        self.assertEqual(report["status"], "fail")
        self.assertIn("unit_tests", [check["name"] for check in report["checks"]])

    def test_fail_fast_stops_after_first_failure(self) -> None:
        runner = FakeRunner(fail_command="py_compile")
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(
                Path(directory),
                runner=runner,
                options=QualityGateOptions(
                    fail_fast=True,
                    output_dir=Path(directory) / "quality_gate",
                ),
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            ["git_state", "python_syntax"],
        )

    def test_frontend_missing_is_skipped(self) -> None:
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(Path(directory), create_frontend=False)

        frontend = _check_by_name(report, "frontend_build")
        self.assertEqual(frontend["status"], "skipped")

    def test_missing_demo_acceptance_report_fails_gate(self) -> None:
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(
                Path(directory),
                runner=FakeRunner(create_demo_report=False),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("demo_acceptance", _failed_check_names(report))

    def test_regex_score_must_match_expected_score(self) -> None:
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(
                Path(directory),
                runner=FakeRunner(regex_score="319 / 320"),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("regex_evaluator", _failed_check_names(report))

    def test_git_dirty_is_warning_unless_strict(self) -> None:
        with TemporaryDirectory() as directory:
            non_strict = _run_fake_gate(
                Path(directory),
                runner=FakeRunner(dirty=True),
            )
        with TemporaryDirectory() as directory:
            strict = _run_fake_gate(
                Path(directory),
                runner=FakeRunner(dirty=True),
                options=QualityGateOptions(
                    strict=True,
                    output_dir=Path(directory) / "quality_gate",
                ),
            )

        self.assertEqual(non_strict["status"], "pass")
        self.assertEqual(_check_by_name(non_strict, "git_state")["status"], "warning")
        self.assertEqual(strict["status"], "fail")
        self.assertEqual(_check_by_name(strict, "git_state")["status"], "fail")

    def test_report_json_and_markdown_are_generated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report = _run_fake_gate(root)
            json_path = root / "quality_gate/report.json"
            markdown_path = root / "quality_gate/report.md"
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(loaded["status"], report["status"])
        self.assertIn("Quality Gate 报告", markdown)

    def test_new_generated_worktree_changes_fail_gate(self) -> None:
        with TemporaryDirectory() as directory:
            report = _run_fake_gate(
                Path(directory),
                runner=FakeRunner(dirty_after_checks=True),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("generated_artifact_consistency", _failed_check_names(report))


def _run_fake_gate(
    root: Path,
    *,
    runner: FakeRunner | None = None,
    options: QualityGateOptions | None = None,
    create_frontend: bool = True,
) -> dict[str, object]:
    runner = runner or FakeRunner()
    options = options or QualityGateOptions(output_dir=root / "quality_gate")
    if create_frontend:
        frontend_dir = root / "frontend"
        frontend_dir.mkdir(parents=True, exist_ok=True)
        (frontend_dir / "package.json").write_text("{}", encoding="utf-8")
    with patch(
        "scripts.run_quality_gate.check_domain_pack_validate",
        side_effect=_domain_check,
    ):
        with patch(
            "scripts.run_quality_gate.check_domain_review_workflow",
            side_effect=_pass_internal("domain_review_workflow"),
        ):
            with patch(
                "scripts.run_quality_gate.check_warehouse_guard",
                side_effect=_pass_internal("warehouse_fingerprint_guard"),
            ):
                return run_quality_gate(options, runner=runner, root=root)


def _domain_check(context: object) -> dict[str, object]:
    context.summary["domains"] = {
        "admissions": {
            "domain_pack_status": "approved",
            "approved_can_execute": True,
        }
    }
    return make_check(
        name="domain_pack_validate",
        status="pass",
        command="internal",
        exit_code=0,
    )


def _pass_internal(name: str):
    def factory(context: object) -> dict[str, object]:
        return make_check(
            name=name,
            status="pass",
            command="internal",
            exit_code=0,
        )

    return factory


def _demo_output_dir(command: str, cwd: Path) -> Path:
    parts = shlex.split(command)
    if "--output-dir" in parts:
        index = parts.index("--output-dir")
        return Path(parts[index + 1])
    return cwd / "outputs/demo_acceptance"


def _write_demo_report(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "total": 25,
            "passed": 25,
            "failed": 0,
            "by_domain": {"admissions": 15, "housing": 5, "products": 5},
            "by_status": {"ok": 15, "needs_confirmation": 8, "no_results": 2},
        }
    }
    (report_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _failed_check_names(report: dict[str, object]) -> set[str]:
    return {
        check["name"]
        for check in report["checks"]
        if check["status"] == "fail"
    }


def _check_by_name(report: dict[str, object], name: str) -> dict[str, object]:
    for check in report["checks"]:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check: {name}")


if __name__ == "__main__":
    unittest.main()
