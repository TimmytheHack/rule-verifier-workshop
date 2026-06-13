"""审查、批准或阻断 draft domain pack。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.generate_domain_pack import DRAFT_STATUS, REVIEW_STATUS
from src.domains import DomainConfig


APPROVED_STATUS = "approved"
BLOCKED_STATUS = "blocked"
DOMAIN_STATUS_VALUES = {DRAFT_STATUS, REVIEW_STATUS, APPROVED_STATUS, BLOCKED_STATUS}
REQUIRED_DRAFT_FILES = [
    "domain.yaml",
    "schema_mapping.yaml",
    "rule_taxonomy.seed.yaml",
    "top_result_mapping.yaml",
    "sort_policy.seed.yaml",
    "schema_profile.json",
    "schema_value_index.json",
    "domain.json",
    "schema_registry.json",
    "rule_taxonomy.json",
]
REQUIRED_RUNTIME_FILES = [
    "domain.json",
    "schema_registry.json",
    "rule_taxonomy.json",
    "top_result_mapping.yaml",
]
CONTRACT_KEYS = {
    "schema_version",
    "domain",
    "domain_version",
    "domain_pack_status",
    "status",
    "query",
    "answer",
    "result_count",
    "items",
    "top_results",
    "executed_filters",
    "candidates_to_confirm",
    "confirmed_rules",
    "unconfirmed_candidates",
    "unexecuted_preferences",
    "no_schema_field_preferences",
    "rejected_confirmations",
    "warnings",
    "evidence_pack",
    "debug_trace",
}
PII_KEYWORDS = {
    "name",
    "email",
    "e-mail",
    "mail",
    "phone",
    "mobile",
    "tel",
    "contact",
    "ssn",
    "passport",
    "id_card",
    "address",
    "note",
    "remark",
    "description",
    "姓名",
    "名称",
    "电话",
    "手机",
    "邮箱",
    "邮件",
    "身份证",
    "地址",
    "备注",
    "描述",
}
NUMERIC_OPS = {"eq", "<=", ">=", "between", "sort"}
CATEGORICAL_OPS = {"eq", "in", "not_in"}
TEXT_OPS = {"contains", "contains_any"}
CATEGORICAL_UNIQUE_LIMIT = 30
MAX_NULL_RATE_FOR_NUMERIC = 0.5


@dataclass(frozen=True)
class ReviewCommandResult:
    ok: bool
    written: bool
    message: str
    payload: dict[str, Any]


def summarize_domain_pack(domain: str | Path) -> dict[str, Any]:
    """读取 draft/review/runtime 文件，生成字段审查摘要。"""

    root = resolve_domain_dir(domain)
    files = _read_pack_files(root)
    review = load_review_metadata(root)
    schema = files.get("schema_registry.json") or {"fields": {}}
    profile_columns = _profile_columns(files)
    value_fields = (files.get("schema_value_index.json") or {}).get("fields", {})
    fields = []
    for field_id, spec in sorted((schema.get("fields") or {}).items()):
        profile = profile_columns.get(field_id, {})
        value_index = value_fields.get(field_id, {})
        fields.append(
            {
                "field_id": field_id,
                "source_column": spec.get("source_column"),
                "type": spec.get("type"),
                "status": spec.get("status"),
                "filter_policy": spec.get("filter_policy"),
                "candidate_allowed_ops": spec.get("candidate_allowed_ops", []),
                "allowed_ops": spec.get("allowed_ops", []),
                "reviewed": field_id in review["reviewed_fields"],
                "blocked": field_id in review["blocked_fields"],
                "approved_ops": review["approved_ops"].get(field_id, []),
                "blocked_ops": review["blocked_ops"].get(field_id, []),
                "null_rate": profile.get("null_rate"),
                "unique_count": profile.get("unique_count"),
                "high_cardinality": profile.get("high_cardinality"),
                "pii_risk": profile.get("pii_risk"),
                "value_index_reviewable": bool(
                    value_index.get("lookup_complete")
                    and value_index.get("lookup_values") is not None
                ),
            }
        )
    return {
        "domain_dir": str(root),
        "domain": review["domain"],
        "domain_version": review["domain_version"],
        "domain_pack_status": review["domain_pack_status"],
        "source_path": review["source_path"],
        "source_fingerprint": review["source_fingerprint"],
        "schema_profile_fingerprint": review["schema_profile_fingerprint"],
        "field_count": len(fields),
        "reviewed_field_count": len(review["reviewed_fields"]),
        "blocked_field_count": len(review["blocked_fields"]),
        "approved_op_count": sum(
            len(ops) for ops in review["approved_ops"].values()
        ),
        "fields": fields,
    }


def validate_domain_pack(domain: str | Path) -> dict[str, Any]:
    """校验 domain pack 的 review/runtime 结构。"""

    root = resolve_domain_dir(domain)
    checks = []
    files = _read_pack_files(root, missing_ok=True)
    domain_json = files.get("domain.json") or {}
    status = str(domain_json.get("status") or BLOCKED_STATUS)
    required_files = (
        REQUIRED_DRAFT_FILES
        if status in {DRAFT_STATUS, REVIEW_STATUS}
        else REQUIRED_RUNTIME_FILES
    )
    for filename in required_files:
        checks.append(_check(filename, filename in files, f"缺少 {filename}"))

    checks.append(
        _check(
            "domain_pack_status",
            status in DOMAIN_STATUS_VALUES,
            f"domain status 不合法：{status}",
        )
    )
    checks.append(
        _check(
            "workbench_response_contract",
            CONTRACT_KEYS == _workbench_contract_keys(),
            "WorkbenchResponse contract key set 不一致。",
        )
    )
    checks.extend(_validate_domain_config_shape(root, domain_json))
    checks.extend(_validate_schema_registry(files.get("schema_registry.json") or {}))
    checks.extend(_validate_top_result_mapping(files.get("top_result_mapping.yaml")))
    if "rule_taxonomy.seed.yaml" in files:
        checks.extend(_validate_rule_taxonomy(files.get("rule_taxonomy.seed.yaml")))
    else:
        checks.extend(_validate_runtime_rule_taxonomy(files.get("rule_taxonomy.json")))
    if "sort_policy.seed.yaml" in files:
        checks.extend(_validate_sort_policy(files.get("sort_policy.seed.yaml")))
    else:
        checks.extend(_validate_runtime_sort_policy(domain_json.get("execution") or {}))
    ok = all(item["ok"] for item in checks)
    return {
        "domain_dir": str(root),
        "ok": ok,
        "checks": checks,
    }


def approve_field(
    domain: str | Path,
    field_id: str,
    *,
    reviewed_by: str = "local_reviewer",
    note: str | None = None,
    write: bool = False,
) -> ReviewCommandResult:
    root = resolve_domain_dir(domain)
    state = _load_mutable_state(root)
    ok, reason = _field_can_be_approved(state, field_id)
    if not ok:
        return ReviewCommandResult(
            ok=False,
            written=False,
            message=reason,
            payload={"field_id": field_id, "reason": reason},
        )

    schema_field = state.schema["fields"][field_id]
    safe_candidates = [
        op
        for op in schema_field.get("candidate_allowed_ops", [])
        if _op_can_be_approved(state, field_id, op)[0]
    ]
    safe_ops = _default_field_ops(state, field_id, safe_candidates)
    if not safe_ops:
        return ReviewCommandResult(
            ok=False,
            written=False,
            message=f"{field_id} 没有可批准的安全 op。",
            payload={"field_id": field_id},
        )

    review = state.review
    review["reviewed_fields"][field_id] = {
        "status": APPROVED_STATUS,
        "approved_ops": safe_ops,
        "reviewed_by": reviewed_by,
        "reviewed_at": _utc_now(),
        "note": note,
    }
    review["approved_ops"][field_id] = safe_ops
    review["blocked_fields"].pop(field_id, None)
    _audit(review, "approve-field", reviewed_by, field_id=field_id, note=note)

    _activate_field(schema_field, safe_ops)
    _touch_review(review, state.domain)
    return _write_or_preview(
        root=root,
        state=state,
        write=write,
        message=f"approved field {field_id}",
    )


def block_field(
    domain: str | Path,
    field_id: str,
    *,
    reviewed_by: str = "local_reviewer",
    note: str | None = None,
    write: bool = False,
) -> ReviewCommandResult:
    root = resolve_domain_dir(domain)
    state = _load_mutable_state(root)
    if field_id not in state.schema.get("fields", {}):
        return _missing_field_result(field_id)
    review = state.review
    review["blocked_fields"][field_id] = {
        "status": BLOCKED_STATUS,
        "blocked_by": reviewed_by,
        "blocked_at": _utc_now(),
        "note": note,
    }
    review["reviewed_fields"].pop(field_id, None)
    review["approved_ops"].pop(field_id, None)
    _audit(review, "block-field", reviewed_by, field_id=field_id, note=note)

    schema_field = state.schema["fields"][field_id]
    schema_field["status"] = BLOCKED_STATUS
    schema_field["allowed_ops"] = []
    schema_field["reviewed"] = False
    schema_field["filter_policy"] = "blocked_by_review"
    _touch_review(review, state.domain)
    return _write_or_preview(
        root=root,
        state=state,
        write=write,
        message=f"blocked field {field_id}",
    )


def approve_op(
    domain: str | Path,
    field_id: str,
    op: str,
    *,
    reviewed_by: str = "local_reviewer",
    note: str | None = None,
    write: bool = False,
) -> ReviewCommandResult:
    root = resolve_domain_dir(domain)
    state = _load_mutable_state(root)
    op = _normalize_op(op)
    ok, reason = _op_can_be_approved(state, field_id, op)
    if not ok:
        return ReviewCommandResult(
            ok=False,
            written=False,
            message=reason,
            payload={"field_id": field_id, "op": op, "reason": reason},
        )
    review = state.review
    approved = _unique([*review["approved_ops"].get(field_id, []), op])
    review["approved_ops"][field_id] = approved
    review["reviewed_fields"].setdefault(
        field_id,
        {
            "status": APPROVED_STATUS,
            "reviewed_by": reviewed_by,
            "reviewed_at": _utc_now(),
            "note": note,
        },
    )
    review["reviewed_fields"][field_id]["approved_ops"] = approved
    _audit(review, "approve-op", reviewed_by, field_id=field_id, op=op, note=note)

    schema_field = state.schema["fields"][field_id]
    _activate_field(schema_field, approved)
    _touch_review(review, state.domain)
    return _write_or_preview(
        root=root,
        state=state,
        write=write,
        message=f"approved op {field_id} {op}",
    )


def block_op(
    domain: str | Path,
    field_id: str,
    op: str,
    *,
    reviewed_by: str = "local_reviewer",
    note: str | None = None,
    write: bool = False,
) -> ReviewCommandResult:
    root = resolve_domain_dir(domain)
    state = _load_mutable_state(root)
    if field_id not in state.schema.get("fields", {}):
        return _missing_field_result(field_id)
    op = _normalize_op(op)
    review = state.review
    review["blocked_ops"][field_id] = _unique(
        [*review["blocked_ops"].get(field_id, []), op]
    )
    review["approved_ops"][field_id] = [
        item for item in review["approved_ops"].get(field_id, []) if item != op
    ]
    _audit(review, "block-op", reviewed_by, field_id=field_id, op=op, note=note)
    state.schema["fields"][field_id]["allowed_ops"] = review["approved_ops"].get(
        field_id,
        [],
    )
    _touch_review(review, state.domain)
    return _write_or_preview(
        root=root,
        state=state,
        write=write,
        message=f"blocked op {field_id} {op}",
    )


def approve_domain(
    domain: str | Path,
    *,
    title_field: str | None = None,
    primary_fields: list[str] | None = None,
    sort_field: str | None = None,
    default_safe_sort: bool = False,
    reviewed_by: str = "local_reviewer",
    note: str | None = None,
    write: bool = False,
) -> ReviewCommandResult:
    root = resolve_domain_dir(domain)
    state = _load_mutable_state(root)
    primary_fields = primary_fields or []
    failures = _approve_domain_failures(
        state=state,
        title_field=title_field,
        primary_fields=primary_fields,
        sort_field=sort_field,
        default_safe_sort=default_safe_sort,
    )
    if failures:
        return ReviewCommandResult(
            ok=False,
            written=False,
            message="approve-domain checks failed",
            payload={"failures": failures},
        )

    review = state.review
    state.domain["status"] = APPROVED_STATUS
    state.domain["review_required"] = False
    state.domain["domain_version"] = str(state.domain.get("domain_version") or "1")
    state.domain.setdefault("paths", {})["top_result_mapping"] = (
        "top_result_mapping.yaml"
    )
    review["domain_pack_status"] = APPROVED_STATUS
    review["item_mapping"] = {
        "title_field_id": title_field,
        "primary_attribute_field_ids": primary_fields,
    }
    review["sort_policy"] = {
        "sort_field_id": sort_field,
        "default_safe_sort": default_safe_sort,
    }
    _audit(
        review,
        "approve-domain",
        reviewed_by,
        note=note,
        title_field=title_field,
        primary_fields=primary_fields,
        sort_field=sort_field,
        default_safe_sort=default_safe_sort,
    )
    _sync_runtime_config(
        state=state,
        title_field=title_field or "",
        primary_fields=primary_fields,
        sort_field=sort_field,
        default_safe_sort=default_safe_sort,
    )
    _touch_review(review, state.domain)
    return _write_or_preview(
        root=root,
        state=state,
        write=write,
        message=f"approved domain {state.review['domain']}",
    )


def write_review_report(
    domain: str | Path,
    *,
    output_dir: str | Path = "outputs/domain_review",
    write: bool = False,
) -> ReviewCommandResult:
    root = resolve_domain_dir(domain)
    summary = summarize_domain_pack(root)
    validation = validate_domain_pack(root)
    review = load_review_metadata(root)
    payload = {
        "generated_at": _utc_now(),
        "domain_dir": str(root),
        "summary": summary,
        "validation": validation,
        "review": review,
    }
    output_root = Path(output_dir)
    domain_id = review["domain"]
    json_path = output_root / f"{domain_id}_review.json"
    md_path = output_root / f"{domain_id}_review.md"
    if write:
        output_root.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(_json_ready(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(_render_review_markdown(payload), encoding="utf-8")
    return ReviewCommandResult(
        ok=True,
        written=write,
        message=f"review report {'written' if write else 'preview'}",
        payload={
            **payload,
            "json_path": str(json_path),
            "markdown_path": str(md_path),
        },
    )


@dataclass
class _MutableState:
    root: Path
    domain: dict[str, Any]
    schema: dict[str, Any]
    rule_taxonomy: dict[str, Any]
    attribute_grounding: dict[str, Any]
    answer_templates: dict[str, Any]
    review: dict[str, Any]
    top_result_mapping: Any
    sort_policy: Any
    schema_profile: dict[str, Any]
    schema_value_index: dict[str, Any]


def resolve_domain_dir(domain: str | Path) -> Path:
    path = Path(domain)
    if path.exists():
        return path
    candidate = ROOT_DIR / "domains" / str(domain)
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Domain pack not found: {domain}")


def load_review_metadata(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    review_path = root / "review.yaml"
    if review_path.exists():
        review = _load_yaml(review_path) or {}
    else:
        review = {}
    domain = _load_json(root / "domain.json", missing_ok=True) or {}
    profile = _load_json(root / "schema_profile.json", missing_ok=True) or {}
    summary = _load_json(root / "ingestion_summary.json", missing_ok=True) or {}
    source = profile.get("source") or {}
    return _normalized_review(
        review=review,
        domain=domain,
        profile=profile,
        summary=summary,
        root=root,
        source=source,
    )


def _normalized_review(
    *,
    review: dict[str, Any],
    domain: dict[str, Any],
    profile: dict[str, Any],
    summary: dict[str, Any],
    root: Path,
    source: dict[str, Any],
) -> dict[str, Any]:
    domain_id = str(
        review.get("domain")
        or domain.get("domain_id")
        or profile.get("domain_id")
        or root.name
    )
    status = str(
        review.get("domain_pack_status")
        or domain.get("status")
        or profile.get("status")
        or DRAFT_STATUS
    )
    return {
        "domain": domain_id,
        "domain_version": str(
            review.get("domain_version")
            or domain.get("domain_version")
            or "1"
        ),
        "domain_pack_status": status,
        "source_path": str(
            review.get("source_path")
            or summary.get("source_path")
            or source.get("path")
            or (domain.get("data") or {}).get("workbook_path")
            or ""
        ),
        "source_fingerprint": review.get("source_fingerprint")
        or summary.get("source_fingerprint")
        or summary.get("fingerprint"),
        "schema_profile_fingerprint": review.get("schema_profile_fingerprint")
        or _file_sha256(root / "schema_profile.json"),
        "reviewed_fields": dict(review.get("reviewed_fields") or {}),
        "blocked_fields": dict(review.get("blocked_fields") or {}),
        "approved_ops": {
            key: list(value or [])
            for key, value in (review.get("approved_ops") or {}).items()
        },
        "blocked_ops": {
            key: list(value or [])
            for key, value in (review.get("blocked_ops") or {}).items()
        },
        "review_notes": list(review.get("review_notes") or []),
        "reviewed_at": review.get("reviewed_at"),
        "reviewed_by": review.get("reviewed_by"),
        "approval_history": list(review.get("approval_history") or []),
        "item_mapping": dict(review.get("item_mapping") or {}),
        "sort_policy": dict(review.get("sort_policy") or {}),
    }


def _read_pack_files(root: Path, missing_ok: bool = False) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for filename in REQUIRED_DRAFT_FILES + [
        "review.yaml",
        "attribute_grounding.json",
        "answer_templates.json",
        "ingestion_summary.json",
    ]:
        path = root / filename
        if not path.exists():
            if not missing_ok:
                continue
            continue
        if path.suffix in {".yaml", ".yml"}:
            files[filename] = _load_yaml(path)
        elif path.suffix == ".json":
            files[filename] = _load_json(path)
    return files


def _load_mutable_state(root: Path) -> _MutableState:
    return _MutableState(
        root=root,
        domain=_load_json(root / "domain.json"),
        schema=_load_json(root / "schema_registry.json"),
        rule_taxonomy=_load_json(root / "rule_taxonomy.json"),
        attribute_grounding=_load_json(root / "attribute_grounding.json"),
        answer_templates=_load_json(root / "answer_templates.json"),
        review=load_review_metadata(root),
        top_result_mapping=_load_yaml(root / "top_result_mapping.yaml"),
        sort_policy=_load_yaml(root / "sort_policy.seed.yaml"),
        schema_profile=_load_json(root / "schema_profile.json"),
        schema_value_index=_load_json(root / "schema_value_index.json"),
    )


def _field_can_be_approved(
    state: _MutableState,
    field_id: str,
) -> tuple[bool, str]:
    if field_id not in state.schema.get("fields", {}):
        return False, f"字段不存在：{field_id}"
    if field_id in state.review["blocked_fields"]:
        return False, f"字段已被 block：{field_id}"
    spec = state.schema["fields"][field_id]
    profile = _profile_for_field(state, field_id)
    if _has_pii_risk(spec, profile):
        return False, f"{field_id} 是 PII/自由文本风险字段，不能默认 approve。"
    if _is_high_cardinality(spec, profile):
        return False, f"{field_id} 是高基数字段，不能作为 categorical hard filter。"
    if spec.get("type") in {"string", "long_text"} and _candidate_ops(spec) & TEXT_OPS:
        return False, f"{field_id} 是文本 contains 候选，必须保持 needs_review。"
    return True, "ok"


def _op_can_be_approved(
    state: _MutableState,
    field_id: str,
    op: str,
) -> tuple[bool, str]:
    if field_id not in state.schema.get("fields", {}):
        return False, f"字段不存在：{field_id}"
    if field_id in state.review["blocked_fields"]:
        return False, f"字段已被 block：{field_id}"
    op = _normalize_op(op)
    spec = state.schema["fields"][field_id]
    profile = _profile_for_field(state, field_id)
    if op not in _candidate_ops(spec):
        return False, f"{op} 不在 {field_id} 的 candidate_allowed_ops 中。"
    if op in state.review["blocked_ops"].get(field_id, []):
        return False, f"{field_id} {op} 已被 block。"
    if _has_pii_risk(spec, profile):
        return False, f"{field_id} 是 PII/自由文本风险字段，不能 approve op。"
    if op in TEXT_OPS:
        return False, "text contains / keyword filter 默认 needs_review，不能自动 approve。"
    if op in NUMERIC_OPS and spec.get("type") in {"number", "number_from_string"}:
        return _numeric_sanity_ok(profile)
    if op in CATEGORICAL_OPS:
        return _categorical_sanity_ok(state, field_id, profile)
    if op == "sort":
        return True, "ok"
    return False, f"不支持批准 op：{op}"


def _sync_runtime_config(
    *,
    state: _MutableState,
    title_field: str,
    primary_fields: list[str],
    sort_field: str | None,
    default_safe_sort: bool,
) -> None:
    output_fields = _unique(
        [title_field, *primary_fields, *_approved_rule_fields(state.review)]
    )
    state.domain["data"]["required_field_ids"] = output_fields
    state.domain["execution"] = _execution_config(
        state.schema["fields"],
        output_fields=output_fields,
        sort_field=sort_field,
        default_safe_sort=default_safe_sort,
    )
    state.top_result_mapping = [
        {"key": "title", "field_id": title_field},
        *[
            {"key": field_id, "field_id": field_id}
            for field_id in primary_fields
        ],
    ]
    state.rule_taxonomy["status"] = APPROVED_STATUS
    state.rule_taxonomy["deterministic_rules"] = _deterministic_rules(state)
    state.rule_taxonomy["candidate_rules"] = []
    state.attribute_grounding["status"] = APPROVED_STATUS
    state.attribute_grounding["slot_policies"] = {
        f"preferences.{field_id}": {
            "field_id": field_id,
            "status": "schema_grounded",
            "reason": "字段已通过 domain pack review，可进入 RuleVerifier 审计。",
        }
        for field_id in _approved_rule_fields(state.review)
    }
    state.attribute_grounding["other_vague_policies"] = {}
    state.domain.setdefault("workbench", {})["context_warnings"] = []
    state.answer_templates.update(
        {
            "status": APPROVED_STATUS,
            "rank_field_id": None,
            "money_field_ids": [],
            "result_line_fields": [
                {"field_id": field_id, "label": field_id, "evidence_key": field_id}
                for field_id in output_fields
            ],
            "result_text_fields": [
                {"field_id": field_id, "label": field_id, "evidence_key": field_id}
                for field_id in output_fields
            ],
        }
    )


def _approve_domain_failures(
    *,
    state: _MutableState,
    title_field: str | None,
    primary_fields: list[str],
    sort_field: str | None,
    default_safe_sort: bool,
) -> list[str]:
    failures = []
    validation = validate_domain_pack(state.root)
    if not validation["ok"]:
        failures.extend(
            check["message"] for check in validation["checks"] if not check["ok"]
        )
    if not state.review["approved_ops"]:
        failures.append("至少需要批准一个 field op。")
    if not title_field:
        failures.append("缺少 item title mapping；请传 --title-field。")
    elif title_field not in state.schema.get("fields", {}):
        failures.append(f"title field 不存在：{title_field}")
    elif title_field not in state.review["reviewed_fields"]:
        failures.append(f"title field 尚未 approve-field：{title_field}")
    if not primary_fields:
        failures.append("缺少 primary attribute mapping；请至少传一个 --primary-field。")
    for field_id in primary_fields:
        if field_id not in state.schema.get("fields", {}):
            failures.append(f"primary field 不存在：{field_id}")
        elif field_id not in state.review["reviewed_fields"]:
            failures.append(f"primary field 尚未 approve-field：{field_id}")
    if not sort_field and not default_safe_sort:
        failures.append("缺少 sort_policy；请传 --sort-field 或 --default-safe-sort。")
    if sort_field:
        if sort_field not in state.review["reviewed_fields"]:
            failures.append(f"sort field 尚未 approve-field：{sort_field}")
        else:
            ok, reason = _op_can_be_approved(state, sort_field, "sort")
            if not ok:
                failures.append(f"sort field 不安全：{reason}")
    return failures


def _deterministic_rules(state: _MutableState) -> list[dict[str, Any]]:
    rules = []
    for field_id, ops in sorted(state.review["approved_ops"].items()):
        spec = state.schema["fields"].get(field_id) or {}
        for op in ops:
            if op == "sort":
                continue
            rules.append(
                {
                    "rule_id": f"d_{field_id}_{_op_id(op)}",
                    "source_text": field_id,
                    "category": "deterministic",
                    "field_id": field_id,
                    "field": spec.get("source_column") or field_id,
                    "operator": op,
                    "slot_path": ["preferences", field_id],
                    "skip_if_missing": True,
                    "confidence": 1.0,
                    "requires_human_confirmation": False,
                    "trace_reason": "字段和 op 已通过 domain pack review。",
                }
            )
    return rules


def _execution_config(
    fields: dict[str, dict[str, Any]],
    *,
    output_fields: list[str],
    sort_field: str | None,
    default_safe_sort: bool,
) -> dict[str, Any]:
    numeric_helpers = []
    helper_by_field = {}
    output_specs = []
    for field_id in output_fields:
        spec = fields[field_id]
        transform = _transform_for_type(spec.get("type"))
        output_spec = {"output_key": field_id, "field_id": field_id, "transform": transform}
        if spec.get("type") in {"number", "number_from_string"}:
            helper = f"__{field_id}_num"
            helper_by_field[field_id] = helper
            numeric_helpers.append({"name": helper, "field_id": field_id})
            output_spec["helper"] = helper
        output_specs.append(output_spec)
    sort_policy = []
    if sort_field and not default_safe_sort:
        helper = helper_by_field.get(sort_field)
        if helper:
            sort_policy.append(
                {
                    "helper": helper,
                    "label_field_id": sort_field,
                    "direction": "ASC",
                    "nulls": "LAST",
                }
            )
    return {
        "rank_field_id": None,
        "tuition_field_id": None,
        "projectable_required_field_ids": [],
        "numeric_helper_fields": numeric_helpers,
        "sort_policy": sort_policy,
        "row_number_output_key": "source_row_number",
        "row_number_offset": 1,
        "output_fields": output_specs,
        "static_output_fields": {},
    }


def _write_or_preview(
    *,
    root: Path,
    state: _MutableState,
    write: bool,
    message: str,
) -> ReviewCommandResult:
    payload = {
        "domain": state.review["domain"],
        "domain_pack_status": state.review["domain_pack_status"],
        "review": state.review,
        "domain_json": state.domain,
        "schema_registry": state.schema,
    }
    if write:
        _write_yaml(root / "review.yaml", state.review)
        _write_json(root / "domain.json", state.domain)
        _write_json(root / "schema_registry.json", state.schema)
        _write_json(root / "rule_taxonomy.json", state.rule_taxonomy)
        _write_json(root / "attribute_grounding.json", state.attribute_grounding)
        _write_json(root / "answer_templates.json", state.answer_templates)
        _write_yaml(root / "top_result_mapping.yaml", state.top_result_mapping)
    return ReviewCommandResult(
        ok=True,
        written=write,
        message=f"{message} ({'written' if write else 'dry-run'})",
        payload=payload,
    )


def _validate_domain_config_shape(
    root: Path,
    domain_json: dict[str, Any],
) -> list[dict[str, Any]]:
    checks = []
    for key in ["domain_id", "status", "data", "paths", "execution", "workbench"]:
        checks.append(_check(f"domain.{key}", key in domain_json, f"domain.json 缺少 {key}"))
    try:
        domain = DomainConfig.from_path(root)
        checks.append(
            _check(
                "DomainConfig.load",
                domain.pack_status in DOMAIN_STATUS_VALUES,
                "DomainConfig pack_status 不合法。",
            )
        )
    except Exception as exc:  # noqa: BLE001 - validate 需要汇总所有结构问题。
        checks.append(_check("DomainConfig.load", False, str(exc)))
    return checks


def _validate_schema_registry(schema: dict[str, Any]) -> list[dict[str, Any]]:
    fields = schema.get("fields")
    checks = [_check("schema.fields", isinstance(fields, dict), "schema 缺少 fields")]
    if not isinstance(fields, dict):
        return checks
    for field_id, spec in fields.items():
        ok = all(key in spec for key in ["source_column", "type", "allowed_ops"])
        checks.append(
            _check(
                f"schema.field.{field_id}",
                ok,
                f"{field_id} 缺少 source_column/type/allowed_ops。",
            )
        )
    return checks


def _validate_top_result_mapping(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        candidates = payload.get("candidate_top_result_mapping")
        return [
            _check(
                "top_result_mapping.seed",
                isinstance(candidates, list),
                "top_result_mapping.yaml 缺少 candidate_top_result_mapping。",
            )
        ]
    if isinstance(payload, list):
        return [
            _check(
                "top_result_mapping.runtime",
                all(_valid_runtime_top_result_item(item) for item in payload),
                "runtime top_result_mapping 每项必须包含 key，并声明 field_id、field_ids 或 computed。",
            )
        ]
    return [_check("top_result_mapping", False, "top_result_mapping 结构不合法。")]


def _valid_runtime_top_result_item(item: Any) -> bool:
    return isinstance(item, dict) and "key" in item and any(
        key in item for key in ["field_id", "field_ids", "computed"]
    )


def _validate_rule_taxonomy(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return [_check("rule_taxonomy.seed", False, "rule taxonomy seed 不是对象。")]
    return [
        _check(
            "rule_taxonomy.seed.candidate_rules",
            isinstance(payload.get("candidate_rules"), list),
            "rule_taxonomy.seed.yaml 缺少 candidate_rules。",
        )
    ]


def _validate_runtime_rule_taxonomy(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return [_check("rule_taxonomy.runtime", False, "rule_taxonomy.json 不是对象。")]
    checks = []
    for key in ["deterministic_rules", "candidate_rules", "non_executable_preferences"]:
        checks.append(
            _check(
                f"rule_taxonomy.runtime.{key}",
                isinstance(payload.get(key), list),
                f"rule_taxonomy.json 缺少列表字段 {key}。",
            )
        )
    return checks


def _validate_sort_policy(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return [_check("sort_policy.seed", False, "sort policy seed 不是对象。")]
    return [
        _check(
            "sort_policy.seed.candidate_sort_policy",
            isinstance(payload.get("candidate_sort_policy"), list),
            "sort_policy.seed.yaml 缺少 candidate_sort_policy。",
        )
    ]


def _validate_runtime_sort_policy(execution: dict[str, Any]) -> list[dict[str, Any]]:
    sort_policy = execution.get("sort_policy")
    explicit_default = bool(execution.get("default_safe_sort"))
    return [
        _check(
            "sort_policy.runtime",
            isinstance(sort_policy, list) and (bool(sort_policy) or explicit_default),
            "runtime execution.sort_policy 必须非空，或显式声明 default_safe_sort。",
        )
    ]


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": "ok" if ok else message}


def _workbench_contract_keys() -> set[str]:
    from src.api.workbench import WorkbenchResponse

    return set(WorkbenchResponse.__dataclass_fields__)


def _profile_columns(files: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profile = files.get("schema_profile.json") or {}
    return {
        column["field_id"]: column
        for column in profile.get("columns", [])
        if "field_id" in column
    }


def _profile_for_field(state: _MutableState, field_id: str) -> dict[str, Any]:
    for column in state.schema_profile.get("columns", []):
        if column.get("field_id") == field_id:
            return column
    return (state.schema["fields"].get(field_id) or {}).get("profile") or {}


def _has_pii_risk(spec: dict[str, Any], profile: dict[str, Any]) -> bool:
    if profile.get("pii_risk") or (spec.get("profile") or {}).get("pii_risk"):
        return True
    text = " ".join(
        str(value or "")
        for value in [
            spec.get("source_column"),
            spec.get("label"),
            profile.get("source_column"),
            profile.get("label"),
        ]
    ).lower()
    return any(keyword.lower() in text for keyword in PII_KEYWORDS)


def _is_high_cardinality(spec: dict[str, Any], profile: dict[str, Any]) -> bool:
    return bool(
        profile.get("high_cardinality")
        or (spec.get("profile") or {}).get("high_cardinality")
    )


def _numeric_sanity_ok(profile: dict[str, Any]) -> tuple[bool, str]:
    numeric = profile.get("numeric")
    if not numeric:
        return False, "数值字段缺少 numeric profile。"
    null_rate = float(profile.get("null_rate") or 0)
    if null_rate > MAX_NULL_RATE_FOR_NUMERIC:
        return False, f"数值字段空值率过高：{null_rate}"
    min_value = numeric.get("min")
    max_value = numeric.get("max")
    if min_value is None or max_value is None:
        return False, "数值字段缺少 min/max。"
    if not all(_finite_number(value) for value in [min_value, max_value]):
        return False, "数值字段范围不是有限数。"
    if float(min_value) > float(max_value):
        return False, "数值字段 min/max 不合法。"
    return True, "ok"


def _categorical_sanity_ok(
    state: _MutableState,
    field_id: str,
    profile: dict[str, Any],
) -> tuple[bool, str]:
    unique_count = int(profile.get("unique_count") or 0)
    if unique_count > CATEGORICAL_UNIQUE_LIMIT:
        return False, f"唯一值数量过高：{unique_count}"
    value_field = (state.schema_value_index.get("fields") or {}).get(field_id) or {}
    if not value_field.get("lookup_complete"):
        return False, "value_index 不完整，不能审查 categorical 值。"
    if value_field.get("lookup_values") is None:
        return False, "value_index 缺少 lookup_values。"
    return True, "ok"


def _candidate_ops(spec: dict[str, Any]) -> set[str]:
    return set(spec.get("candidate_allowed_ops") or spec.get("allowed_ops") or [])


def _default_field_ops(
    state: _MutableState,
    field_id: str,
    candidates: list[str],
) -> list[str]:
    spec = state.schema["fields"][field_id]
    profile = _profile_for_field(state, field_id)
    role = str(profile.get("role") or spec.get("role") or "")
    source = str(spec.get("source_column") or field_id).lower()
    if role == "identifier" or source.endswith("_id") or source == "id":
        return ["eq"] if "eq" in candidates else candidates[:1]
    if spec.get("type") == "enum":
        if "in" in candidates:
            return ["in"]
        if "eq" in candidates:
            return ["eq"]
    if spec.get("type") in {"number", "number_from_string"}:
        for op in ["<=", ">=", "between", "eq"]:
            if op in candidates:
                return [op]
    return candidates[:1]


def _activate_field(schema_field: dict[str, Any], allowed_ops: list[str]) -> None:
    schema_field["status"] = "active"
    schema_field["reviewed"] = True
    schema_field["allowed_ops"] = _unique(allowed_ops)
    schema_field["review_required"] = False


def _approved_rule_fields(review: dict[str, Any]) -> list[str]:
    return [field_id for field_id, ops in review["approved_ops"].items() if ops]


def _touch_review(review: dict[str, Any], domain: dict[str, Any]) -> None:
    now = _utc_now()
    review["reviewed_at"] = now
    if history := review.get("approval_history"):
        review["reviewed_by"] = history[-1].get("reviewed_by")
    review["domain_pack_status"] = domain.get("status") or review["domain_pack_status"]


def _audit(
    review: dict[str, Any],
    action: str,
    reviewed_by: str,
    **details: Any,
) -> None:
    review.setdefault("approval_history", []).append(
        {
            "action": action,
            "reviewed_by": reviewed_by,
            "reviewed_at": _utc_now(),
            "details": {key: value for key, value in details.items() if value is not None},
        }
    )


def _missing_field_result(field_id: str) -> ReviewCommandResult:
    return ReviewCommandResult(
        ok=False,
        written=False,
        message=f"字段不存在：{field_id}",
        payload={"field_id": field_id},
    )


def _normalize_op(op: str) -> str:
    return {"=": "eq", "==": "eq", "≤": "<=", "≥": ">="}.get(op, op)


def _op_id(op: str) -> str:
    return {
        "eq": "eq",
        "<=": "le",
        ">=": "ge",
        "between": "between",
        "in": "in",
        "not_in": "not_in",
    }.get(op, op.replace(" ", "_"))


def _transform_for_type(field_type: Any) -> str:
    if field_type in {"number", "number_from_string"}:
        return "number"
    return "text"


def _finite_number(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed)


def _unique(values: list[Any]) -> list[Any]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _load_json(path: Path, missing_ok: bool = False) -> dict[str, Any]:
    if missing_ok and not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: Any) -> None:
    path.write_text(
        yaml.safe_dump(
            _json_ready(payload),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _render_review_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    validation = payload["validation"]
    review = payload["review"]
    lines = [
        f"# {summary['domain']} Domain Pack 审查报告",
        "",
        f"- domain：`{summary['domain']}`",
        f"- domain_version：`{summary['domain_version']}`",
        f"- domain_pack_status：`{summary['domain_pack_status']}`",
        f"- source_path：`{summary['source_path']}`",
        f"- reviewed_fields：`{summary['reviewed_field_count']}`",
        f"- blocked_fields：`{summary['blocked_field_count']}`",
        f"- approved_ops：`{summary['approved_op_count']}`",
        f"- validate：`{'通过' if validation['ok'] else '失败'}`",
        "",
        "## 字段摘要",
        "",
        "| field_id | source_column | type | allowed_ops | blocked | pii | high_cardinality |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for field in summary["fields"]:
        lines.append(
            "| {field_id} | {source_column} | {type} | {ops} | {blocked} | {pii} | {high} |".format(
                field_id=field["field_id"],
                source_column=field.get("source_column") or "",
                type=field.get("type") or "",
                ops=", ".join(field.get("allowed_ops") or []),
                blocked="是" if field.get("blocked") else "否",
                pii="是" if field.get("pii_risk") else "否",
                high="是" if field.get("high_cardinality") else "否",
            )
        )
    lines.extend(
        [
            "",
            "## 校验结果",
            "",
            "| check | result | message |",
            "|---|---:|---|",
        ]
    )
    for check in validation["checks"]:
        lines.append(
            f"| {check['name']} | {'通过' if check['ok'] else '失败'} | {check['message']} |"
        )
    lines.extend(
        [
            "",
            "## 审计历史",
            "",
            "```json",
            json.dumps(
                _json_ready(review.get("approval_history", [])),
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("domain")

    validate = subparsers.add_parser("validate")
    validate.add_argument("domain")

    approve_field_parser = subparsers.add_parser("approve-field")
    _add_mutation_args(approve_field_parser)
    approve_field_parser.add_argument("field_id")

    block_field_parser = subparsers.add_parser("block-field")
    _add_mutation_args(block_field_parser)
    block_field_parser.add_argument("field_id")

    approve_op_parser = subparsers.add_parser("approve-op")
    _add_mutation_args(approve_op_parser)
    approve_op_parser.add_argument("field_id")
    approve_op_parser.add_argument("op")

    block_op_parser = subparsers.add_parser("block-op")
    _add_mutation_args(block_op_parser)
    block_op_parser.add_argument("field_id")
    block_op_parser.add_argument("op")

    approve_domain_parser = subparsers.add_parser("approve-domain")
    _add_mutation_args(approve_domain_parser)
    approve_domain_parser.add_argument("--title-field")
    approve_domain_parser.add_argument(
        "--primary-field",
        action="append",
        default=[],
        dest="primary_fields",
    )
    approve_domain_parser.add_argument("--sort-field")
    approve_domain_parser.add_argument("--default-safe-sort", action="store_true")

    report = subparsers.add_parser("report")
    report.add_argument("domain")
    report.add_argument("--output-dir", default="outputs/domain_review")
    report.add_argument("--write", action="store_true")
    return parser


def _add_mutation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("domain")
    parser.add_argument("--reviewed-by", default="local_reviewer")
    parser.add_argument("--note")
    parser.add_argument("--write", action="store_true")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "summarize":
        payload = summarize_domain_pack(args.domain)
        print(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate":
        payload = validate_domain_pack(args.domain)
        print(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2))
        return 0 if payload["ok"] else 1
    if args.command == "approve-field":
        result = approve_field(
            args.domain,
            args.field_id,
            reviewed_by=args.reviewed_by,
            note=args.note,
            write=args.write,
        )
    elif args.command == "block-field":
        result = block_field(
            args.domain,
            args.field_id,
            reviewed_by=args.reviewed_by,
            note=args.note,
            write=args.write,
        )
    elif args.command == "approve-op":
        result = approve_op(
            args.domain,
            args.field_id,
            args.op,
            reviewed_by=args.reviewed_by,
            note=args.note,
            write=args.write,
        )
    elif args.command == "block-op":
        result = block_op(
            args.domain,
            args.field_id,
            args.op,
            reviewed_by=args.reviewed_by,
            note=args.note,
            write=args.write,
        )
    elif args.command == "approve-domain":
        result = approve_domain(
            args.domain,
            title_field=args.title_field,
            primary_fields=args.primary_fields,
            sort_field=args.sort_field,
            default_safe_sort=args.default_safe_sort,
            reviewed_by=args.reviewed_by,
            note=args.note,
            write=args.write,
        )
    elif args.command == "report":
        result = write_review_report(
            args.domain,
            output_dir=args.output_dir,
            write=args.write,
        )
    else:  # pragma: no cover - argparse prevents this.
        raise AssertionError(args.command)
    print(json.dumps(_json_ready(result.payload), ensure_ascii=False, indent=2))
    if result.message:
        print(result.message, file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
