"""FastAPI entry point for the frontend workbench."""

from __future__ import annotations

import os
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from src.api.dataset_service import DatasetService, DatasetServiceError
from src.api.local_settings import llm_status, save_llm_settings
from src.api.preflight_store import PreflightStore, PreflightValidationError
from src.api.tool_registry import (
    TOOL_CONTRACT_VERSION,
    ToolPermissionError,
    ToolRegistryError,
    get_tool_schema,
    invoke_tool,
    list_tools as list_registered_tools,
)
from src.api.workbench import (
    DEFAULT_USER_INPUT,
    WORKBENCH_SCHEMA_VERSION,
    WorkbenchConfig,
    available_options,
    run_workbench,
)
from src.api.workbench_preflight import (
    WorkbenchPreflightConfig,
    preflight_input_signature,
)
from src.domains import DomainConfig


ROOT_DIR = Path(__file__).resolve().parents[2]
API_VERSION = "api.v1"
DATA_ROOT = Path(os.getenv("DATA_ROOT", "outputs/uploaded_datasets"))
OUTPUT_ROOT = Path(os.getenv("OUTPUT_ROOT", "outputs"))
DEFAULT_FRONTEND_USER_DIST = ROOT_DIR / "frontend-user" / "dist"
DEFAULT_FRONTEND_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
SENSITIVE_ERROR_PATTERN = re.compile(
    r"(secret|api[_-]?key|token|password|passwd|traceback|stack|\.env)",
    re.IGNORECASE,
)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(/Users/[^\s\"']+|/tmp/[^\s\"']+|/var/[^\s\"']+)"
)


class GenerateDomainPackRequest(BaseModel):
    """上传数据集生成 draft domain pack 的请求。"""

    domain_name: str | None = None
    base_domain: str | None = None
    template_id: str | None = None
    llm: str = "off"


class FieldReviewRequest(BaseModel):
    """字段 approve/block 请求。"""

    field_id: str
    reviewed_by: str = "api_reviewer"
    note: str | None = None


class OpReviewRequest(BaseModel):
    """字段 op approve 请求。"""

    field_id: str
    op: str
    reviewed_by: str = "api_reviewer"
    note: str | None = None


class ApproveDomainRequest(BaseModel):
    """domain approve 请求。"""

    title_field: str | None = None
    primary_fields: list[str] = Field(default_factory=list)
    sort_field: str | None = None
    default_safe_sort: bool = False
    reviewed_by: str = "api_reviewer"
    note: str | None = None


class WorkbenchQueryRequest(BaseModel):
    """统一 Workbench query 请求，支持 dataset_id 或内置 domain。"""

    dataset_id: str | None = None
    domain_name: str = "admissions"
    user_input: str = Field(default=DEFAULT_USER_INPUT, min_length=1)
    hard_filters: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)
    extractor: str = "regex"
    generator: str = "template_evidence"
    model: str = ""
    planner_mode: str = "auto"
    confirmed_candidates: list[str] = Field(default_factory=list)
    preflight_id: str | None = None
    confirmed_boundaries: list["PreflightBoundarySelection"] = Field(
        default_factory=list
    )
    disabled_boundaries: list["PreflightBoundarySelection"] = Field(
        default_factory=list
    )


class WorkbenchPreflightRequest(BaseModel):
    """uploaded admissions 查询前检查请求。"""

    dataset_id: str
    domain_name: str = "admissions"
    user_input: str = Field(min_length=1)
    hard_filters: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)
    model: str = ""
    planner_mode: str = "llm_semantic"


class PreflightBoundarySelection(BaseModel):
    """用户对查询前检查确认项的受控选择。"""

    confirmation_id: str
    option_id: str = "do_not_use"


class ToolInvokeRequest(BaseModel):
    """通用 tool invoke 请求。"""

    payload: dict[str, Any] = Field(default_factory=dict)
    actor_context: dict[str, Any] = Field(default_factory=dict)


class LLMSettingsRequest(BaseModel):
    """本机 LLM 设置请求。"""

    enabled: bool = False
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_url: str = "https://api.deepseek.com/chat/completions"
    api_key: str | None = None


def _frontend_origins() -> list[str]:
    configured = os.getenv("FRONTEND_ORIGIN")
    if not configured:
        return DEFAULT_FRONTEND_ORIGINS
    return [
        origin.strip()
        for origin in configured.split(",")
        if origin.strip()
    ] or DEFAULT_FRONTEND_ORIGINS


