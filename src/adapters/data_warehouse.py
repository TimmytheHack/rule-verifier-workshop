"""Local DuckDB data warehouse for structured admission data."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.adapters.excel_adapter import ExcelAdapter, ExcelDataSet, cell_text
from src.schema.schema_registry import SchemaRegistry


DEFAULT_TABLE_NAME = "admissions"
DEFAULT_LOOKUP_LIMIT = 2000


@dataclass(frozen=True)
class WarehouseBuildResult:
    """构建本地结构化仓库后的摘要。"""

    database_path: Path
    index_path: Path
    table_name: str
    row_count: int
    column_count: int
    source_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path),
            "index_path": str(self.index_path),
            "table_name": self.table_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "source_fingerprint": self.source_fingerprint,
        }


def build_structured_store(
    workbook_path: str | Path,
    required_columns: list[str],
    schema_path: str | Path,
    database_path: str | Path,
    index_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
) -> WarehouseBuildResult:
    """把 Excel 离线落到 DuckDB，并生成 schema/value index。"""

    dataset = ExcelAdapter(workbook_path, required_columns).load()
    database_path = Path(database_path)
    index_path = Path(index_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(database_path)) as connection:
        connection.register("source_dataframe", dataset.dataframe)
        quoted_table = _quote_identifier(table_name)
        connection.execute(f"CREATE OR REPLACE TABLE {quoted_table} AS SELECT * FROM source_dataframe")
        _write_metadata(connection, dataset, table_name)

    registry = SchemaRegistry.from_file(schema_path, dataset.headers)
    index_payload = build_schema_value_index(
        dataset=dataset,
        schema_registry=registry,
        database_path=database_path,
        table_name=table_name,
    )
    index_path.write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return WarehouseBuildResult(
        database_path=database_path,
        index_path=index_path,
        table_name=table_name,
        row_count=len(dataset.dataframe),
        column_count=len(dataset.dataframe.columns),
        source_fingerprint=_file_fingerprint(Path(workbook_path)),
    )


def load_structured_dataset(
    database_path: str | Path,
    required_columns: list[str],
    table_name: str = DEFAULT_TABLE_NAME,
) -> ExcelDataSet:
    """从本地 DuckDB 仓库读取数据，暴露和 ExcelAdapter 一致的数据结构。"""

    database_path = Path(database_path)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        dataframe = connection.execute(
            f"SELECT * FROM {_quote_identifier(table_name)}"
        ).fetchdf()
        metadata = _read_metadata(connection)

    missing = [column for column in required_columns if column not in dataframe.columns]
    if missing:
        raise RuntimeError(f"Structured store missing required columns: {', '.join(missing)}")

    headers = [cell_text(column) for column in dataframe.columns]
    header_index = {name: idx for idx, name in enumerate(headers) if name}
    return ExcelDataSet(
        workbook_path=database_path,
        sheet_name=metadata.get("table_name", table_name),
        header_row=int(metadata.get("header_row", 0)),
        headers=headers,
        header_index=header_index,
        dataframe=dataframe,
    )


def build_schema_value_index(
    dataset: ExcelDataSet,
    schema_registry: SchemaRegistry,
    database_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
    top_k: int = 30,
    lookup_limit: int = DEFAULT_LOOKUP_LIMIT,
) -> dict[str, Any]:
    """生成字段级 value dictionary，供抽取和审查参考。"""

    fields = {}
    for field_id, spec in schema_registry.configured_fields.items():
        source_column = spec.get("source_column")
        active = schema_registry.has_field(field_id)
        field_record: dict[str, Any] = {
            "source_column": source_column,
            "active": active,
            "type": spec.get("type"),
            "allowed_ops": spec.get("allowed_ops", []),
            "aliases": spec.get("aliases", []),
        }
        if active and source_column in dataset.dataframe.columns:
            series = dataset.dataframe[source_column]
            field_record.update(
                _series_value_profile(
                    series,
                    spec,
                    top_k=top_k,
                    lookup_limit=lookup_limit,
                )
            )
        fields[field_id] = field_record

    return {
        "source": {
            "workbook_path": str(dataset.workbook_path),
            "sheet_name": dataset.sheet_name,
            "header_row": dataset.header_row,
            "source_fingerprint": _file_fingerprint(dataset.workbook_path),
        },
        "warehouse": {
            "database_path": str(database_path),
            "table_name": table_name,
            "row_count": len(dataset.dataframe),
            "column_count": len(dataset.dataframe.columns),
        },
        "fields": fields,
    }


class SchemaValueIndex:
    """只读字段值索引，用于接地审计，不参与规则执行。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.fields = payload.get("fields", {})

    @classmethod
    def from_file(cls, path: str | Path) -> "SchemaValueIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload)

    def audit_value(self, field_id: str | None, value: Any) -> dict[str, Any]:
        """检查抽取值是否能在离线 value index 中找到证据。"""

        if not field_id:
            return {
                "field_id": field_id,
                "status": "not_applicable",
                "reason": "没有字段映射，无法做值索引审计。",
            }
        field = self.fields.get(field_id)
        if not field:
            return {
                "field_id": field_id,
                "status": "field_not_indexed",
                "reason": "schema/value index 中没有该字段。",
            }
        if not field.get("active"):
            return {
                "field_id": field_id,
                "source_column": field.get("source_column"),
                "status": "field_inactive",
                "reason": "该字段未进入当前可执行 schema。",
            }
        values = _value_list(value)
        if not values:
            return {
                "field_id": field_id,
                "source_column": field.get("source_column"),
                "status": "empty_value",
                "reason": "抽取值为空，无法做值索引审计。",
            }
        if field.get("numeric"):
            return self._audit_numeric(field_id, field, values)
        return self._audit_text(field_id, field, values)

    def _audit_numeric(
        self,
        field_id: str,
        field: dict[str, Any],
        values: list[Any],
    ) -> dict[str, Any]:
        numeric = field.get("numeric") or {}
        minimum = _parse_number(numeric.get("min"))
        maximum = _parse_number(numeric.get("max"))
        parsed_values = [_parse_number(value) for value in values]
        checks = []
        for original, parsed in zip(values, parsed_values, strict=True):
            within_range = (
                parsed is not None
                and minimum is not None
                and maximum is not None
                and minimum <= parsed <= maximum
            )
            checks.append(
                {
                    "value": original,
                    "parsed_value": parsed,
                    "status": (
                        "within_numeric_profile"
                        if within_range
                        else "outside_numeric_profile"
                    ),
                }
            )
        if all(check["status"] == "within_numeric_profile" for check in checks):
            status = "within_numeric_profile"
        elif any(check["status"] == "within_numeric_profile" for check in checks):
            status = "partial_numeric_profile"
        else:
            status = "outside_numeric_profile"
        return {
            "field_id": field_id,
            "source_column": field.get("source_column"),
            "status": status,
            "profile_kind": "numeric",
            "numeric": numeric,
            "checks": checks,
        }

    def _audit_text(
        self,
        field_id: str,
        field: dict[str, Any],
        values: list[Any],
    ) -> dict[str, Any]:
        lookup_values = [str(item) for item in field.get("lookup_values") or []]
        lookup_complete = bool(field.get("lookup_complete"))
        if not lookup_values:
            return {
                "field_id": field_id,
                "source_column": field.get("source_column"),
                "status": "lookup_unavailable",
                "profile_kind": "text",
                "lookup_complete": lookup_complete,
                "reason": "该字段没有可用于运行时审计的值列表。",
            }

        checks = [
            _match_text_value(value, lookup_values, lookup_complete)
            for value in values
        ]
        statuses = {check["status"] for check in checks}
        if statuses <= {"exact_match", "contains_match"}:
            status = "matched"
        elif statuses & {"exact_match", "contains_match"}:
            status = "partial_match"
        elif lookup_complete:
            status = "not_found"
        else:
            status = "not_found_in_partial_index"
        return {
            "field_id": field_id,
            "source_column": field.get("source_column"),
            "status": status,
            "profile_kind": "text",
            "lookup_complete": lookup_complete,
            "distinct_count": field.get("distinct_count"),
            "checks": checks,
        }


