from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.semantic.query_ast import _reject_raw_sql_key


QueryType = Literal[
    "semantic_recommendation",
    "admissions_major_rank",
    "group_detail_report",
    "unknown",
]


class SemanticUserContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_rank: int | None = None
    user_score: int | None = None
    source_province: str | None = None
    subject_type: str | None = None
    reselected_subjects: list[str] = Field(default_factory=list)

    @field_validator("user_rank", "user_score")
    @classmethod
    def _positive_number(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("数值必须为正整数。")
        return value

    @field_validator("reselected_subjects")
    @classmethod
    def _clean_subjects(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in output:
                output.append(text)
        return output[:2]


class SemanticPreference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_text: str
    semantic: str
    op: str
    value: Any
    confidence: float = 1.0
    reason: str | None = None

    @field_validator("source_text", "semantic", "op")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("文本字段不能为空。")
        return text

    @field_validator("value")
    @classmethod
    def _reject_raw_sql(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "semantic preference value")


class SemanticIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_type: QueryType
    user_context: SemanticUserContext = Field(default_factory=SemanticUserContext)
    preferences: list[SemanticPreference] = Field(default_factory=list)
    requested_output: list[str] = Field(default_factory=list)
    source_language: str = "zh-CN"

    @field_validator("requested_output")
    @classmethod
    def _clean_requested_output(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in output:
                output.append(text)
        return output


class IntentExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: SemanticIntent
    provider: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("raw_payload", "warnings")
    @classmethod
    def _reject_raw_sql_records(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "intent extraction record")