app = FastAPI(title="Preference-to-Rule Workbench API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
dataset_service = DatasetService(DATA_ROOT)
preflight_store = PreflightStore()


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple health signal."""

    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Kubernetes-style liveness probe。"""

    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    """检查发布运行所需的基础依赖。"""

    checks = [
        _check_data_root_writable(),
        _check_tool_schemas(),
        _check_domain_configs(),
        _check_quality_gate_dependencies(),
    ]
    return {
        "status": "ok" if all(check["ok"] for check in checks) else "error",
        "checks": checks,
    }


@app.get("/version")
def version() -> dict[str, str]:
    """返回 API、response contract 和 tool contract 版本。"""

    return {
        "git_commit": _git_commit(),
        "schema_version": WORKBENCH_SCHEMA_VERSION,
        "api_version": API_VERSION,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "distribution_mode": _distribution_mode(),
    }


@app.get("/api/workbench/options")
def options() -> dict[str, object]:
    """Return API-mode user option whitelists."""

    return available_options()


@app.get("/settings/llm")
def get_llm_settings(request: Request) -> dict[str, Any]:
    """返回本机 LLM 配置状态，不返回密钥明文。"""

    _ensure_scope(_actor_context_from_request(request), "read_only")
    return llm_status()


@app.post("/settings/llm")
async def update_llm_settings(http_request: Request) -> dict[str, Any]:
    """保存本机 LLM 配置，不把密钥回显给前端。"""

    _ensure_scope(_actor_context_from_request(http_request), "diagnostics")
    try:
        payload = await http_request.json()
        request = LLMSettingsRequest.model_validate(payload)
        return save_llm_settings(request.model_dump())
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_llm_settings",
                "message": "LLM 设置请求无效",
            },
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_llm_settings", "message": str(exc)},
        ) from exc


