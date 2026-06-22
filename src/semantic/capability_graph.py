from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.adapters.excel_adapter import ExcelDataSet, cell_text


@dataclass(frozen=True)
class CapabilityField:
    """数据源字段的可执行能力画像。"""

    source_column: str
    inferred_type: str
    non_null_count: int
    distinct_count: int
    sample_values: list[str]
    numeric_min: float | None
    numeric_max: float | None
    candidate_ops: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "inferred_type": self.inferred_type,
            "non_null_count": self.non_null_count,
            "distinct_count": self.distinct_count,
            "sample_values": self.sample_values,
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "candidate_ops": self.candidate_ops,
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
        fields = {
            header: _field_profile(header, dataset.dataframe[header])
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
            row_count=len(dataset.dataframe),
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


def _field_profile(source_column: str, series: pd.Series) -> CapabilityField:
    values = [cell_text(value) for value in series.tolist()]
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
    return CapabilityField(
        source_column=source_column,
        inferred_type=inferred_type,
        non_null_count=non_null_count,
        distinct_count=distinct_count,
        sample_values=distinct_values[:5],
        numeric_min=min(numeric_values) if numeric_values else None,
        numeric_max=max(numeric_values) if numeric_values else None,
        candidate_ops=_candidate_ops(inferred_type),
    )


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
        return ["eq", "<=", ">=", "between", "sort"]
    if inferred_type == "enum_or_category":
        return ["eq", "in", "not_in", "sort"]
    return ["contains", "eq", "sort"]


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
