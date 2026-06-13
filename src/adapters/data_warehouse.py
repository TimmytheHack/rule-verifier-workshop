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
            field_record.update(_series_value_profile(series, spec, top_k=top_k))
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
) -> dict[str, Any]:
    cleaned = series.dropna().map(cell_text)
    cleaned = cleaned[cleaned != ""]
    top_values = [
        {"value": str(value), "count": int(count)}
        for value, count in cleaned.value_counts().head(top_k).items()
    ]
    profile: dict[str, Any] = {
        "non_null_count": int(cleaned.shape[0]),
        "distinct_count": int(cleaned.nunique()),
        "top_values": top_values,
        "sample_values": [str(value) for value in cleaned.drop_duplicates().head(10)],
    }
    if spec.get("type") in {"number", "number_from_string"}:
        numbers = cleaned.map(_parse_number).dropna()
        if not numbers.empty:
            profile["numeric"] = {
                "min": _clean_number(numbers.min()),
                "max": _clean_number(numbers.max()),
            }
    return profile


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
