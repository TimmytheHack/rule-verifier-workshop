"""运行项目交付前统一 Quality Gate。"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.generate_domain_pack import generate_domain_pack, load_source_dataset
from scripts.review_domain_pack import (
    summarize_domain_pack,
    validate_domain_pack,
    write_review_report,
)
from src.adapters.data_warehouse import (
    audit_data_warehouse_fingerprints,
    build_structured_store,
    build_structured_store_from_dataset,
)
from src.api.workbench import WorkbenchConfig, run_workbench
from src.domains import DomainConfig


DEFAULT_DOMAINS = ["admissions", "housing", "products"]
OUTPUT_DIR = Path("outputs/quality_gate")
REPORT_JSON = "report.json"
REPORT_MD = "report.md"
REGEX_AUDIT_PATH = Path("outputs/eval/fuzzy_eval_results.audit_tmp.json")
REGEX_EXPECTED_SCORE = "320/320"
TAIL_LIMIT = 4000


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


class CommandRunner(Protocol):
    def run(self, command: str, cwd: Path) -> CommandResult:
        """Run one shell command."""


class SubprocessRunner:
    def run(self, command: str, cwd: Path) -> CommandResult:
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=round(time.monotonic() - started, 3),
        )


@dataclass
class QualityGateOptions:
    fail_fast: bool = False
    skip_frontend: bool = False
    skip_demo: bool = False
    domains: list[str] = field(default_factory=lambda: list(DEFAULT_DOMAINS))
    output_dir: Path = OUTPUT_DIR
    json_only: bool = False
    strict: bool = False


@dataclass
class GateContext:
    root: Path
    options: QualityGateOptions
    runner: CommandRunner
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    warehouse_paths: dict[str, tuple[Path, Path]] = field(default_factory=dict)


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    report = run_quality_gate(options)
    if options.json_only:
        print(json.dumps(_json_ready(report), ensure_ascii=False, indent=2))
    else:
        print(f"Quality Gate: {report['status']}")
        print(f"Wrote {options.output_dir / REPORT_MD}")
        print(f"Wrote {options.output_dir / REPORT_JSON}")
    return 0 if report["status"] == "pass" else 1


def parse_args(argv: list[str] | None = None) -> QualityGateOptions:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-demo", action="store_true")
    parser.add_argument("--domain", action="append", dest="domains")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    return QualityGateOptions(
        fail_fast=args.fail_fast,
        skip_frontend=args.skip_frontend,
        skip_demo=args.skip_demo,
        domains=args.domains or list(DEFAULT_DOMAINS),
        output_dir=Path(args.output_dir),
        json_only=args.json_only,
        strict=args.strict,
    )


def run_quality_gate(
    options: QualityGateOptions | None = None,
    *,
    runner: CommandRunner | None = None,
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    options = options or QualityGateOptions()
    runner = runner or SubprocessRunner()
    output_dir = root / options.output_dir if not options.output_dir.is_absolute() else options.output_dir
    options = QualityGateOptions(
        fail_fast=options.fail_fast,
        skip_frontend=options.skip_frontend,
        skip_demo=options.skip_demo,
        domains=list(options.domains),
        output_dir=output_dir,
        json_only=options.json_only,
        strict=options.strict,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    started = _utc_now()
    started_monotonic = time.monotonic()
    context = GateContext(root=root, options=options, runner=runner)

    git_commit, git_dirty = git_info(runner, root)
    context.summary.update(
        {
            "regex_score": "",
            "unit_tests": "",
            "api_contract_tests": "",
            "demo_acceptance": {
                "total": 0,
                "passed": 0,
                "status_distribution": {},
                "by_domain": {},
            },
            "domains": {},
        }
    )

    stopped = False

    def add_step(factory: Any) -> None:
        nonlocal stopped
        if stopped:
            return
        check = factory()
        _add_check(context, check)
        if options.fail_fast and check["status"] == "fail":
            stopped = True

    add_step(lambda: check_git_state(context, git_dirty))
    add_step(
        lambda: run_command_check(
            context,
            name="python_syntax",
            command=(
                "find src scripts tests -name '*.py' -print0 | "
                "xargs -0 .venv/bin/python -m py_compile"
            ),
        )
    )
    add_step(
        lambda: run_command_check(
            context,
            name="unit_tests",
            command=".venv/bin/python -m unittest discover -s tests",
            after=lambda check: _summarize_unit_tests(context, check),
        )
    )
    add_step(
        lambda: run_command_check(
            context,
            name="api_contract_tests",
            command=".venv/bin/python -m unittest tests.test_workbench_api_contract",
            after=lambda check: _summarize_api_contract_tests(context, check),
        )
    )
    add_step(
        lambda: run_command_check(
            context,
            name="regex_evaluator",
            command=(
                ".venv/bin/python scripts/eval_fuzzy_inputs.py --methods regex "
                f"--quiet --output-path {REGEX_AUDIT_PATH}"
            ),
            after=lambda check: _summarize_regex_score(context, check),
        )
    )
    if options.skip_demo:
        add_step(lambda: skipped_check("demo_acceptance", "用户传入 --skip-demo。"))
    else:
        add_step(lambda: check_demo_acceptance(context))
    add_step(lambda: check_domain_pack_validate(context))
    add_step(lambda: check_domain_review_workflow(context))
    add_step(lambda: check_warehouse_guard(context))
    add_step(
        lambda: run_command_check(
            context,
            name="git_diff_check",
            command="git diff --check",
        )
    )
    if options.skip_frontend:
        add_step(lambda: skipped_check("frontend_build", "用户传入 --skip-frontend。"))
    else:
        add_step(lambda: check_frontend_build(context))

    finished = _utc_now()
    summary = finalize_summary(context)
    report = {
        "status": "fail" if summary["failed"] else "pass",
        "started_at": started,
        "finished_at": finished,
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "checks": context.checks,
        "summary": summary,
        "artifacts": [],
    }
    json_path = options.output_dir / REPORT_JSON
    md_path = options.output_dir / REPORT_MD
    report["artifacts"] = [str(md_path), str(json_path), *context.artifacts]
    json_path.write_text(
        json.dumps(_json_ready(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def run_command_check(
    context: GateContext,
    *,
    name: str,
    command: str,
    after: Any | None = None,
) -> dict[str, Any]:
    result = context.runner.run(command, context.root)
    status = "pass" if result.exit_code == 0 else "fail"
    check = make_check(
        name=name,
        status=status,
        command=command,
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if after:
        after(check)
    return check


def check_git_state(context: GateContext, git_dirty: bool) -> dict[str, Any]:
    if not git_dirty:
        return make_check(
            name="git_state",
            status="pass",
            command="git status --porcelain",
            exit_code=0,
        )
    status = "fail" if context.options.strict else "warning"
    message = "工作区存在未提交变更。"
    if context.options.strict:
        message = "strict 模式下工作区 dirty 会阻断 gate。"
    return make_check(
        name="git_state",
        status=status,
        command="git status --porcelain",
        exit_code=1 if context.options.strict else 0,
        stdout=message,
    )


def check_demo_acceptance(context: GateContext) -> dict[str, Any]:
    command = ".venv/bin/python scripts/run_demo_acceptance.py"
    result = context.runner.run(command, context.root)
    check = make_check(
        name="demo_acceptance",
        status="pass" if result.exit_code == 0 else "fail",
        command=command,
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
        stdout=result.stdout,
        stderr=result.stderr,
        artifacts=[
            "outputs/demo_acceptance/report.md",
            "outputs/demo_acceptance/report.json",
        ],
    )
    report_path = context.root / "outputs/demo_acceptance/report.json"
    if not report_path.exists():
        check["status"] = "fail"
        check["stderr_tail"] = _append_tail(
            check["stderr_tail"],
            "缺少 outputs/demo_acceptance/report.json。",
        )
        return check
    payload = _load_json(report_path)
    summary = payload.get("summary") or {}
    context.summary["demo_acceptance"] = {
        "total": int(summary.get("total") or 0),
        "passed": int(summary.get("passed") or 0),
        "status_distribution": dict(summary.get("by_status") or {}),
        "by_domain": dict(summary.get("by_domain") or {}),
    }
    failures = []
    if int(summary.get("failed") or 0) != 0:
        failures.append("demo acceptance 存在失败记录。")
    expected_domains = {domain: 0 for domain in context.options.domains}
    by_domain = summary.get("by_domain") or {}
    for domain in ["admissions", "housing", "products"]:
        if domain in expected_domains and int(by_domain.get(domain) or 0) == 0:
            failures.append(f"demo acceptance 缺少 {domain} 记录。")
    if failures:
        check["status"] = "fail"
        check["stderr_tail"] = _append_tail(check["stderr_tail"], "\n".join(failures))
    return check


def check_domain_pack_validate(context: GateContext) -> dict[str, Any]:
    started = time.monotonic()
    stdout_lines = []
    failures = []
    domains_summary: dict[str, Any] = {}
    try:
        warehouse_paths = ensure_gate_warehouses(context)
        for domain_id in context.options.domains:
            domain = DomainConfig.load(domain_id)
            domain_record = {
                "domain_pack_status": domain.pack_status,
                "domain_config_valid": True,
                "review_validate_ok": False,
                "approved_can_execute": False,
                "top_result_mapping_count": len(domain.top_result_mapping),
            }
            validation = validate_domain_pack(domain.root)
            domain_record["review_validate_ok"] = bool(validation.get("ok"))
            if not validation.get("ok"):
                failed_checks = [
                    item
                    for item in validation.get("checks", [])
                    if not item.get("ok")
                ]
                failures.append(
                    f"{domain_id} review validate failed: "
                    + "; ".join(item.get("message", "") for item in failed_checks[:5])
                )
            if domain.pack_status != "approved":
                failures.append(f"{domain_id} 不是 approved：{domain.pack_status}")
            if not domain.top_result_mapping:
                failures.append(f"{domain_id} 缺少 top_result_mapping。")
            if not domain.execution.get("output_fields"):
                failures.append(f"{domain_id} 缺少 execution.output_fields。")
            smoke = _run_domain_smoke(domain_id, warehouse_paths)
            domain_record["approved_can_execute"] = smoke.get("ok", False)
            domain_record["smoke_status"] = smoke.get("status")
            if not smoke.get("ok"):
                failures.append(f"{domain_id} smoke query 未执行：{smoke.get('reason')}")
            domains_summary[domain_id] = domain_record
            stdout_lines.append(json.dumps(domain_record, ensure_ascii=False))

        draft_checks = _draft_pack_block_checks(context)
        stdout_lines.extend(draft_checks["messages"])
        if not draft_checks["ok"]:
            failures.extend(draft_checks["failures"])
    except Exception as exc:  # noqa: BLE001 - gate 需要汇总失败，不抛出。
        failures.append(f"domain pack validate exception: {type(exc).__name__}: {exc}")

    context.summary["domains"].update(domains_summary)
    return make_check(
        name="domain_pack_validate",
        status="fail" if failures else "pass",
        command="internal: DomainConfig + approved/draft execution guard",
        exit_code=1 if failures else 0,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout="\n".join(stdout_lines),
        stderr="\n".join(failures),
    )


def check_domain_review_workflow(context: GateContext) -> dict[str, Any]:
    started = time.monotonic()
    failures = []
    artifacts: list[str] = []
    stdout_lines = []
    try:
        tmp_root = context.options.output_dir / "tmp/domain_review_smoke"
        tmp_root.mkdir(parents=True, exist_ok=True)
        generated = generate_domain_pack(
            source_path=context.root / "domains/housing/fixtures/housing.csv",
            domain_name="quality_gate_review_smoke",
            output_root=tmp_root,
        )
        summary = summarize_domain_pack(generated.domain_dir)
        validation = validate_domain_pack(generated.domain_dir)
        report = write_review_report(
            generated.domain_dir,
            output_dir=tmp_root / "reports",
            write=True,
        )
        stdout_lines.append(
            json.dumps(
                {
                    "summary_domain": summary.get("domain"),
                    "validation_ok": validation.get("ok"),
                    "report_written": report.written,
                },
                ensure_ascii=False,
            )
        )
        artifacts.extend(
            [
                str(report.payload["json_path"]),
                str(report.payload["markdown_path"]),
            ]
        )
        if not validation.get("ok"):
            failures.append("review_domain_pack validate failed in smoke.")
        if not report.written:
            failures.append("review_domain_pack report 未写入。")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"domain review workflow exception: {type(exc).__name__}: {exc}")
    context.artifacts.extend(artifacts)
    return make_check(
        name="domain_review_workflow",
        status="fail" if failures else "pass",
        command="internal: review_domain_pack summarize/validate/report",
        exit_code=1 if failures else 0,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout="\n".join(stdout_lines),
        stderr="\n".join(failures),
        artifacts=artifacts,
    )


def check_warehouse_guard(context: GateContext) -> dict[str, Any]:
    started = time.monotonic()
    failures = []
    stdout_lines = []
    try:
        warehouse_paths = ensure_gate_warehouses(context)
        for domain_id, (database_path, index_path) in warehouse_paths.items():
            domain = DomainConfig.load(domain_id)
            audit = audit_data_warehouse_fingerprints(
                workbook_path=domain.workbook_path,
                database_path=database_path,
                index_path=index_path,
                table_name=domain.table_name,
            )
            record = {
                "domain": domain_id,
                "ok": audit.get("ok"),
                "source_fingerprint": (audit.get("source") or {}).get("fingerprint"),
                "duckdb_fingerprint": (audit.get("duckdb") or {}).get("fingerprint"),
                "value_index_fingerprint": (
                    audit.get("schema_value_index") or {}
                ).get("fingerprint"),
                "warnings": audit.get("warnings", []),
            }
            stdout_lines.append(json.dumps(record, ensure_ascii=False))
            if not audit.get("ok"):
                failures.append(f"{domain_id} warehouse fingerprint guard failed.")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"warehouse guard exception: {type(exc).__name__}: {exc}")
    return make_check(
        name="warehouse_fingerprint_guard",
        status="fail" if failures else "pass",
        command="internal: build/audit domain warehouses",
        exit_code=1 if failures else 0,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout="\n".join(stdout_lines),
        stderr="\n".join(failures),
        artifacts=[str(context.options.output_dir / "warehouses")],
    )


def check_frontend_build(context: GateContext) -> dict[str, Any]:
    frontend_dir = context.root / "frontend"
    package_json = frontend_dir / "package.json"
    if not frontend_dir.exists() or not package_json.exists():
        return skipped_check("frontend_build", "frontend/package.json 不存在。")
    build_command = _frontend_build_command(frontend_dir)
    result = context.runner.run(build_command, frontend_dir)
    combined = f"{result.stdout}\n{result.stderr}"
    has_warning = "warning" in combined.lower() or "(!)" in combined
    status = "pass"
    if result.exit_code != 0:
        status = "fail"
    elif has_warning:
        status = "warning"
    return make_check(
        name="frontend_build",
        status=status,
        command=f"cd frontend && {build_command}",
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
        stdout=result.stdout,
        stderr=result.stderr,
        artifacts=["frontend/dist"],
    )


def _frontend_build_command(frontend_dir: Path) -> str:
    if sys.platform != "darwin":
        return "npm run build"
    rollup_dir = frontend_dir / "node_modules/@rollup"
    arm64_pkg = rollup_dir / "rollup-darwin-arm64"
    x64_pkg = rollup_dir / "rollup-darwin-x64"
    if arm64_pkg.exists() and not x64_pkg.exists():
        return "arch -arm64 npm run build"
    if x64_pkg.exists() and not arm64_pkg.exists():
        return "arch -x86_64 npm run build"
    return "npm run build"


def ensure_gate_warehouses(context: GateContext) -> dict[str, tuple[Path, Path]]:
    if context.warehouse_paths:
        return context.warehouse_paths
    warehouse_dir = context.options.output_dir / "warehouses"
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    for domain_id in context.options.domains:
        domain = DomainConfig.load(domain_id)
        database_path = warehouse_dir / f"{domain_id}.duckdb"
        index_path = warehouse_dir / f"{domain_id}_schema_value_index.json"
        if domain_id == "admissions":
            build_structured_store(
                workbook_path=domain.workbook_path,
                required_columns=domain.required_columns,
                schema_path=domain.schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name=domain.table_name,
            )
        else:
            dataset = load_source_dataset(domain.workbook_path)
            build_structured_store_from_dataset(
                dataset=dataset,
                schema_path=domain.schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name=domain.table_name,
                source_path=domain.workbook_path,
            )
        context.warehouse_paths[domain_id] = (database_path, index_path)
    return context.warehouse_paths


def _run_domain_smoke(
    domain_id: str,
    warehouse_paths: dict[str, tuple[Path, Path]],
) -> dict[str, Any]:
    config = _smoke_config(domain_id)
    if config is None:
        return {"ok": False, "reason": "缺少 smoke config"}

    def database_for_domain(domain_config: DomainConfig) -> Path:
        return warehouse_paths[domain_config.domain_id][0]

    def index_for_domain(domain_config: DomainConfig) -> Path:
        return warehouse_paths[domain_config.domain_id][1]

    with patch("src.api.workbench._warehouse_database_path", database_for_domain):
        with patch("src.api.workbench._warehouse_value_index_path", index_for_domain):
            response = run_workbench(config)
    execution = (response.get("evidence_pack") or {}).get("execution_summary") or {}
    sql = execution.get("sql") or (response.get("debug_trace") or {}).get(
        "execution",
        {},
    ).get("sql")
    ok = response.get("status") in {"ok", "needs_confirmation", "no_results"} and bool(sql)
    return {
        "ok": ok,
        "status": response.get("status"),
        "reason": "" if ok else response.get("answer"),
    }


def _smoke_config(domain_id: str) -> WorkbenchConfig | None:
    if domain_id == "admissions":
        prompt = "广东物理，排位32000，想学计算机，广深优先。"
        return WorkbenchConfig(
            domain_name="admissions",
            user_input=prompt,
            soft_preferences={"prompt": prompt},
            extractor="regex",
        )
    if domain_id == "housing":
        return WorkbenchConfig(
            domain_name="housing",
            user_input="Austin under 1900",
            hard_filters={"city": ["Austin"], "rent_cap": 1900},
            soft_preferences={"prompt": "Austin under 1900"},
            extractor="regex",
        )
    if domain_id == "products":
        return WorkbenchConfig(
            domain_name="products",
            user_input="Audio products under 100",
            hard_filters={"categories": ["audio"], "price_cap": 100},
            soft_preferences={"prompt": "Audio products under 100"},
            extractor="regex",
        )
    return None


def _draft_pack_block_checks(context: GateContext) -> dict[str, Any]:
    messages = []
    failures = []
    tmp_root = context.options.output_dir / "tmp/domain_pack_block"
    tmp_root.mkdir(parents=True, exist_ok=True)
    generated = generate_domain_pack(
        source_path=context.root / "domains/housing/fixtures/housing.csv",
        domain_name="quality_gate_draft_block",
        output_root=tmp_root,
    )
    for status in ["draft", "needs_review"]:
        domain_json_path = generated.domain_dir / "domain.json"
        domain_json = _load_json(domain_json_path)
        domain_json["status"] = status
        domain_json_path.write_text(
            json.dumps(domain_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        response = run_workbench(
            WorkbenchConfig(
                domain_name="quality_gate_draft_block",
                domain_path=str(generated.domain_dir),
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_cap": 1900},
                soft_preferences={"prompt": "Austin under 1900"},
                extractor="regex",
            )
        )
        execution = (response.get("debug_trace") or {}).get("execution") or {}
        ok = response.get("status") == "blocked" and not execution.get("sql")
        messages.append(f"{status}: {'blocked' if ok else 'not blocked'}")
        if not ok:
            failures.append(f"{status} domain pack 未被阻断。")
    return {"ok": not failures, "messages": messages, "failures": failures}


def _summarize_unit_tests(context: GateContext, check: dict[str, Any]) -> None:
    count = _parse_unittest_count(_combined_output(check))
    context.summary["unit_tests"] = f"{count} tests" if count is not None else ""
    if check["status"] == "pass" and count is None:
        check["status"] = "warning"
        check["stderr_tail"] = _append_tail(check["stderr_tail"], "未解析到 unittest 数量。")


def _summarize_api_contract_tests(context: GateContext, check: dict[str, Any]) -> None:
    count = _parse_unittest_count(_combined_output(check))
    context.summary["api_contract_tests"] = (
        f"{count} tests" if count is not None else ""
    )
    if check["status"] == "pass" and count is None:
        check["status"] = "warning"
        check["stderr_tail"] = _append_tail(
            check["stderr_tail"],
            "未解析到 API contract test 数量。",
        )


def _summarize_regex_score(context: GateContext, check: dict[str, Any]) -> None:
    score = _parse_regex_score(_combined_output(check))
    context.summary["regex_score"] = score or ""
    if score != REGEX_EXPECTED_SCORE:
        check["status"] = "fail"
        check["stderr_tail"] = _append_tail(
            check["stderr_tail"],
            f"regex score expected {REGEX_EXPECTED_SCORE}, got {score or 'unknown'}。",
        )


def finalize_summary(context: GateContext) -> dict[str, Any]:
    passed = sum(1 for check in context.checks if check["status"] == "pass")
    failed = sum(1 for check in context.checks if check["status"] == "fail")
    warnings = sum(1 for check in context.checks if check["status"] == "warning")
    return {
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "regex_score": context.summary.get("regex_score") or "",
        "unit_tests": context.summary.get("unit_tests") or "",
        "api_contract_tests": context.summary.get("api_contract_tests") or "",
        "demo_acceptance": context.summary.get("demo_acceptance")
        or {
            "total": 0,
            "passed": 0,
            "status_distribution": {},
        },
        "domains": context.summary.get("domains") or {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    failed_checks = [check for check in report["checks"] if check["status"] == "fail"]
    lines = [
        "# Quality Gate 报告",
        "",
        f"- 总体状态：`{report['status']}`",
        f"- 当前 git commit：`{report['git_commit']}`",
        f"- 工作区 dirty：`{report['git_dirty']}`",
        f"- 开始时间：`{report['started_at']}`",
        f"- 结束时间：`{report['finished_at']}`",
        f"- 耗时秒数：`{report['duration_seconds']}`",
        f"- regex score：`{summary.get('regex_score')}`",
        f"- unittest：`{summary.get('unit_tests')}`",
        f"- API contract：`{summary.get('api_contract_tests')}`",
        f"- demo acceptance：`{summary.get('demo_acceptance', {}).get('passed')}` / `{summary.get('demo_acceptance', {}).get('total')}`",
        "",
        "## 检查列表",
        "",
        "| check | status | exit_code | duration_seconds |",
        "|---|---|---:|---:|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | {check['status']} | {check['exit_code']} | {check['duration_seconds']} |"
        )
    lines.extend(["", "## 失败原因摘要", ""])
    if not failed_checks:
        lines.append("- 无失败项。")
    for check in failed_checks:
        reason = check.get("stderr_tail") or check.get("stdout_tail") or "无输出。"
        lines.append(f"- `{check['name']}`: {reason[:500]}")
    lines.extend(["", "## Domain Pack 状态", ""])
    domains = summary.get("domains") or {}
    if not domains:
        lines.append("- 未记录 domain summary。")
    for domain, payload in domains.items():
        lines.append(
            f"- `{domain}`: status=`{payload.get('domain_pack_status')}`, "
            f"review_validate=`{payload.get('review_validate_ok')}`, "
            f"can_execute=`{payload.get('approved_can_execute')}`"
        )
    lines.extend(["", "## 生成 artifacts", ""])
    for artifact in report.get("artifacts") or []:
        lines.append(f"- `{artifact}`")
    return "\n".join(lines).rstrip() + "\n"


def make_check(
    *,
    name: str,
    status: str,
    command: str,
    exit_code: int | None = None,
    duration_seconds: float = 0.0,
    stdout: str = "",
    stderr: str = "",
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": round(duration_seconds, 3),
        "stdout_tail": _tail(stdout),
        "stderr_tail": _tail(stderr),
        "artifacts": artifacts or [],
    }


def skipped_check(name: str, reason: str) -> dict[str, Any]:
    return make_check(
        name=name,
        status="skipped",
        command="",
        exit_code=None,
        stdout=reason,
    )


def git_info(runner: CommandRunner, root: Path) -> tuple[str, bool]:
    commit = runner.run("git rev-parse --short HEAD", root)
    status = runner.run("git status --porcelain", root)
    return (commit.stdout.strip() or "unknown", bool(status.stdout.strip()))


def _add_check(context: GateContext, check: dict[str, Any]) -> None:
    context.checks.append(check)


def _parse_unittest_count(text: str) -> int | None:
    match = re.search(r"Ran\s+(\d+)\s+tests?", text)
    return int(match.group(1)) if match else None


def _parse_regex_score(text: str) -> str | None:
    match = re.search(
        r"rule_regex_extractor_symbolic_verifier\s+score\s+(\d+)\s*/\s*(\d+)",
        text,
    )
    if not match:
        match = re.search(r"score\s+(\d+)\s*/\s*(\d+)", text)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _combined_output(check: dict[str, Any]) -> str:
    return f"{check.get('stdout_tail') or ''}\n{check.get('stderr_tail') or ''}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tail(text: str) -> str:
    if len(text) <= TAIL_LIMIT:
        return text
    return text[-TAIL_LIMIT:]


def _append_tail(existing: str, message: str) -> str:
    return _tail("\n".join(item for item in [existing, message] if item))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _json_ready(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
