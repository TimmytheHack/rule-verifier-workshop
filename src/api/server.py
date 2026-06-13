"""FastAPI entry point for the frontend workbench."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    )
    return run_workbench(config)
