"""运行真实招生 Excel operator trial。"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_real_dataset_pilot import (
    TARGET_QUERIES,
    _fixture_path,
    _manual_approval_fixture,
    _safe_auto_suggest_approvals,
    _sanitize_report_paths,
    _target_query_record,
)
from src.api.dataset_service import DatasetService, DatasetServiceError


DEFAULT_OUTPUT_ROOT = Path("outputs/operator_trial")


@dataclass
class TrialContext:
    """operator trial 运行上下文。"""

    source_path: Path
    output_dir: Path
    dataset_id: str
    service: DatasetService
    sheet_name: str | None = None
    operation_cards: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)


def main(argv: list[str] | None = None) -> int:
    args = _arg_parser().parse_args(argv)
    if not args.fixture and not args.source_path:
        raise SystemExit("source_path is required unless --fixture is used.")
    source_path = _fixture_path() if args.fixture else Path(args.source_path)
    report = run_operator_trial(
        source_path=source_path,
        sheet_name=args.sheet_name,
        output_root=Path(args.output_root),
        run_id=args.run_id,
    )
    if args.json_only:
        print(json.dumps(_json_ready(report), ensure_ascii=False, indent=2))
    else:
        print(f"Operator trial: {report['status']}")
        print(f"Wrote {report['artifacts']['markdown_report']}")
        print(f"Wrote {report['artifacts']['json_report']}")
    return 0 if report["status"] == "pass" else 1


def run_operator_trial(
    *,
    source_path: Path,
    sheet_name: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_id: str | None = None,
) -> dict[str, Any]:
    """执行 upload/profile/review/approve/build/query operator trial。"""

    output_dir = _trial_output_dir(output_root, run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = _dataset_id(source_path)
    upload_root = output_dir / "uploaded_datasets"
    shutil.rmtree(upload_root / dataset_id, ignore_errors=True)
    context = TrialContext(
        source_path=source_path,
        output_dir=output_dir,
        dataset_id=dataset_id,
        service=DatasetService(upload_root),
        sheet_name=sheet_name,
    )

    upload = _step(
        context,
        "upload",
        lambda: context.service.upload(
            filename=source_path.name,
            content=source_path.read_bytes(),
            dataset_id=dataset_id,
            sheet_name=sheet_name,
        ),
    )
    generated = _step(
        context,
        "generate_draft_domain_pack",
        lambda: context.service.generate_domain_pack(
            dataset_id,
            domain_name="admissions",
            base_domain="admissions",
        ),
        required=bool(upload),
    )
    profile = _step(
        context,
        "profile",
        lambda: context.service.profile(dataset_id),
        required=bool(generated),
    )
    review = _step(
        context,
        "review_summary",
        lambda: context.service.review_summary(dataset_id),
        required=bool(generated),
    )
    review_blockers = _review_blockers(review)
    if review_blockers:
        context.failures.append(
            {
                "stage": "review_blockers",
                "message": "review_summary 存在阻断项，不能标记 trial pass。",
                "missing_fields": review.get("missing_fields") or [],
                "risky_fields": review.get("risky_fields") or [],
                "blockers": review_blockers,
            }
        )
        context.operation_cards.append(
            _manual_card(
                "review_blockers",
                "warning",
                {
                    "missing_fields": review.get("missing_fields") or [],
                    "risky_fields": review.get("risky_fields") or [],
                    "blockers": review_blockers,
                },
            )
        )
    suggestions = _safe_auto_suggest_approvals(review or {})
    context.operation_cards.append(
        _manual_card(
            "safe_auto_suggest_approvals",
            "pass",
            {
                "suggestions": suggestions,
                "note": "仅作为 operator 审查建议，不自动提升 seed ops。",
            },
        )
    )
    approved = _step(
        context,
        "approve_domain",
        lambda: context.service.approve_domain(dataset_id),
        required=bool(review),
    )
    if approved and not approved.get("ok"):
        context.failures.append(
            {
                "stage": "approve_domain",
                "message": approved.get("message") or "approve_domain failed",
                "payload": approved.get("payload"),
            }
        )
    warehouse = _step(
        context,
        "build_warehouse",
        lambda: context.service.build_warehouse(dataset_id),
        required=bool(approved and approved.get("ok")),
    )
    target_results = []
    if warehouse and warehouse.get("status") == "queryable":
        for index, query in enumerate(TARGET_QUERIES, start=1):
            response = _step(
                context,
                f"target_query_{index}",
                lambda query=query: context.service.query(
                    dataset_id,
                    user_input=query,
                    soft_preferences={"prompt": query},
                    extractor="regex",
                    planner_mode="legacy",
                ),
            )
            if response:
                record = _target_query_record(query, response)
                target_results.append(record)
                for failure in record.get("failures") or []:
                    context.failures.append(
                        {
                            "stage": "target_query",
                            "query": query,
                            "message": failure,
                        }
                    )
    else:
        context.failures.append(
            {
                "stage": "target_query",
                "message": "warehouse 未 queryable，跳过目标查询。",
            }
        )

    report = build_report(
        context=context,
        upload=upload or {},
        generated=generated or {},
        profile=profile or {},
        review=review or {},
        approved=approved or {},
        warehouse=warehouse or {},
        target_results=target_results,
        suggestions=suggestions,
        review_blockers=review_blockers,
    )
    write_report(report, output_dir)
    return report


def build_report(
    *,
    context: TrialContext,
    upload: dict[str, Any],
    generated: dict[str, Any],
    profile: dict[str, Any],
    review: dict[str, Any],
    approved: dict[str, Any],
    warehouse: dict[str, Any],
    target_results: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    review_blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    """把 trial 过程整理为 operator 可审计报告。"""

    warnings = _dedupe_warnings(context.warnings)
    review_payload = (approved.get("payload") or {}).get("review") or {}
    approved_fields = sorted((review_payload.get("reviewed_fields") or {}).keys())
    blocked_fields = sorted((review_payload.get("blocked_fields") or {}).keys())
    warehouse_audit = warehouse.get("warehouse_audit") or {}
    duckdb = warehouse_audit.get("duckdb") or {}
    artifacts = {
        **context.artifacts,
        "json_report": str(context.output_dir / "report.json"),
        "markdown_report": str(context.output_dir / "report.md"),
        "domain_dir": generated.get("domain_dir") or upload.get("domain_dir"),
        "schema_profile_path": generated.get("schema_profile_path"),
        "schema_value_index_path": generated.get("schema_value_index_path"),
        "ingestion_summary_path": generated.get("ingestion_summary_path"),
    }
    report = {
        "status": "fail" if context.failures else "pass",
        "generated_at": _utc_now(),
        "run_id": context.output_dir.name,
        "source_path": str(context.source_path),
        "dataset_id": upload.get("dataset_id") or context.dataset_id,
        "source_fingerprint": upload.get("source_fingerprint"),
        "sheet_name": upload.get("sheet_name"),
        "sheet_summaries": upload.get("sheet_summaries", []),
        "row_count": upload.get("row_count"),
        "column_count": upload.get("column_count"),
        "detected_header_row": upload.get("detected_header_row"),
        "header_detection_status": upload.get("header_detection_status"),
        "schema_profile_summary": _schema_profile_summary(profile),
        "review_summary": _operator_review_summary(review),
        "review_blockers": review_blockers,
        "risky_fields": review.get("risky_fields", []),
        "missing_fields": review.get("missing_fields", []),
        "safe_auto_suggest_approvals": suggestions,
        "manual_approval_fixture": _manual_approval_fixture(),
        "approved_fields": approved_fields,
        "blocked_fields": blocked_fields,
        "warehouse_path": (warehouse.get("warehouse") or {}).get("database_path"),
        "warehouse_fingerprint": duckdb.get("fingerprint"),
        "target_query_results": target_results,
        "manual_checkpoints": _manual_checkpoints(
            context=context,
            upload=upload,
            profile=profile,
            review=review,
            approved=approved,
            warehouse=warehouse,
            target_results=target_results,
            review_blockers=review_blockers,
        ),
        "failure_playbook": _failure_playbook(),
        "operation_cards": context.operation_cards,
        "warnings": warnings,
        "failures": context.failures,
        "artifacts": artifacts,
    }
    return _sanitize_report_paths(report, base_dir=context.output_dir)


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    (output_dir / "report.json").write_text(
        json.dumps(_json_ready(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Operator Trial 报告",
        "",
        f"- status：`{report['status']}`",
        f"- run_id：`{report['run_id']}`",
        f"- source_path：`{report['source_path']}`",
        f"- dataset_id：`{report['dataset_id']}`",
        f"- source_fingerprint：`{report.get('source_fingerprint')}`",
        f"- sheet_name：`{report.get('sheet_name')}`",
        f"- row_count / column_count：`{report.get('row_count')}` / `{report.get('column_count')}`",
        f"- detected_header_row：`{report.get('detected_header_row')}`",
        f"- warehouse_path：`{report.get('warehouse_path')}`",
        "",
        "## 操作卡点",
        _json_block(report["operation_cards"]),
        "## Schema Profile 摘要",
        _json_block(report["schema_profile_summary"]),
        "## Review 摘要",
        _json_block(report["review_summary"]),
        "## 缺失字段与风险字段",
        _json_block(
            {
                "missing_fields": report["missing_fields"],
                "risky_fields": report["risky_fields"],
                "review_blockers": report["review_blockers"],
            }
        ),
        "## 已批准与已阻断字段",
        _json_block(
            {
                "approved_fields": report["approved_fields"],
                "blocked_fields": report["blocked_fields"],
                "safe_auto_suggest_approvals": report[
                    "safe_auto_suggest_approvals"
                ],
            }
        ),
        "## 目标查询结果",
        _json_block(report["target_query_results"]),
        "## 人工检查卡点",
        _json_block(report["manual_checkpoints"]),
        "## 常见失败处理",
        _json_block(report["failure_playbook"]),
        "## 警告",
        _json_block(report["warnings"]),
        "## 失败项",
        _json_block(report["failures"]),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _step(
    context: TrialContext,
    stage: str,
    fn: Callable[[], dict[str, Any]],
    *,
    required: bool = True,
) -> dict[str, Any] | None:
    if not required:
        card = _manual_card(stage, "skipped", {"reason": "前置步骤未通过。"})
        context.operation_cards.append(card)
        return None
    started = time.monotonic()
    try:
        result = fn()
    except (DatasetServiceError, FileNotFoundError, ValueError) as exc:
        context.failures.append(
            {
                "stage": stage,
                "message": str(exc),
                "error_type": type(exc).__name__,
            }
        )
        context.operation_cards.append(
            _manual_card(
                stage,
                "fail",
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "duration_seconds": round(time.monotonic() - started, 3),
                },
            )
        )
        return None
    stage_warnings = _extract_warnings(result)
    context.warnings.extend(stage_warnings)
    context.operation_cards.append(
        _manual_card(
            stage,
            "warning" if stage_warnings else "pass",
            {
                "status": result.get("status") or result.get("domain_pack_status"),
                "warning_count": len(stage_warnings),
                "summary": _stage_summary(stage, result),
                "duration_seconds": round(time.monotonic() - started, 3),
            },
        )
    )
    return result


def _manual_card(
    stage: str,
    status: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "details": details,
    }


def _extract_warnings(result: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    warnings.extend(result.get("warnings") or [])
    warnings.extend((result.get("warehouse_audit") or {}).get("warnings") or [])
    return warnings


def _stage_summary(stage: str, result: dict[str, Any]) -> dict[str, Any]:
    if stage == "upload":
        return {
            "dataset_id": result.get("dataset_id"),
            "sheet_name": result.get("sheet_name"),
            "row_count": result.get("row_count"),
            "column_count": result.get("column_count"),
            "detected_header_row": result.get("detected_header_row"),
        }
    if stage == "profile":
        return {
            "field_count": len(result.get("fields") or []),
            "row_count": result.get("row_count"),
            "column_count": result.get("column_count"),
        }
    if stage == "review_summary":
        return {
            "reviewable_fields": len(result.get("reviewable_fields") or []),
            "missing_fields": len(result.get("missing_fields") or []),
            "risky_fields": len(result.get("risky_fields") or []),
        }
    if stage.startswith("target_query"):
        return {
            "status": result.get("status"),
            "query_type": result.get("query_type"),
            "result_count": result.get("result_count"),
        }
    if stage == "build_warehouse":
        return {
            "status": result.get("status"),
            "warehouse_path": (result.get("warehouse") or {}).get("database_path"),
        }
    return {
        "keys": sorted(result.keys())[:12],
    }


def _review_blockers(review: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not review:
        return []
    blockers = []
    for field in review.get("missing_fields") or []:
        blockers.append(
            {
                "type": "missing_required_field",
                "field_id": field.get("field_id"),
                "message": field.get("message") or "required field missing",
            }
        )
    for field in review.get("risky_fields") or []:
        blockers.append(
            {
                "type": "risky_field",
                "field_id": field.get("field_id"),
                "risk_flags": field.get("risk_flags") or [],
                "message": "字段需要 operator 人工审查。",
            }
        )
    return blockers


def _operator_review_summary(review: dict[str, Any]) -> dict[str, Any]:
    fields = review.get("reviewable_fields") or []
    return {
        "status": review.get("status"),
        "domain_pack_status": review.get("domain_pack_status"),
        "reviewable_field_count": len(fields),
        "required_field_count": len(review.get("required_fields") or []),
        "missing_field_count": len(review.get("missing_fields") or []),
        "risky_field_count": len(review.get("risky_fields") or []),
        "approved_field_count": sum(1 for field in fields if field.get("reviewed")),
    }


def _manual_checkpoints(
    *,
    context: TrialContext,
    upload: dict[str, Any],
    profile: dict[str, Any],
    review: dict[str, Any],
    approved: dict[str, Any],
    warehouse: dict[str, Any],
    target_results: list[dict[str, Any]],
    review_blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成 operator 可直接勾审的人工卡点摘要。"""

    warehouse_audit = warehouse.get("warehouse_audit") or {}
    target_failures = [
        failure
        for result in target_results
        for failure in (result.get("failures") or [])
    ]
    return [
        {
            "stage": "sheet_header",
            "status": _checkpoint_status(
                has_failure=not upload,
                has_warning=bool(
                    upload.get("warnings")
                    or upload.get("header_detection_status") != "ok"
                ),
            ),
            "evidence": {
                "sheet_name": upload.get("sheet_name"),
                "sheet_summaries": upload.get("sheet_summaries", []),
                "detected_header_row": upload.get("detected_header_row"),
                "header_detection_status": upload.get("header_detection_status"),
            },
            "operator_action": "人工确认 selected sheet 与 detected_header_row 是否和原表一致。",
        },
        {
            "stage": "schema_profile",
            "status": _checkpoint_status(
                has_failure=not profile,
                has_warning=bool(profile.get("warnings")),
            ),
            "evidence": _schema_profile_summary(profile),
            "operator_action": "核对 dtype、空值率、唯一值数量、样例值和数值范围。",
        },
        {
            "stage": "review_approval",
            "status": _checkpoint_status(
                has_failure=bool(review_blockers),
                has_warning=bool(review.get("risky_fields")),
            ),
            "evidence": {
                "missing_fields": review.get("missing_fields", []),
                "risky_fields": review.get("risky_fields", []),
                "review_blockers": review_blockers,
                "approved_ok": bool(approved.get("ok")),
            },
            "operator_action": "缺失字段必须补映射或阻断；risky fields 必须人工 approve/block。",
        },
        {
            "stage": "warehouse",
            "status": _checkpoint_status(
                has_failure=warehouse.get("status") != "queryable",
                has_warning=bool(warehouse_audit.get("warnings")),
            ),
            "evidence": {
                "status": warehouse.get("status"),
                "warehouse_path": (warehouse.get("warehouse") or {}).get(
                    "database_path"
                ),
                "warehouse_fingerprint": (
                    warehouse_audit.get("duckdb") or {}
                ).get("fingerprint"),
                "warnings": warehouse_audit.get("warnings", []),
            },
            "operator_action": "fingerprint 不一致或状态不是 queryable 时，禁止进入生产查询。",
        },
        {
            "stage": "target_queries",
            "status": _checkpoint_status(
                has_failure=bool(target_failures) or len(target_results) != 2,
                has_warning=any(
                    result.get("status") != "ok"
                    for result in target_results
                ),
            ),
            "evidence": [
                {
                    "query_type": result.get("query_type"),
                    "status": result.get("status"),
                    "result_count": result.get("result_count"),
                    "failure_count": len(result.get("failures") or []),
                }
                for result in target_results
            ],
            "operator_action": "逐条核对 EvidencePack、SQL/params、warnings 和结果是否符合人工预期。",
        },
        {
            "stage": "trial_closeout",
            "status": _checkpoint_status(has_failure=bool(context.failures)),
            "evidence": {
                "warning_count": len(context.warnings),
                "failure_count": len(context.failures),
            },
            "operator_action": "把可接受 warning、必须修复 warning、owner 和下一步结论写入反馈模板。",
        },
    ]