def _write_metadata(
    connection: duckdb.DuckDBPyConnection,
    dataset: ExcelDataSet,
    table_name: str,
) -> None:
    metadata = pd.DataFrame(
        [
            {"key": "source_path", "value": str(dataset.workbook_path)},
            {"key": "sheet_name", "value": dataset.sheet_name},
            {"key": "header_row", "value": str(dataset.header_row)},
            {"key": "table_name", "value": table_name},
            {"key": "row_count", "value": str(len(dataset.dataframe))},
            {"key": "source_fingerprint", "value": _file_fingerprint(dataset.workbook_path)},
        ]
    )
    connection.register("metadata_dataframe", metadata)
    connection.execute(
        "CREATE OR REPLACE TABLE __metadata AS SELECT * FROM metadata_dataframe"
    )


def _read_metadata(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    try:
        rows = connection.execute("SELECT key, value FROM __metadata").fetchall()
    except duckdb.CatalogException:
        return {}
    return {str(key): str(value) for key, value in rows}


def _series_value_profile(
    series: pd.Series,
    spec: dict[str, Any],
    top_k: int,
    lookup_limit: int,
) -> dict[str, Any]:
    cleaned = series.dropna().map(cell_text)
    cleaned = cleaned[cleaned != ""]
    distinct_values = [str(value) for value in cleaned.drop_duplicates()]
    top_values = [
        {"value": str(value), "count": int(count)}
        for value, count in cleaned.value_counts().head(top_k).items()
    ]
    profile: dict[str, Any] = {
        "non_null_count": int(cleaned.shape[0]),
        "distinct_count": int(cleaned.nunique()),
        "top_values": top_values,
        "sample_values": distinct_values[:10],
        "lookup_complete": len(distinct_values) <= lookup_limit,
    }
    if profile["lookup_complete"]:
        profile["lookup_values"] = distinct_values
    if spec.get("type") in {"number", "number_from_string"}:
        numbers = cleaned.map(_parse_number).dropna()
        if not numbers.empty:
            profile["numeric"] = {
                "min": _clean_number(numbers.min()),
                "max": _clean_number(numbers.max()),
            }
    return profile


def _value_list(value: Any) -> list[Any]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [item for item in values if cell_text(item)]


def _match_text_value(
    value: Any,
    lookup_values: list[str],
    lookup_complete: bool,
) -> dict[str, Any]:
    text = cell_text(value)
    if not text:
        return {"value": value, "status": "empty_value", "matched_values": []}
    exact = [candidate for candidate in lookup_values if candidate == text]
    if exact:
        return {
            "value": value,
            "status": "exact_match",
            "matched_values": exact[:5],
        }
    contains = [
        candidate
        for candidate in lookup_values
        if text in candidate or candidate in text
    ]
    if contains:
        return {
            "value": value,
            "status": "contains_match",
            "matched_values": contains[:5],
        }
    return {
        "value": value,
        "status": "not_found" if lookup_complete else "not_found_in_partial_index",
        "matched_values": [],
    }


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    return float(match.group())


def _clean_number(value: Any) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def _file_fingerprint(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
