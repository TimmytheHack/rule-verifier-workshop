from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.semantic.query_ast import _reject_raw_sql_key


RankingOperation = Literal[
    "text_match",
    "equals_preferred_value",
    "in_preferred_set",
    "numeric_distance_to_user_value",
    "numeric_higher_is_better",
    "numeric_lower_is_better",
    "boolean_preferred_value",
    "missing_value_penalty",
]

ALLOWED_RANKING_OPERATIONS = frozenset(RankingOperation.__args__)
BOOLEAN_STRING_VALUES = frozenset({"是", "否", "true", "false", "1", "0"})
SQL_COMMAND_TEXT_PATTERN = re.compile(
    r"\b("
    r"select\s+.+\s+from|"
    r"select\s+(?:\*|\d+|'[^']*'|\"[^\"]*\"|[A-Za-z_][\w.]*)\s*;?(?:$|\s+from\b)|"
    r"insert\s+into|"
    r"update\s+\S+\s+set|"
    r"delete\s+from|"
    r"drop\s+(table|database|view|index)|"
    r"alter\s+(table|database|view)|"
    r"create\s+(table|database|view|index)"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)


class RankingCriterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str
    source_text: str
    required_field: str
    operation: str
    value: Any = None
    priority: int
    direction: str = "desc"
    rationale: str

    @model_validator(mode="before")
    @classmethod
    def _reject_raw_sql_payload(cls, value: Any) -> Any:
        _reject_raw_sql_key(value, "ranking criterion")
        return _reject_sql_command_text(value, "ranking criterion")

    @field_validator(
        "criterion_id",
        "source_text",
        "required_field",
        "operation",
        "rationale",
    )
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空。")
        return normalized

    @field_validator("direction")
    @classmethod
    def _normalize_direction(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"asc", "desc"}:
            raise ValueError("direction 必须是 asc 或 desc。")
        return normalized

    @field_validator("priority")
    @classmethod
    def _require_positive_priority(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("priority 必须为正整数。")
        return value

    @model_validator(mode="after")
    def _validate_operation_value(self) -> "RankingCriterion":
        if self.operation not in ALLOWED_RANKING_OPERATIONS:
            return self

        value = self.value
        if self.operation == "text_match":
            if not _is_non_empty_string_list(value):
                raise ValueError("text_match 的 value 必须是非空字符串列表。")
        elif self.operation == "equals_preferred_value":
            if not _is_scalar_value(value):
                raise ValueError("equals_preferred_value 的 value 必须是标量。")
        elif self.operation == "in_preferred_set":
            if not _is_non_empty_scalar_list(value):
                raise ValueError("in_preferred_set 的 value 必须是非空标量列表。")
        elif self.operation == "numeric_distance_to_user_value":
            if not _is_finite_number_or_numeric_string(value):
                raise ValueError("numeric_distance_to_user_value 的 value 必须是有限数值。")
        elif self.operation in {
            "numeric_higher_is_better",
            "numeric_lower_is_better",
            "missing_value_penalty",
        }:
            if value is not None and not _is_scalar_value(value):
                raise ValueError(f"{self.operation} 的 value 必须为空或标量。")
        elif self.operation == "boolean_preferred_value":
            if not _is_boolean_preference_value(value):
                raise ValueError("boolean_preferred_value 的 value 必须是布尔值或已审查布尔文本。")
        return self


class RankingPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[RankingCriterion] = Field(default_factory=list)
    rationale_summary: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_raw_sql_payload(cls, value: Any) -> Any:
        _reject_raw_sql_key(value, "ranking plan")
        return _reject_sql_command_text(value, "ranking plan")

    @field_validator("rationale_summary")
    @classmethod
    def _normalize_rationale_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reject_sql_command_text(value: Any, context: str) -> Any:
    if isinstance(value, str) and SQL_COMMAND_TEXT_PATTERN.search(value):
        raise ValueError(f"{context} 不能包含 SQL 命令文本。")
    if isinstance(value, dict):
        for nested_value in value.values():
            _reject_sql_command_text(nested_value, context)
    elif isinstance(value, list):
        for nested_value in value:
            _reject_sql_command_text(nested_value, context)
    return value


def _is_scalar_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _is_non_empty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_non_empty_string(item) for item in value)
    )


def _is_non_empty_scalar_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_scalar_value(item) for item in value)
    )


def _is_finite_number_or_numeric_string(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str) and value.strip():
        try:
            return math.isfinite(float(value.strip()))
        except ValueError:
            return False
    return False


def _is_boolean_preference_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip().lower() in BOOLEAN_STRING_VALUES
    return False


__all__ = [
    "ALLOWED_RANKING_OPERATIONS",
    "RankingCriterion",
    "RankingOperation",
    "RankingPlan",
]
