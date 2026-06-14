"""Functional tool registry for LLM-safe structured data workflows."""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - 依赖安装前的降级路径。
    Draft202012Validator = None  # type: ignore[assignment]

from scripts.run_quality_gate import QualityGateOptions, run_quality_gate
from scripts.run_real_dataset_pilot import (
    _json_ready as _pilot_json_ready,
    _render_markdown as _render_pilot_markdown,
    _fixture_path,
    run_pilot,
)
from src.api.dataset_service import DatasetService, DatasetServiceError
from src.api.workbench import WorkbenchConfig, run_workbench


ROOT_DIR = Path(__file__).resolve().parents[2]
TOOL_SCHEMA_DIR = ROOT_DIR / "schemas/tools"
DEFAULT_AUDIT_PATH = ROOT_DIR / "outputs/tool_audit/audit.jsonl"
TOOL_CONTRACT_VERSION = "tools.v1"
LLM_SAFE_TOOL_NAMES = {
    "dataset.profile",
    "dataset.review_summary",
    "workbench.query",
    "workbench.confirm",
    "evidence.get",
}
FORBIDDEN_LLM_INPUT_FIELDS = {
    "raw_sql",
    "sql",
    "executable_rules",
    "executable_rule",
    "hard_rules",
    "hard_rule",
    "approved_ops",
    "domain_pack_status",
}
PERMISSION_SCOPES = {
    "read_only",
    "query",
    "confirm",
    "dataset_write",
    "review_admin",
    "warehouse_admin",
    "diagnostics",
}
SECRET_KEY_PATTERN = re.compile(
    r"(secret|api[_-]?key|token|password|passwd|env|traceback|stack)",
    re.IGNORECASE,
)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(/Users/[^\s\"']+|/tmp/[^\s\"']+|/var/[^\s\"']+)"
)


class ToolRegistryError(ValueError):
    """tool registry 的结构化错误。"""


class ToolPermissionError(PermissionError):
    """actor_context 缺少 tool 所需权限。"""


@dataclass(frozen=True)
class ToolInvocation:
    """记录一次 tool invocation 的审计摘要。"""

    tool_name: str
    actor_id: str
    permission_scope: str
    status: str
    duration_seconds: float
    side_effects: list[str]
    message: str | None = None
    dataset_id: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "actor_id": _sanitize_audit_value(self.actor_id),
            "permission_scope": self.permission_scope,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 3),
            "side_effects": self.side_effects,
            "message": _sanitize_audit_value(self.message),
            "dataset_id": _sanitize_audit_value(self.dataset_id),
            "error_code": self.error_code,
            "created_at": _utc_now(),
        }


def list_tools(
    permission_scope: str | None = None,
    llm_safe_only: bool = False,
) -> list[dict[str, Any]]:
    """列出可调用 tool contract。"""

    contracts = [_public_contract(contract) for contract in _load_contracts().values()]
    if permission_scope:
        contracts = [
            contract
            for contract in contracts
            if contract["permission_scope"] == permission_scope
        ]
    if llm_safe_only:
        contracts = [
            contract
            for contract in contracts
            if contract.get("llm_safe") and contract["name"] in LLM_SAFE_TOOL_NAMES
        ]
    return sorted(contracts, key=lambda item: item["name"])


def get_tool_schema(tool_name: str) -> dict[str, Any]:
    """返回单个 tool 的完整 contract。"""

    contracts = _load_contracts()
    if tool_name not in contracts:
        raise ToolRegistryError(f"Unknown tool: {tool_name}")
    return dict(contracts[tool_name])