@app.get("/datasets")
def list_datasets(request: Request) -> dict[str, object]:
    """列出本机托管数据源。"""

    try:
        _ensure_scope(_actor_context_from_request(request), "read_only")
        return dataset_service.list_datasets()
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/upload")
async def upload_dataset(
    request: Request,
    filename: str = Query(..., min_length=1),
    dataset_id: str | None = Query(default=None),
    sheet_name: str | None = Query(default=None),
) -> dict[str, object]:
    """上传 CSV/Excel 到托管数据目录。"""

    try:
        _ensure_scope(_actor_context_from_request(request), "dataset_write")
        content = await request.body()
        return dataset_service.upload(
            filename=filename,
            content=content,
            dataset_id=dataset_id,
            sheet_name=sheet_name,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/generate-domain-pack")
def generate_dataset_domain_pack(
    dataset_id: str,
    request: GenerateDomainPackRequest,
    http_request: Request,
) -> dict[str, object]:
    """为上传数据集生成 draft domain pack。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "dataset_write")
        _reject_user_upload_only_domain_template(request)
        return dataset_service.generate_domain_pack(
            dataset_id,
            domain_name=request.domain_name,
            base_domain=request.base_domain,
            template_id=request.template_id,
            llm=request.llm,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.get("/datasets/{dataset_id}/profile")
def dataset_profile(dataset_id: str, request: Request) -> dict[str, object]:
    """返回 schema profile。"""

    try:
        _ensure_scope(_actor_context_from_request(request), "read_only")
        return dataset_service.profile(dataset_id)
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.get("/datasets/{dataset_id}/review-summary")
def dataset_review_summary(dataset_id: str, request: Request) -> dict[str, object]:
    """返回 domain pack review 摘要。"""

    try:
        _ensure_scope(_actor_context_from_request(request), "read_only")
        return dataset_service.review_summary(dataset_id)
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/approve-field")
def dataset_approve_field(
    dataset_id: str,
    request: FieldReviewRequest,
    http_request: Request,
) -> dict[str, object]:
    """批准字段进入可执行审查范围。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "review_admin")
        return dataset_service.approve_field(
            dataset_id,
            request.field_id,
            reviewed_by=request.reviewed_by,
            note=request.note,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/approve-op")
def dataset_approve_op(
    dataset_id: str,
    request: OpReviewRequest,
    http_request: Request,
) -> dict[str, object]:
    """批准字段的单个 op。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "review_admin")
        return dataset_service.approve_op(
            dataset_id,
            request.field_id,
            request.op,
            reviewed_by=request.reviewed_by,
            note=request.note,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/block-field")
def dataset_block_field(
    dataset_id: str,
    request: FieldReviewRequest,
    http_request: Request,
) -> dict[str, object]:
    """阻断字段执行。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "review_admin")
        return dataset_service.block_field(
            dataset_id,
            request.field_id,
            reviewed_by=request.reviewed_by,
            note=request.note,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/approve-domain")
def dataset_approve_domain(
    dataset_id: str,
    request: ApproveDomainRequest,
    http_request: Request,
) -> dict[str, object]:
    """批准整个 uploaded domain pack。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "review_admin")
        return dataset_service.approve_domain(
            dataset_id,
            title_field=request.title_field,
            primary_fields=request.primary_fields,
            sort_field=request.sort_field,
            default_safe_sort=request.default_safe_sort,
            reviewed_by=request.reviewed_by,
            note=request.note,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/build-warehouse")
def dataset_build_warehouse(dataset_id: str, request: Request) -> dict[str, object]:
    """为 approved uploaded domain pack 构建 DuckDB warehouse。"""

    try:
        _ensure_scope(_actor_context_from_request(request), "warehouse_admin")
        return dataset_service.build_warehouse(dataset_id)
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/workbench/preflight")
def preflight_workbench(
    request: WorkbenchPreflightRequest,
    http_request: Request,
) -> dict[str, object]:
    """uploaded dataset 查询前检查，不执行 SQL。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "query")
        response = dataset_service.preflight(
            request.dataset_id,
            user_input=request.user_input.strip(),
            hard_filters=request.hard_filters,
            soft_preferences=request.soft_preferences,
            model=request.model,
            planner_mode=request.planner_mode,
            domain_name=request.domain_name,
        )
        if response.get("status") in {"ready", "needs_confirmation"}:
            preflight_store.put(response)
        return response
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/workbench/query")
def query_workbench(
    request: WorkbenchQueryRequest,
    http_request: Request,
) -> dict[str, object]:
    """统一查询入口，支持内置 domain 或 uploaded dataset。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "query")
        if request.dataset_id:
            hard_filters, soft_preferences = _query_filters_after_preflight(request)
            return dataset_service.query(
                request.dataset_id,
                user_input=request.user_input.strip(),
                hard_filters=hard_filters,
                soft_preferences=soft_preferences,
                extractor=request.extractor,
                generator=request.generator,
                model=request.model,
                planner_mode=request.planner_mode,
                confirmed_candidates=request.confirmed_candidates,
                domain_name=request.domain_name,
            )
        if _user_upload_only_mode():
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "dataset_id_required",
                    "message": "本地用户模式必须选择一个已上传数据源。",
                },
            )
        return run_workbench(
            WorkbenchConfig(
                user_input=request.user_input.strip(),
                hard_filters=request.hard_filters,
                soft_preferences=request.soft_preferences,
                extractor=request.extractor,
                generator=request.generator,
                model=request.model,
                planner_mode=request.planner_mode,
                confirmed_candidates=request.confirmed_candidates,
                domain_name=request.domain_name,
            )
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc
    except PreflightValidationError as exc:
        raise _invalid_preflight_http_error(exc.message) from exc


def _query_filters_after_preflight(
    request: WorkbenchQueryRequest,
) -> tuple[dict[str, Any], dict[str, Any]]:
    hard_filters = dict(request.hard_filters)
    soft_preferences = dict(request.soft_preferences)
    has_selection = bool(request.confirmed_boundaries or request.disabled_boundaries)
    if not request.preflight_id:
        if has_selection:
            raise PreflightValidationError("确认项必须引用系统生成的 preflight_id。")
        return hard_filters, soft_preferences

    patches = preflight_store.validate(
        preflight_id=request.preflight_id,
        input_signature=_query_preflight_signature(request),
        dataset_id=str(request.dataset_id or ""),
        domain_name=request.domain_name,
        confirmed=_selection_dicts(request.confirmed_boundaries),
        disabled=_selection_dicts(request.disabled_boundaries),
    )
    return _merge_preflight_patches(hard_filters, soft_preferences, patches)


def _query_preflight_signature(request: WorkbenchQueryRequest) -> str:
    return preflight_input_signature(
        WorkbenchPreflightConfig(
            user_input=request.user_input.strip(),
            hard_filters=dict(request.hard_filters),
            soft_preferences={
                "prompt": request.user_input.strip(),
                **dict(request.soft_preferences),
            },
            model=request.model,
            planner_mode=request.planner_mode,
            domain_name=request.domain_name,
            dataset_id=request.dataset_id,
        )
    )


def _selection_dicts(
    selections: list[PreflightBoundarySelection],
) -> list[dict[str, Any]]:
    return [selection.model_dump() for selection in selections]


def _merge_preflight_patches(
    hard_filters: dict[str, Any],
    soft_preferences: dict[str, Any],
    patches: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged_hard = dict(hard_filters)
    merged_soft = dict(soft_preferences)
    for patch in patches:
        hard_patch = patch.get("hard_filters")
        if isinstance(hard_patch, dict):
            merged_hard.update(hard_patch)
        soft_patch = patch.get("soft_preferences")
        if isinstance(soft_patch, dict):
            merged_soft.update(soft_patch)
    return merged_hard, merged_soft


@app.get("/tools/list")
def tools_list(
    request: Request,
    permission_scope: str | None = Query(default=None),
    llm_safe_only: bool = Query(default=False),
) -> dict[str, Any]:
    """列出当前 actor 可见的 tool contracts。"""

    actor_context = _actor_context_from_request(request)
    tools = list_registered_tools(
        permission_scope=permission_scope,
        llm_safe_only=llm_safe_only,
    )
    return {
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "tools": _filter_tools_for_actor(tools, actor_context, llm_safe_only),
    }


@app.get("/tools/{tool_name}/schema")
def tool_schema(tool_name: str) -> dict[str, Any]:
    """返回单个 tool 的 JSON contract。"""

    try:
        return get_tool_schema(tool_name)
    except ToolRegistryError as exc:
        raise _tool_http_error(exc) from exc


@app.post("/tools/{tool_name}/invoke")
def tool_invoke(
    tool_name: str,
    request: ToolInvokeRequest,
    http_request: Request,
) -> dict[str, Any]:
    """通过 ToolRegistry 调用 tool，不复制业务逻辑。"""

    actor_context = _actor_context_from_request(http_request, request.actor_context)
    try:
        return invoke_tool(tool_name, request.payload, actor_context)
    except (ToolPermissionError, ToolRegistryError, DatasetServiceError) as exc:
        raise _tool_http_error(exc) from exc
    except Exception as exc:  # noqa: BLE001 - API 边界统一净化未知异常。
        raise _tool_http_error(exc) from exc


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    """返回本地用户 Web 首页。"""

    response = _frontend_file_response("")
    _set_local_user_auth_cookie(response)
    return response


@app.get("/assets/{full_path:path}", include_in_schema=False)
def frontend_asset(full_path: str) -> FileResponse:
    """返回本地用户 Web 构建资源。"""

    return _frontend_file_response(f"assets/{full_path}")


def _dataset_http_error(exc: DatasetServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details or {},
        },
    )


def _reject_user_upload_only_domain_template(
    request: GenerateDomainPackRequest,
) -> None:
    if not _user_upload_only_mode():
        return
    if request.base_domain or request.template_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "domain_template_unavailable",
                "message": "本地用户模式不复用内置领域模板。",
            },
        )


def _distribution_mode() -> str:
    return os.getenv("APP_DISTRIBUTION_MODE", "development")


def _user_upload_only_mode() -> bool:
    return _distribution_mode() == "user_upload_only"


def _invalid_preflight_http_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "invalid_preflight", "message": message},
    )


def _frontend_file_response(full_path: str) -> FileResponse:
    dist_dir = Path(
        os.getenv("FRONTEND_USER_DIST", str(DEFAULT_FRONTEND_USER_DIST))
    ).resolve()
    index_path = (dist_dir / "index.html").resolve()
    if not index_path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "frontend_not_built",
                "message": "本地用户 Web 尚未构建，请先运行 frontend-user build。",
            },
        )
    if full_path:
        requested_path = (dist_dir / full_path).resolve()
        try:
            requested_path.relative_to(dist_dir)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found") from None
        if requested_path.is_file():
            return FileResponse(requested_path)
        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(index_path)


def _set_local_user_auth_cookie(response: FileResponse) -> None:
    token = os.getenv("LOCAL_USER_AUTO_AUTH_TOKEN", "").strip()
    if not token or token not in _auth_token_map():
        return
    response.set_cookie(
        key="actor_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _tool_http_error(exc: Exception) -> HTTPException:
    status_code = 500
    code = "tool_error"
    if isinstance(exc, ToolPermissionError):
        status_code = 403
        code = "permission_denied"
    elif isinstance(exc, ToolRegistryError):
        status_code = 400
        code = "invalid_tool_request"
    elif isinstance(exc, DatasetServiceError):
        status_code = exc.status_code
        code = exc.code
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": _sanitize_error_message(str(exc)),
            "details": {},
        },
    )


def _actor_context_from_request(
    request: Request,
    body_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = body_context
    actor = _authenticated_actor(request)
    return {
        "actor_id": actor["actor_id"],
        "permission_scopes": actor["permission_scopes"],
        "dataset_root": str(DATA_ROOT),
        "audit_path": os.getenv(
            "TOOL_AUDIT_LOG_PATH",
            str(OUTPUT_ROOT / "tool_audit/audit.jsonl"),
        ),
    }


def _authenticated_actor(request: Request) -> dict[str, Any]:
    """只从服务端配置的 token 映射中派生 actor 和权限。"""

    token = _request_token(request)
    actors = _auth_token_map()
    if not token or token not in actors:
        return {"actor_id": "anonymous", "permission_scopes": []}
    record = actors[token]
    return {
        "actor_id": _safe_actor_id(record.get("actor_id") or "api_client"),
        "permission_scopes": _safe_scopes(record.get("permission_scopes") or []),
    }


def _request_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    token = request.headers.get("X-Actor-Token") or request.cookies.get("actor_token")
    return token.strip() if token and token.strip() else None


def _auth_token_map() -> dict[str, dict[str, Any]]:
    raw = os.getenv("AUTH_TOKENS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    actors: dict[str, dict[str, Any]] = {}
    for token, record in parsed.items():
        if not isinstance(token, str) or not token:
            continue
        if isinstance(record, list):
            actors[token] = {
                "actor_id": "api_client",
                "permission_scopes": record,
            }
        elif isinstance(record, dict):
            actors[token] = dict(record)
    return actors


def _safe_actor_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.@-]+", "_", str(value or "api_client")).strip("_")
    return text[:80] or "api_client"


def _safe_scopes(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)
        except TypeError:
            raw_values = []
    return sorted(
        {
            str(value).strip()
            for value in raw_values
            if str(value).strip()
        }
    )


def _ensure_scope(actor_context: dict[str, Any], required_scope: str) -> None:
    granted = _granted_scopes(actor_context, llm_safe_only=False)
    if "*" in granted or required_scope in granted:
        return
    raise _tool_http_error(
        ToolPermissionError(f"Tool requires permission_scope={required_scope}")
    )


def _filter_tools_for_actor(
    tools: list[dict[str, Any]],
    actor_context: dict[str, Any],
    llm_safe_only: bool,
) -> list[dict[str, Any]]:
    granted = _granted_scopes(actor_context, llm_safe_only=llm_safe_only)
    if "*" in granted:
        return tools
    return [
        tool
        for tool in tools
        if tool.get("permission_scope") in granted
    ]


def _granted_scopes(
    actor_context: dict[str, Any],
    *,
    llm_safe_only: bool,
) -> set[str]:
    granted = set(actor_context.get("permission_scopes") or [])
    if actor_context.get("permission_scope"):
        granted.add(str(actor_context["permission_scope"]))
    if not granted and llm_safe_only:
        return {"read_only", "query", "confirm"}
    return granted


def _check_data_root_writable() -> dict[str, Any]:
    try:
        root = DATA_ROOT
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".readyz_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"name": "data_root_writable", "ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"name": "data_root_writable", "ok": False, "message": str(exc)}


def _check_tool_schemas() -> dict[str, Any]:
    try:
        tools = list_registered_tools()
        return {"name": "tool_schemas", "ok": bool(tools), "count": len(tools)}
    except Exception as exc:  # noqa: BLE001
        return {"name": "tool_schemas", "ok": False, "message": str(exc)}


def _check_domain_configs() -> dict[str, Any]:
    if _user_upload_only_mode():
        return {
            "name": "domain_configs",
            "ok": True,
            "skipped": True,
            "reason": "user_upload_only",
        }
    failures = []
    for domain in ["admissions", "housing", "products"]:
        try:
            DomainConfig.load(domain)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{domain}: {_sanitize_error_message(str(exc))}")
    return {
        "name": "domain_configs",
        "ok": not failures,
        "domains": ["admissions", "housing", "products"],
        "failures": failures,
    }


def _check_quality_gate_dependencies() -> dict[str, Any]:
    if _user_upload_only_mode():
        return {
            "name": "quality_gate_dependencies",
            "ok": True,
            "skipped": True,
            "reason": "user_upload_only",
        }
    python_path = ROOT_DIR / ".venv/bin/python"
    script_path = ROOT_DIR / "scripts/run_quality_gate.py"
    return {
        "name": "quality_gate_dependencies",
        "ok": python_path.exists() and script_path.exists(),
        "python": ".venv/bin/python",
        "script": "scripts/run_quality_gate.py",
    }


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() or "unknown"


def _sanitize_error_message(message: str) -> str:
    if SENSITIVE_ERROR_PATTERN.search(message):
        return "[redacted]"
    return ABSOLUTE_PATH_PATTERN.sub("[redacted_path]", message)
