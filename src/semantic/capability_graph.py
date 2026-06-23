from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.adapters.excel_adapter import ExcelDataSet, cell_text


LOW_CARDINALITY_VALUE_LIMIT = 200
BOOLEAN_TRUE_VALUES = {
    "是",
    "有",
    "1",
    "true",
    "TRUE",
    "True",
    "Y",
    "y",
    "yes",
    "YES",
}
BOOLEAN_FALSE_VALUES = {
    "否",
    "无",
    "0",
    "false",
    "FALSE",
    "False",
    "N",
    "n",
    "no",
    "NO",
}


@dataclass(frozen=True)
class CapabilityField:
    """数据源字段的可执行能力画像。"""

    source_column: str
    inferred_type: str
    non_null_count: int
    missing_rate: float
    distinct_count: int
    sample_values: list[str]
    numeric_min: float | None
    numeric_max: float | None
    candidate_ops: list[str]
    parse_success_rate: float
    top_values: list[dict[str, Any]]
    distinct_values: list[str]
    distinct_values_complete: bool
    boolean_profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "inferred_type": self.inferred_type,
            "non_null_count": self.non_null_count,
            "missing_rate": self.missing_rate,
            "distinct_count": self.distinct_count,
            "sample_values": self.sample_values,
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "candidate_ops": self.candidate_ops,
            "parse_success_rate": self.parse_success_rate,
            "top_values": self.top_values,
            "distinct_values": self.distinct_values,
            "distinct_values_complete": self.distinct_values_complete,
            "boolean_profile": self.boolean_profile,
        }


@dataclass(frozen=True)
class DatasetCapabilityGraph:
    """数据集级别的字段能力图。"""

    source_path: Path
    sheet_name: str
    row_count: int
    column_count: int
    fields: dict[str, CapabilityField]
    missing_source_columns: list[str]

    @classmethod
    def from_dataset(
        cls,
        dataset: ExcelDataSet,
        expected_source_columns: list[str] | None = None,
    ) -> "DatasetCapabilityGraph":
        row_count = len(dataset.dataframe)
        fields = {
            header: _field_profile(header, dataset.dataframe[header], row_count)
            for header in dataset.headers
            if header and header in dataset.dataframe.columns
        }
        expected = expected_source_columns or []
        missing_source_columns = [
            column for column in expected if column and column not in fields
        ]
        return cls(
            source_path=dataset.workbook_path,
            sheet_name=dataset.sheet_name,
            row_count=row_count,
            column_count=len(dataset.headers),
            fields=fields,
            missing_source_columns=missing_source_columns,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "sheet_name": self.sheet_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "fields": {
                name: field.to_dict() for name, field in self.fields.items()
            },
            "missing_source_columns": self.missing_source_columns,
        }


def _field_profile(
    source_column: str,
    series: pd.Series,
    row_count: int,
) -> CapabilityField:
    values = [_profile_cell_text(value) for value in series.tolist()]
    non_empty = [value for value in values if value]
    numeric_values = [
        parsed for parsed in (_parse_number(value) for value in non_empty)
        if parsed is not None
    ]
    non_null_count = len(non_empty)
    distinct_values = list(dict.fromkeys(non_empty))
    distinct_count = len(distinct_values)
    numeric_ratio = (
        len(numeric_values) / non_null_count if non_null_count else 0.0
    )
    inferred_type = _infer_type(
        non_null_count=non_null_count,
        distinct_count=distinct_count,
        numeric_ratio=numeric_ratio,
        sample_values=distinct_values[:20],
    )
    boolean_profile = _boolean_profile(non_empty, row_count)
    candidate_ops = _candidate_ops(inferred_type)
    if (
        boolean_profile["is_boolean_like"]
        and "boolean_preferred_value" not in candidate_ops
    ):
        candidate_ops = [*candidate_ops, "boolean_preferred_value"]
    distinct_values_for_output = distinct_values[:LOW_CARDINALITY_VALUE_LIMIT]
    return CapabilityField(
        source_column=source_column,
        inferred_type=inferred_type,
        non_null_count=non_null_count,
        missing_rate=(row_count - non_null_count) / row_count if row_count else 0.0,
        distinct_count=distinct_count,
        sample_values=distinct_values[:5],
        numeric_min=min(numeric_values) if numeric_values else None,
        numeric_max=max(numeric_values) if numeric_values else None,
        candidate_ops=candidate_ops,
        parse_success_rate=(
            len(numeric_values) / non_null_count if non_null_count else 0.0
        ),
        top_values=_top_values(non_empty),
        distinct_values=distinct_values_for_output,
        distinct_values_complete=distinct_count <= LOW_CARDINALITY_VALUE_LIMIT,
        boolean_profile=boolean_profile,
    )


def _profile_cell_text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return cell_text(value)


def _infer_type(
    *,
    non_null_count: int,
    distinct_count: int,
    numeric_ratio: float,
    sample_values: list[str],
) -> str:
    if numeric_ratio >= 0.95 and non_null_count > 0:
        return "number"
    if distinct_count <= 50:
        return "enum_or_category"
    if _has_long_text(sample_values):
        return "long_text"
    return "string"


def _has_long_text(sample_values: list[str]) -> bool:
    return any(len(value) >= 40 for value in sample_values)


def _candidate_ops(inferred_type: str) -> list[str]:
    if inferred_type == "number":
        return [
            "eq",
            "<=",
            ">=",
            "between",
            "sort",
            "numeric_distance_to_user_value",
            "numeric_higher_is_better",
            "numeric_lower_is_better",
        ]
    if inferred_type == "enum_or_category":
        return [
            "eq",
            "in",
            "not_in",
            "contains",
            "contains_any",
            "sort",
            "equals_preferred_value",
            "in_preferred_set",
        ]
    return ["contains", "contains_any", "eq", "sort", "text_match"]


def _top_values(values: list[str], limit: int = 20) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"value": value, "count": count} for value, count in ordered[:limit]]


def _top_count_items(counts: dict[str, int], limit: int = 20) -> list[dict[str, Any]]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"value": value, "count": count} for value, count in ordered[:limit]]


def _boolean_profile(values: list[str], row_count: int) -> dict[str, Any]:
    true_count = 0
    false_count = 0
    other_values: dict[str, int] = {}
    for value in values:
        normalized = value.strip()
        if normalized in BOOLEAN_TRUE_VALUES:
            true_count += 1
        elif normalized in BOOLEAN_FALSE_VALUES:
            false_count += 1
        else:
            other_values[normalized] = other_values.get(normalized, 0) + 1
    null_count = max(row_count - len(values), 0)
    other_count = sum(other_values.values())
    return {
        "true_count": true_count,
        "false_count": false_count,
        "null_count": null_count,
        "other_count": other_count,
        "true_rate": true_count / row_count if row_count else 0.0,
        "false_rate": false_count / row_count if row_count else 0.0,
        "other_values": _top_count_items(other_values, limit=5),
        "is_boolean_like": (true_count + false_count > 0 and other_count == 0),
    }


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    text = cell_text(value)
    if not text:
        return None
    normalized = text.replace(",", "").replace("，", "")
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    parsed = float(match.group(0))
    return parsed if math.isfinite(parsed) else None