def invoke_tool(
    tool_name: str,
    payload: dict[str, Any],
    actor_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行 tool 并写入审计事件。"""

    actor_context = actor_context or {}
    contract = get_tool_schema(tool_name)
    actor_id = str(actor_context.get("actor_id") or "anonymous")
    dataset_id = _payload_dataset_id(payload)
    started = time.monotonic()
    try:
        _enforce_permission(contract, actor_context)
        _validate_payload(contract, payload)
        if contract.get("llm_safe"):
            _reject_forbidden_input_fields(payload)
        output = _dispatch_tool(tool_name, payload, actor_context)
        _write_audit_event(
            actor_context,
            ToolInvocation(
                tool_name=tool_name,
                actor_id=actor_id,
                permission_scope=contract["permission_scope"],
                status="ok",
                duration_seconds=time.monotonic() - started,
                side_effects=list(contract.get("side_effects") or []),
                dataset_id=dataset_id,
            ),
        )
        return output
    except Exception as exc:
        _write_audit_event(
            actor_context,
            ToolInvocation(
                tool_name=tool_name,
                actor_id=actor_id,
                permission_scope=contract["permission_scope"],
                status="error",
                duration_seconds=time.monotonic() - started,
                side_effects=list(contract.get("side_effects") or []),
                message=str(exc),
                dataset_id=dataset_id,
                error_code=_error_code(exc),
            ),
        )
        raise


def _dispatch_tool(
    tool_name: str,
    payload: dict[str, Any],
    actor_context: dict[str, Any],
) -> dict[str, Any]:
    service = _dataset_service(actor_context)
    if tool_name == "dataset.upload":
        return _tool_dataset_upload(service, payload)
    if tool_name == "dataset.profile":
        return service.profile(str(payload["dataset_id"]))
    if tool_name == "dataset.generate_domain_pack":
        return service.generate_domain_pack(
            str(payload["dataset_id"]),
            domain_name=payload.get("domain_name"),
            base_domain=payload.get("base_domain"),
            llm=str(payload.get("llm") or "off"),
        )
    if tool_name == "dataset.review_summary":
        return service.review_summary(str(payload["dataset_id"]))
    if tool_name == "dataset.approve_field":
        return service.approve_field(
            str(payload["dataset_id"]),
            str(payload["field_id"]),
            reviewed_by=_reviewed_by(actor_context),
            note=payload.get("note"),
        )
    if tool_name == "dataset.approve_op":
        return service.approve_op(
            str(payload["dataset_id"]),
            str(payload["field_id"]),
            str(payload["op"]),
            reviewed_by=_reviewed_by(actor_context),
            note=payload.get("note"),
        )
    if tool_name == "dataset.block_field":
        return service.block_field(
            str(payload["dataset_id"]),
            str(payload["field_id"]),
            reviewed_by=_reviewed_by(actor_context),
            note=payload.get("note"),
        )
    if tool_name == "dataset.approve_domain":
        return service.approve_domain(
            str(payload["dataset_id"]),
            title_field=payload.get("title_field"),
            primary_fields=list(payload.get("primary_fields") or []),
            sort_field=payload.get("sort_field"),
            default_safe_sort=bool(payload.get("default_safe_sort") or False),
            reviewed_by=_reviewed_by(actor_context),
            note=payload.get("note"),
        )
    if tool_name == "dataset.build_warehouse":
        return service.build_warehouse(str(payload["dataset_id"]))
    if tool_name == "workbench.query":
        return _tool_workbench_query(service, payload)
    if tool_name == "workbench.confirm":
        return _tool_workbench_confirm(service, payload)
    if tool_name == "evidence.get":
        return _tool_evidence_get(payload)
    if tool_name == "quality.run":
        return _tool_quality_run(payload)
    if tool_name == "pilot.run":
        return _tool_pilot_run(payload)
    raise ToolRegistryError(f"Unknown tool: {tool_name}")


def _tool_dataset_upload(
    service: DatasetService,
    payload: dict[str, Any],
) -> dict[str, Any]:
    filename = str(payload.get("filename") or "")
    source_path = payload.get("source_path")
    content_base64 = payload.get("content_base64")
    if source_path:
        path = Path(str(source_path))
        _reject_path_traversal(path)
        filename = filename or path.name
        content = path.read_bytes()
    elif content_base64:
        content = base64.b64decode(str(content_base64))
    else:
        raise ToolRegistryError("dataset.upload requires source_path or content_base64")
    return service.upload(
        filename=filename,
        content=content,
        dataset_id=payload.get("dataset_id"),
        sheet_name=payload.get("sheet_name"),
    )


def _tool_workbench_query(
    service: DatasetService,
    payload: dict[str, Any],
) -> dict[str, Any]:
    deterministic_fields = dict(payload.get("deterministic_fields") or {})
    natural_language = str(payload.get("natural_language") or "").strip()
    if not natural_language:
        raise ToolRegistryError("workbench.query requires natural_language")
    domain = payload.get("domain")
    confirmed = list(payload.get("confirmed_candidate_ids") or [])
    dataset_id = payload.get("dataset_id")
    if dataset_id:
        return service.query(
            str(dataset_id),
            user_input=natural_language,
            hard_filters=deterministic_fields,
            soft_preferences={"prompt": natural_language},
            extractor="regex",
            generator="template_evidence",
            confirmed_candidates=confirmed,
            domain_name=str(domain) if domain else None,
        )
    return run_workbench(
        WorkbenchConfig(
            user_input=natural_language,
            hard_filters=deterministic_fields,
            soft_preferences={"prompt": natural_language},
            extractor="regex",
            generator="template_evidence",
            confirmed_candidates=confirmed,
            domain_name=str(domain or "admissions"),
        )
    )


def _tool_workbench_confirm(
    service: DatasetService,
    payload: dict[str, Any],
) -> dict[str, Any]:
    previous_response = dict(payload.get("previous_response") or {})
    query = previous_response.get("query") or {}
    candidate_ids = list(payload.get("confirmed_candidate_ids") or [])
    if not previous_response or not candidate_ids:
        raise ToolRegistryError(
            "workbench.confirm requires previous_response and confirmed_candidate_ids"
        )
    natural_language = str(query.get("text") or "").strip()
    if not natural_language:
        raise ToolRegistryError("previous_response.query.text is required")
    request = {
        "dataset_id": payload.get("dataset_id") or query.get("dataset_id"),
        "domain": payload.get("domain") or previous_response.get("domain") or "admissions",
        "deterministic_fields": dict(query.get("hard_filters") or {}),
        "natural_language": natural_language,
        "confirmed_candidate_ids": candidate_ids,
    }
    return _tool_workbench_query(service, request)


def _tool_evidence_get(payload: dict[str, Any]) -> dict[str, Any]:
    response = dict(payload.get("workbench_response") or {})
    evidence = payload.get("evidence_pack")
    if evidence is None:
        evidence = response.get("evidence_pack") or {}
    return {"evidence_pack": _sanitize_evidence(evidence)}


def _tool_quality_run(payload: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(str(payload.get("output_dir") or "outputs/quality_gate"))
    _reject_path_traversal(output_dir)
    options = QualityGateOptions(
        fail_fast=bool(payload.get("fail_fast") or False),
        skip_frontend=bool(payload.get("skip_frontend") or False),
        skip_demo=bool(payload.get("skip_demo") or False),
        domains=list(payload.get("domains") or ["admissions", "housing", "products"]),
        output_dir=output_dir,
        json_only=False,
        strict=bool(payload.get("strict") or False),
    )
    return run_quality_gate(options)


def _tool_pilot_run(payload: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(str(payload.get("output_dir") or "outputs/real_dataset_pilot"))
    _reject_path_traversal(output_dir)
    if payload.get("fixture"):
        source_path = _fixture_path()
    elif payload.get("source_path"):
        source_path = Path(str(payload["source_path"]))
        _reject_path_traversal(source_path)
    else:
        raise ToolRegistryError("pilot.run requires source_path or fixture=true")
    report = run_pilot(
        source_path=source_path,
        sheet_name=payload.get("sheet_name"),
        output_dir=output_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(_pilot_json_ready(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _render_pilot_markdown(report),
        encoding="utf-8",
    )
    return report


def _load_contracts() -> dict[str, dict[str, Any]]:
    contracts = {}
    for path in sorted(TOOL_SCHEMA_DIR.glob("*.json")):
        contract = json.loads(path.read_text(encoding="utf-8"))
        name = contract.get("name")
        if not name:
            continue
        contracts[str(name)] = contract
    return contracts


def _public_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": contract["name"],
        "description": contract["description"],
        "permission_scope": contract["permission_scope"],
        "required_domain_status": contract.get("required_domain_status"),
        "executes_sql": bool(contract.get("executes_sql")),
        "writes_files": bool(contract.get("writes_files")),
        "llm_safe": bool(contract.get("llm_safe")),
        "status_enum": list(contract.get("status_enum") or []),
    }


def _enforce_permission(
    contract: dict[str, Any],
    actor_context: dict[str, Any],
) -> None:
    required = str(contract["permission_scope"])
    granted = set(actor_context.get("permission_scopes") or [])
    single = actor_context.get("permission_scope")
    if single:
        granted.add(str(single))
    if "*" in granted or required in granted:
        return
    raise ToolPermissionError(f"Tool requires permission_scope={required}")


def _validate_payload(contract: dict[str, Any], payload: dict[str, Any]) -> None:
    if Draft202012Validator is None:
        return
    validator = Draft202012Validator(contract["input_schema"])
    errors = sorted(validator.iter_errors(payload), key=lambda item: item.path)
    if errors:
        message = "; ".join(error.message for error in errors[:3])
        raise ToolRegistryError(f"Invalid payload for {contract['name']}: {message}")


def _reject_forbidden_input_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in FORBIDDEN_LLM_INPUT_FIELDS:
                raise ToolRegistryError(f"Forbidden LLM-safe input field: {key}")
            if str(key) in {"previous_response", "workbench_response", "evidence_pack"}:
                continue
            _reject_forbidden_input_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            _reject_forbidden_input_fields(item)


def _dataset_service(actor_context: dict[str, Any]) -> DatasetService:
    root = Path(str(actor_context.get("dataset_root") or "outputs/uploaded_datasets"))
    _reject_path_traversal(root)
    return DatasetService(root)


def _reviewed_by(actor_context: dict[str, Any]) -> str:
    return str(actor_context.get("actor_id") or "tool_reviewer")


def _write_audit_event(
    actor_context: dict[str, Any],
    invocation: ToolInvocation,
) -> None:
    audit_path = Path(actor_context.get("audit_path") or DEFAULT_AUDIT_PATH)
    _reject_path_traversal(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("", encoding="utf-8") if not audit_path.exists() else None
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(invocation.to_dict(), ensure_ascii=False) + "\n")


def _payload_dataset_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("dataset_id")
    return str(value) if value else None


def _sanitize_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if SECRET_KEY_PATTERN.search(str(key)):
                continue
            sanitized[str(key)] = _sanitize_evidence(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_evidence(item) for item in value]
    if isinstance(value, str):
        if SECRET_KEY_PATTERN.search(value):
            return "[redacted]"
        if ABSOLUTE_PATH_PATTERN.search(value):
            return "[redacted_path]"
    return value


def _sanitize_audit_value(value: Any) -> Any:
    if value is None:
        return None
    return _sanitize_evidence(value)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ToolPermissionError):
        return "permission_denied"
    if isinstance(exc, ToolRegistryError):
        return "invalid_tool_request"
    if isinstance(exc, DatasetServiceError):
        return exc.code
    return "tool_error"


def _reject_path_traversal(path: Path) -> None:
    if ".." in path.parts:
        raise ToolRegistryError("Path traversal is not allowed")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
