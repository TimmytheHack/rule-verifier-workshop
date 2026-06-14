"""运行 fake agent 黑盒 tool-use 验收。"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.api.openai_tool_adapter import OpenAIToolAdapter
from src.api.tool_registry import invoke_tool


DEFAULT_OUTPUT_DIR = Path("outputs/agent_tool_acceptance")
SAFE_OPENAI_TOOL_NAMES = {
    "dataset__profile",
    "dataset__review_summary",
    "workbench__query",
    "workbench__confirm",
    "evidence__get",
}


@dataclass
class AcceptanceCheck:
    name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "message": self.message,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    report = run_acceptance(Path(args.output_dir))
    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Agent tool acceptance: {report['status']}")
        print(f"Wrote {report['artifacts']['markdown']}")
        print(f"Wrote {report['artifacts']['json']}")
    return 0 if report["status"] == "pass" else 1


def run_acceptance(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """运行 list/profile/review/query/confirm/evidence/权限拒绝黑盒验收。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[AcceptanceCheck] = []
    with tempfile.TemporaryDirectory(prefix="agent_tool_acceptance_") as directory:
        root = Path(directory)
        dataset_id = prepare_queryable_dataset(root)
        actor = {
            "actor_id": "fake_agent",
            "permission_scopes": ["read_only", "query", "confirm"],
            "dataset_root": str(root / "managed"),
            "audit_path": str(root / "agent_audit.jsonl"),
        }
        adapter = OpenAIToolAdapter()

        checks.append(check_tool_list(adapter))
        profile = adapter.invoke(
            "dataset__profile",
            {"dataset_id": dataset_id},
            actor,
        )
        checks.append(
            make_assertion(
                "profile",
                bool(profile.get("fields")),
                {"field_count": len(profile.get("fields") or [])},
                "dataset.profile 应返回字段 profile。",
            )
        )
        review = adapter.invoke(
            "dataset__review_summary",
            {"dataset_id": dataset_id},
            actor,
        )
        checks.append(
            make_assertion(
                "review_summary",
                bool(review.get("reviewable_fields")),
                {
                    "reviewable_count": len(review.get("reviewable_fields") or []),
                    "domain_pack_status": review.get("domain_pack_status"),
                },
                "dataset.review_summary 应返回可审查字段。",
            )
        )
        query = adapter.invoke(
            "workbench__query",
            {
                "dataset_id": dataset_id,
                "natural_language": "Austin under 1900",
                "deterministic_fields": {
                    "city": ["Austin"],
                    "rent_usd": 1900,
                },
                "top_k": 5,
            },
            actor,
        )
        checks.append(
            make_assertion(
                "query",
                query.get("status") == "ok" and bool(query.get("items")),
                {
                    "status": query.get("status"),
                    "result_count": query.get("result_count"),
                    "sql": (
                        (query.get("debug_trace") or {})
                        .get("execution", {})
                        .get("sql", "")
                    ),
                },
                "workbench.query 应在 approved + warehouse_ready 后返回 items。",
            )
        )
        confirmed = adapter.invoke(
            "workbench__confirm",
            {
                "previous_response": query,
                "confirmed_candidate_ids": ["forged_candidate_id"],
            },
            actor,
        )
        checks.append(
            make_assertion(
                "confirm_rejects_forged_candidate",
                confirmed.get("status") == "blocked"
                and bool(confirmed.get("rejected_confirmations")),
                {
                    "status": confirmed.get("status"),
                    "rejected_confirmations": confirmed.get(
                        "rejected_confirmations",
                        [],
                    ),
                },
                "workbench.confirm 必须拒绝伪造 candidate_id。",
            )
        )
        evidence = adapter.invoke(
            "evidence__get",
            {"workbench_response": query},
            actor,
        )
        serialized_evidence = json.dumps(evidence, ensure_ascii=False)
        checks.append(
            make_assertion(
                "evidence",
                "evidence_pack" in evidence
                and "Traceback" not in serialized_evidence
                and "/Users/" not in serialized_evidence,
                {"keys": sorted(evidence.keys())},
                "evidence.get 应返回净化 EvidencePack。",
            )
        )
        denied = adapter.invoke(
            "dataset__approve_op",
            {
                "dataset_id": dataset_id,
                "field_id": "city",
                "op": "in",
            },
            actor,
        )
        checks.append(
            make_assertion(
                "admin_permission_denied",
                denied.get("status") == "error"
                and (denied.get("error") or {}).get("code") == "tool_not_allowed",
                denied,
                "LLM-safe adapter 默认不能调用 admin tools。",
            )
        )

    report = build_report(checks, output_dir)
    write_report(report, output_dir)
    return report


