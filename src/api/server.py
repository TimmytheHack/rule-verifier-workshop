"""FastAPI entry point for the frontend workbench."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api.dataset_service import DatasetService, DatasetServiceError
from src.api.workbench import (
    DEFAULT_USER_INPUT,
    WorkbenchConfig,
    available_options,
    run_workbench,
)


class HardFiltersRequest(BaseModel):
    """Structured facts that may become deterministic rules after verification."""

    source_province: str | None = "广东"
    subject_type: str | None = "物理"
    reselected_subjects: list[str] = Field(default_factory=lambda: ["化学", "生物"])
    user_rank: int | None = 32000
    major_keyword: str | None = None
    preferred_cities: list[str] = Field(default_factory=list)
    tuition_cap_yuan: int | None = None


class SoftPreferencesRequest(BaseModel):
    """Soft preferences that stay candidate/not-executed until verified."""

    prompt: str | None = "想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"
    safety_margin_percent: int | None = None
    tuition_cap_yuan: int | None = None


class WorkbenchRunRequest(BaseModel):
    """Request body for a workbench pipeline run."""

    user_input: str = Field(default=DEFAULT_USER_INPUT, min_length=1)
    hard_filters: HardFiltersRequest = Field(default_factory=HardFiltersRequest)
    soft_preferences: SoftPreferencesRequest = Field(default_factory=SoftPreferencesRequest)
    extractor: str = "hybrid"
    generator: str = "template_evidence"
    model: str = "deepseek-v4-flash"
    confirmed_candidates: list[str] = Field(default_factory=list)
    domain_name: str = "admissions"
    domain_path: str | None = None
    dataset_id: str | None = None


class GenerateDomainPackRequest(BaseModel):
    """上传数据集生成 draft domain pack 的请求。"""

    domain_name: str | None = None
    base_domain: str | None = None
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
    model: str = "deepseek-v4-flash"
    confirmed_candidates: list[str] = Field(default_factory=list)


app = FastAPI(title="Preference-to-Rule Workbench API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
dataset_service = DatasetService()


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple health signal."""

    return {"status": "ok"}


@app.get("/api/workbench/options")
def options() -> dict[str, object]:
    """Return API-mode user option whitelists."""

    return available_options()


@app.post("/api/workbench/run")
def run(request: WorkbenchRunRequest) -> dict[str, object]:
    """Run the workbench pipeline with controlled frontend options."""

    config = WorkbenchConfig(
        user_input=request.user_input.strip(),
        hard_filters=request.hard_filters.dict(),
        soft_preferences=request.soft_preferences.dict(),
        extractor=request.extractor,
        generator=request.generator,
        model=request.model,
        confirmed_candidates=request.confirmed_candidates,
        domain_name=request.domain_name,
        domain_path=request.domain_path,
        dataset_id=request.dataset_id,
    )
    return run_workbench(config)


@app.post("/datasets/upload")
async def upload_dataset(
    request: Request,
    filename: str = Query(..., min_length=1),
    dataset_id: str | None = Query(default=None),
    sheet_name: str | None = Query(default=None),
) -> dict[str, object]:
    """上传 CSV/Excel 到托管数据目录。"""

    try:
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
) -> dict[str, object]:
    """为上传数据集生成 draft domain pack。"""

    try:
        return dataset_service.generate_domain_pack(
            dataset_id,
            domain_name=request.domain_name,
            base_domain=request.base_domain,
            llm=request.llm,
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.get("/datasets/{dataset_id}/profile")
def dataset_profile(dataset_id: str) -> dict[str, object]:
    """返回 schema profile。"""

    try:
        return dataset_service.profile(dataset_id)
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.get("/datasets/{dataset_id}/review-summary")
def dataset_review_summary(dataset_id: str) -> dict[str, object]:
    """返回 domain pack review 摘要。"""

    try:
        return dataset_service.review_summary(dataset_id)
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/datasets/{dataset_id}/approve-field")
def dataset_approve_field(
    dataset_id: str,
    request: FieldReviewRequest,
) -> dict[str, object]:
    """批准字段进入可执行审查范围。"""

    try:
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
) -> dict[str, object]:
    """批准字段的单个 op。"""

    try:
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
) -> dict[str, object]:
    """阻断字段执行。"""

    try:
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
) -> dict[str, object]:
    """批准整个 uploaded domain pack。"""

    try:
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
def dataset_build_warehouse(dataset_id: str) -> dict[str, object]:
    """为 approved uploaded domain pack 构建 DuckDB warehouse。"""

    try:
        return dataset_service.build_warehouse(dataset_id)
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


@app.post("/workbench/query")
def query_workbench(request: WorkbenchQueryRequest) -> dict[str, object]:
    """统一查询入口，支持内置 domain 或 uploaded dataset。"""

    try:
        if request.dataset_id:
            return dataset_service.query(
                request.dataset_id,
                user_input=request.user_input.strip(),
                hard_filters=request.hard_filters,
                soft_preferences=request.soft_preferences,
                extractor=request.extractor,
                generator=request.generator,
                model=request.model,
                confirmed_candidates=request.confirmed_candidates,
                domain_name=request.domain_name,
            )
        return run_workbench(
            WorkbenchConfig(
                user_input=request.user_input.strip(),
                hard_filters=request.hard_filters,
                soft_preferences=request.soft_preferences,
                extractor=request.extractor,
                generator=request.generator,
                model=request.model,
                confirmed_candidates=request.confirmed_candidates,
                domain_name=request.domain_name,
            )
        )
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc


def _dataset_http_error(exc: DatasetServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details or {},
        },
    )
