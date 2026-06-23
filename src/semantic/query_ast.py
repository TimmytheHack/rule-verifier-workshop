from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


FORBIDDEN_SQL_PAYLOAD_KEYS = ("raw_sql", "sql")


def _reject_raw_sql_key(value: Any, context: str) -> Any:
    if isinstance(value, dict):
        forbidden_keys = [key for key in FORBIDDEN_SQL_PAYLOAD_KEYS if key in value]
        if forbidden_keys:
            raise ValueError(f"{context} 不能包含 {'、'.join(forbidden_keys)}。")
        for nested_value in value.values():
            _reject_raw_sql_key(nested_value, context)
    elif isinstance(value, list):
        for nested_value in value:
            _reject_raw_sql_key(nested_value, context)
    return value


class QueryFilter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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

    @field_validator("value")
    @classmethod
    def _reject_raw_sql_value(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "value")


class QuerySort(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: str = "table_filter"
    select: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[QuerySort] = Field(default_factory=list)
    limit: int = 30
    requested_output: list[str] = Field(default_factory=list)
    source: str = "candidate"

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


class QueryVerificationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str
    field_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def _reject_reserved_detail_keys(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        reserved_keys = {"code", "severity", "message", "field_id"}
        conflicts = reserved_keys.intersection(value)
        if conflicts:
            raise ValueError("details 不能覆盖标准字段。")
        return _reject_raw_sql_key(value, "details")

    def to_dict(self) -> dict[str, Any]:
        serialized = self.model_dump(exclude={"details"}, exclude_none=True)
        serialized.update(self.details)
        return serialized


class VerifiedQueryPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: str
    table_name: str
    select_columns: list[dict[str, str]]
    filters: list[dict[str, Any]]
    sort: list[dict[str, str]]
    limit: int
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]

    @field_validator("table_name")
    @classmethod
    def _require_non_empty_table_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("table_name 不能为空。")
        return normalized

    @field_validator("limit")
    @classmethod
    def _clamp_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit 必须为正整数。")
        return min(value, 100)

    @field_validator("answerable_intents", "unanswerable_intents")
    @classmethod
    def _reject_raw_sql_intent_records(
        cls, value: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        for record in value:
            _reject_raw_sql_key(record, "intent 记录")
        return value

    @staticmethod
    def _require_exact_record_keys(
        record: dict[str, Any], allowed_keys: set[str], record_name: str
    ) -> None:
        if set(record) != allowed_keys:
            raise ValueError(f"{record_name} 字段集合不正确。")

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
            allowed_keys = {"field_id", "source_column"}
            cls._require_exact_record_keys(record, allowed_keys, "select_columns")
            normalized.append(
                {
                    "field_id": cls._require_record_text(
                        record, "field_id", "select_columns"
                    ),
                    "source_column": cls._require_record_text(
                        record, "source_column", "select_columns"
                    ),
                }
            )
        return normalized

    @field_validator("filters")
    @classmethod
    def _validate_filters(
        cls, value: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        normalized = []
        for record in value:
            allowed_keys = {"field_id", "source_column", "op", "value"}
            cls._require_exact_record_keys(record, allowed_keys, "filters")
            normalized.append(
                {
                    "field_id": cls._require_record_text(
                        record, "field_id", "filters"
                    ),
                    "source_column": cls._require_record_text(
                        record, "source_column", "filters"
                    ),
                    "op": cls._require_record_text(record, "op", "filters"),
                    "value": _reject_raw_sql_key(
                        record["value"], "filters.value"
                    ),
                }
            )
        return normalized

    @field_validator("sort")
    @classmethod
    def _validate_sort(
        cls, value: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        normalized = []
        for record in value:
            allowed_keys = {"field_id", "source_column", "direction"}
            cls._require_exact_record_keys(record, allowed_keys, "sort")
            direction = cls._require_record_text(record, "direction", "sort")
            direction = direction.lower()
            if direction not in {"asc", "desc"}:
                raise ValueError("sort.direction 必须是 asc 或 desc。")
            normalized.append(
                {
                    "field_id": cls._require_record_text(
                        record, "field_id", "sort"
                    ),
                    "source_column": cls._require_record_text(
                        record, "source_column", "sort"
                    ),
                    "direction": direction,
                }
            )
        return normalized
