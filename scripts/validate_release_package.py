"""校验 release package 的静态完整性。"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "release_manifest.json"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs/release_package"
REQUIRED_MAKE_TARGETS = {
    "bootstrap",
    "serve",
    "demo",
    "pilot",
    "operator-trial",
    "agent-acceptance",
    "quality",
    "frontend",
    "clean-artifacts",
    "release-check",
}
REQUIRED_RELEASE_FILES = {
    "CHANGELOG.md",
    "RELEASE_CHECKLIST.md",
    "Dockerfile",
    "docker-compose.yml",
    "docs/demo_script.md",
    "docs/production_deployment.md",
    "docs/security_model.md",
    "docs/backup_restore.md",
    "release_manifest.json",
}
FORBIDDEN_SAMPLE_SUFFIXES = {".duckdb", ".db", ".sqlite", ".env"}
MAX_SAMPLE_BYTES = 250_000


@dataclass
class ReleaseCheck:
    """release package 单项检查结果。"""

    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)

    report = validate_release_package(
        manifest_path=Path(args.manifest),
        output_dir=Path(args.output_dir),
    )
    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Release package: {report['status']}")
        print(f"Wrote {report['artifacts']['json_report']}")
        print(f"Wrote {report['artifacts']['markdown_report']}")
    return 0 if report["status"] == "pass" else 1


def validate_release_package(
    *,
    manifest_path: Path = MANIFEST_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """读取 manifest 并校验发布包所需文件与样例。"""

    checks: list[ReleaseCheck] = []
    manifest = _load_manifest(manifest_path, checks)
    if manifest:
        checks.extend(_check_manifest_shape(manifest))
        checks.extend(_check_manifest_paths(manifest))
        checks.append(_check_make_targets())
        checks.append(_check_git_commit())
    else:
        checks.append(
            ReleaseCheck(
                "manifest_shape",
                "fail",
                "release_manifest.json 不能读取，跳过后续 manifest 检查。",
            )
        )
    status = "fail" if any(check.status == "fail" for check in checks) else "pass"
    report = {
        "status": status,
        "generated_at": _utc_now(),
        "manifest_path": str(manifest_path),
        "checks": [check.to_dict() for check in checks],
        "summary": {
            "passed": sum(1 for check in checks if check.status == "pass"),
            "failed": sum(1 for check in checks if check.status == "fail"),
            "warnings": sum(1 for check in checks if check.status == "warning"),
        },
        "artifacts": {
            "json_report": str(output_dir / "report.json"),
            "markdown_report": str(output_dir / "report.md"),
        },
    }
    _write_report(report, output_dir)
    return report


def _load_manifest(
    manifest_path: Path,
    checks: list[ReleaseCheck],
) -> dict[str, Any] | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        checks.append(
            ReleaseCheck("manifest_exists", "fail", "release_manifest.json 不存在。")
        )
        return None
    except json.JSONDecodeError as exc:
        checks.append(
            ReleaseCheck(
                "manifest_json",
                "fail",
                "release_manifest.json 不是合法 JSON。",
                {"line": exc.lineno, "column": exc.colno},
            )
        )
        return None
    checks.append(ReleaseCheck("manifest_exists", "pass", "manifest 可读取。"))
    return manifest


def _check_manifest_shape(manifest: dict[str, Any]) -> list[ReleaseCheck]:
    required_keys = {
        "release_manifest_version",
        "release_name",
        "release_status",
        "recommended_tag",
        "api_version",
        "workbench_schema_version",
        "tool_contract_version",
        "commands",
        "sample_data",
        "sample_outputs",
        "docs",
        "security_invariants",
    }
    missing = sorted(required_keys - set(manifest))
    checks = [
        ReleaseCheck(
            "manifest_shape",
            "fail" if missing else "pass",
            "manifest 顶层字段完整。" if not missing else "manifest 缺少必需字段。",
            {"missing": missing},
        )
    ]
    commands = {item.get("name") for item in manifest.get("commands", [])}
    missing_commands = sorted(REQUIRED_MAKE_TARGETS - commands)
    checks.append(
        ReleaseCheck(
            "manifest_commands",
            "fail" if missing_commands else "pass",
            "manifest 已列出关键 make target。"
            if not missing_commands
            else "manifest 缺少关键 make target。",
            {"missing": missing_commands},
        )
    )
    return checks


def _check_manifest_paths(manifest: dict[str, Any]) -> list[ReleaseCheck]:
    entries = []
    for key in ("sample_data", "sample_outputs", "docs"):
        for item in manifest.get(key, []):
            if isinstance(item, dict) and item.get("path"):
                entries.append((key, item["path"]))
    entries.extend(("release_file", path) for path in sorted(REQUIRED_RELEASE_FILES))

    checks = []
    missing = []
    forbidden = []
    oversized = []
    invalid_json = []
    for group, relative_path in entries:
        path = _safe_repo_path(relative_path)
        if path is None or not path.exists():
            missing.append(relative_path)
            continue
        if path.suffix in FORBIDDEN_SAMPLE_SUFFIXES:
            forbidden.append(relative_path)
        if group.startswith("sample") and path.stat().st_size > MAX_SAMPLE_BYTES:
            oversized.append(relative_path)
        if group == "sample_outputs" and path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                invalid_json.append(
                    {
                        "path": relative_path,
                        "line": exc.lineno,
                        "column": exc.colno,
                    }
                )
    checks.append(
        ReleaseCheck(
            "manifest_paths_exist",
            "fail" if missing else "pass",
            "manifest 引用路径均存在。" if not missing else "manifest 引用路径缺失。",
            {"missing": missing},
        )
    )
    checks.append(
        ReleaseCheck(
            "sample_artifact_safety",
            "fail" if forbidden or oversized or invalid_json else "pass",
            "sample artifacts 大小、后缀和 JSON 格式通过。"
            if not (forbidden or oversized or invalid_json)
            else "sample artifacts 存在风险。",
            {
                "forbidden": forbidden,
                "oversized": oversized,
                "invalid_json": invalid_json,
            },
        )
    )
    return checks


def _check_make_targets() -> ReleaseCheck:
    makefile = ROOT_DIR / "Makefile"
    text = makefile.read_text(encoding="utf-8")
    missing = [
        target
        for target in sorted(REQUIRED_MAKE_TARGETS)
        if f"{target}:" not in text
    ]
    return ReleaseCheck(
        "make_targets",
        "fail" if missing else "pass",
        "Makefile 关键 target 完整。" if not missing else "Makefile 缺少 target。",
        {"missing": missing},
    )


def _check_git_commit() -> ReleaseCheck:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ReleaseCheck(
            "git_commit",
            "warning",
            "无法读取当前 git commit；release checklist 仍可继续。",
        )
    return ReleaseCheck(
        "git_commit",
        "pass",
        "当前 git commit 可读取。",
        {"commit": completed.stdout.strip()},
    )


def _safe_repo_path(relative_path: str) -> Path | None:
    path = (ROOT_DIR / relative_path).resolve()
    try:
        path.relative_to(ROOT_DIR)
    except ValueError:
        return None
    return path


def _write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _render_markdown(report),
        encoding="utf-8",
    )


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Release Package 校验报告",
        "",
        f"- status：`{report['status']}`",
        f"- manifest_path：`{report['manifest_path']}`",
        f"- generated_at：`{report['generated_at']}`",
        "",
        "| check | status | message |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | `{check['status']}` | {check['message']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