def _checkpoint_status(*, has_failure: bool, has_warning: bool = False) -> str:
    if has_failure:
        return "fail"
    if has_warning:
        return "needs_review"
    return "pass"


def _failure_playbook() -> list[dict[str, str]]:
    """返回 operator trial 常见失败处理建议。"""

    return [
        {
            "symptom": "header_detection_status 不是 ok 或 detected_header_row 不符合人工观察。",
            "likely_cause": "Excel 前几行包含标题、说明、合并单元格或空行。",
            "operator_action": "用 --sheet-name 选定 sheet；必要时清理表头说明行后重新上传。",
        },
        {
            "symptom": "missing_fields 非空。",
            "likely_cause": "源列名和 admissions canonical field 无法稳定映射。",
            "operator_action": "补充字段映射或确认该数据源不支持目标 query；不能强行 approve domain。",
        },
        {
            "symptom": "risky_fields 非空。",
            "likely_cause": "字段存在 PII、高基数、自由文本或特殊计划语义风险。",
            "operator_action": "逐字段 approve/block；未审查字段不能成为 executable hard filter。",
        },
        {
            "symptom": "warehouse status 不是 queryable 或 fingerprint guard 不通过。",
            "likely_cause": "源文件被替换、warehouse 过期或构建中断。",
            "operator_action": "重新 build warehouse；若仍不一致，重新上传并重跑 review。",
        },
        {
            "symptom": "recommendation 缺少 score_without_rank warning。",
            "likely_cause": "只有分数无位次时仍试图给出风险判断。",
            "operator_action": "阻断发布，修复 admissions recommendation guard 后重跑 trial。",
        },
        {
            "symptom": "答案声称录取概率或执行了 no_schema_field 偏好。",
            "likely_cause": "Answer/EvidencePack 边界或 verifier guard 失效。",
            "operator_action": "阻断发布，补测试并修复后重新跑 Quality Gate。",
        },
    ]