def check_tool_list(adapter: OpenAIToolAdapter) -> AcceptanceCheck:
    tools = adapter.export_tools()
    names = {tool["function"]["name"] for tool in tools}
    return make_assertion(
        "list_tools",
        names == SAFE_OPENAI_TOOL_NAMES,
        {"tool_names": sorted(names)},
        "默认 OpenAI adapter 只能列出 LLM-safe tools。",
    )


def prepare_queryable_dataset(root: Path) -> str:
    """用 operator 权限准备 fake agent 可查询的临时数据集。"""

    source = root / "housing.csv"
    source.write_text(
        "\n".join(
            [
                "listing_id,city,rent_usd,bedrooms",
                "1,Austin,1800,2",
                "2,Dallas,1600,1",
                "3,Austin,2100,3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_id = "ds_agent_acceptance"
    write_actor = _actor(root, ["dataset_write"])
    review_actor = _actor(root, ["review_admin"])
    warehouse_actor = _actor(root, ["warehouse_admin"])
    invoke_tool(
        "dataset.upload",
        {
            "filename": source.name,
            "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
            "dataset_id": dataset_id,
        },
        write_actor,
    )
    invoke_tool(
        "dataset.generate_domain_pack",
        {"dataset_id": dataset_id, "domain_name": "agent_housing"},
        write_actor,
    )
    for field_id in ["listing_id", "city", "rent_usd"]:
        invoke_tool(
            "dataset.approve_field",
            {"dataset_id": dataset_id, "field_id": field_id},
            review_actor,
        )
    invoke_tool(
        "dataset.approve_op",
        {"dataset_id": dataset_id, "field_id": "city", "op": "in"},
        review_actor,
    )
    invoke_tool(
        "dataset.approve_op",
        {"dataset_id": dataset_id, "field_id": "rent_usd", "op": "<="},
        review_actor,
    )
    approved = invoke_tool(
        "dataset.approve_domain",
        {
            "dataset_id": dataset_id,
            "title_field": "listing_id",
            "primary_fields": ["city", "rent_usd"],
            "sort_field": "rent_usd",
        },
        review_actor,
    )
    if not approved.get("ok"):
        raise RuntimeError(json.dumps(approved, ensure_ascii=False, indent=2))
    built = invoke_tool(
        "dataset.build_warehouse",
        {"dataset_id": dataset_id},
        warehouse_actor,
    )
    if built.get("status") != "queryable":
        raise RuntimeError(json.dumps(built, ensure_ascii=False, indent=2))
    return dataset_id


def _actor(root: Path, permission_scopes: list[str]) -> dict[str, Any]:
    return {
        "actor_id": "acceptance_operator",
        "permission_scopes": permission_scopes,
        "dataset_root": str(root / "managed"),
        "audit_path": str(root / "operator_audit.jsonl"),
        "_trusted_internal": True,
    }


def make_assertion(
    name: str,
    condition: bool,
    details: dict[str, Any],
    message: str,
) -> AcceptanceCheck:
    return AcceptanceCheck(
        name=name,
        status="pass" if condition else "fail",
        details=details,
        message="" if condition else message,
    )


def build_report(
    checks: list[AcceptanceCheck],
    output_dir: Path,
) -> dict[str, Any]:
    failed = [check for check in checks if check.status != "pass"]
    return {
        "status": "fail" if failed else "pass",
        "generated_at": _utc_now(),
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
        },
        "checks": [check.to_dict() for check in checks],
        "artifacts": {
            "json": str(output_dir / "report.json"),
            "markdown": str(output_dir / "report.md"),
        },
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Tool Acceptance 报告",
        "",
        f"- 总体状态：`{report['status']}`",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 通过：`{report['summary']['passed']}` / `{report['summary']['total']}`",
        "",
        "| check | status | message |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | {check['status']} | {check.get('message') or ''} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
