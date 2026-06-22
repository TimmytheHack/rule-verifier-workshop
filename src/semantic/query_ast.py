from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QueryFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_id: str
    op: str
    value: Any

    @field_validator("field_id", "op")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空。")
        return normalized


class QuerySort(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_id: str
    direction: str = "asc"

    @field_validator("field_id")
    @classmethod
    def _require_non_empty_field_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空。")
        return normalized

    @field_validator("direction")
    @classmethod
    def _normalize_direction(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"asc", "desc"}:
            raise ValueError("排序方向必须是 asc 或 desc。")
        return normalized


class QueryAST(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str = "table_filter"
    select: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[QuerySort] = Field(default_factory=list)
    limit: int = 30
    requested_output: list[str] = Field(default_factory=list)
    source: str = "candidate"
    raw_sql: str | None = Field(default=None, exclude=True)

    @classmethod
    def from_candidate(cls, candidate: Any) -> "QueryAST":
        return cls.model_validate(candidate)

    @field_validator("intent", "source")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空。")
        return normalized

    @field_validator("select", "requested_output")
    @classmethod
    def _normalize_text_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("limit")
    @classmethod
    def _clamp_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit 必须为正整数。")
        return min(value, 100)

    @model_validator(mode="after")
    def _reject_raw_sql(self) -> "QueryAST":
        if self.raw_sql is not None:
            raise ValueError("raw_sql 不允许作为 QueryAST 候选结构。")
        return self


class QueryVerificationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str
    field_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        serialized = self.model_dump(exclude={"details"}, exclude_none=True)
        serialized.update(self.details)
        return serialized


class VerifiedQueryPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str
    table_name: str
    select_columns: list[dict[str, str]]
    filters: list[dict[str, Any]]
    sort: list[dict[str, str]]
    limit: int
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]

    @staticmethod
    def _require_record_text(
        record: dict[str, Any], key: str, record_name: str
    ) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{record_name}.{key} 不能为空。")
        return value.strip()

    @field_validator("select_columns")
    @classmethod
    def _validate_select_columns(
        cls, value: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        normalized = []
        for record in value:
            copied = dict(record)
            copied["field_id"] = cls._require_record_text(
                copied, "field_id", "select_columns"
            )
            copied["source_column"] = cls._require_record_text(
                copied, "source_column", "select_columns"
            )
            normalized.append(copied)
        return normalized

    @field_validator("filters")
    @classmethod
    def _validate_filters(
        cls, value: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        normalized = []
        for record in value:
            copied = dict(record)
            copied["field_id"] = cls._require_record_text(
                copied, "field_id", "filters"
            )
            copied["source_column"] = cls._require_record_text(
                copied, "source_column", "filters"
            )
            copied["op"] = cls._require_record_text(copied, "op", "filters")
            normalized.append(copied)
        return normalized

    @field_validator("sort")
    @classmethod
    def _validate_sort(
        cls, value: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        normalized = []
        for record in value:
            copied = dict(record)
            copied["field_id"] = cls._require_record_text(
                copied, "field_id", "sort"
            )
            copied["source_column"] = cls._require_record_text(
                copied, "source_column", "sort"
            )
            direction = cls._require_record_text(copied, "direction", "sort")
            direction = direction.lower()
            if direction not in {"asc", "desc"}:
                raise ValueError("sort.direction 必须是 asc 或 desc。")
            copied["direction"] = direction
            normalized.append(copied)
        return normalized