def _schema_profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    fields = profile.get("fields") or []
    inferred = Counter(field.get("inferred_type") for field in fields)
    return {
        "row_count": profile.get("row_count"),
        "column_count": profile.get("column_count"),
        "sheet_summaries": profile.get("sheet_summaries", []),
        "detected_header_row": profile.get("detected_header_row"),
        "header_detection_status": profile.get("header_detection_status"),
        "inferred_type_distribution": dict(inferred),
        "warnings": profile.get("warnings", []),
    }


def _dedupe_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for warning in warnings:
        key = (
            warning.get("code"),
            warning.get("message"),
            json.dumps(warning.get("details", {}), sort_keys=True, ensure_ascii=False),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped


def _trial_output_dir(output_root: Path, run_id: str | None) -> Path:
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    if "/" in run_id or "\\" in run_id or ".." in Path(run_id).parts:
        raise ValueError("run_id 不能包含路径穿越。")
    return output_root / run_id


def _dataset_id(source_path: Path) -> str:
    safe = "".join(
        char if char.isalnum() else "_"
        for char in source_path.stem.lower()
    )
    safe = safe.strip("_")[:24] or "admissions"
    return f"ds_operator_trial_{safe}"


def _json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(
        _json_ready(payload),
        ensure_ascii=False,
        indent=2,
    ) + "\n```"


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


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行真实招生 Excel/CSV operator trial。"
    )
    parser.add_argument("source_path", nargs="?", help="CSV/Excel 源文件路径。")
    parser.add_argument("--fixture", action="store_true", help="使用内置 fixture。")
    parser.add_argument("--sheet-name", default=None, help="Excel sheet 名称。")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--json-only", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
