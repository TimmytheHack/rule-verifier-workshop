"""Local DuckDB data warehouse for structured admission data."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
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
    source_path: Path
    row_count: int
    column_count: int
    source_fingerprint: str
    field_profiles: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "fingerprint": self.source_fingerprint,
            "source_fingerprint": self.source_fingerprint,
            "database_path": str(self.database_path),
            "index_path": str(self.index_path),
            "table_name": self.table_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "field_profiles": self.field_profiles,
            "created_at": self.created_at,
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
    return build_structured_store_from_dataset(
        dataset=dataset,
        schema_path=schema_path,
        database_path=database_path,
        index_path=index_path,
        table_name=table_name,
        source_path=workbook_path,
    )


def build_structured_store_from_dataset(
    dataset: ExcelDataSet,
    schema_path: str | Path,
    database_path: str | Path,
    index_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
    source_path: str | Path | None = None,
) -> WarehouseBuildResult:
    """把已读取的结构化数据落到 DuckDB，并复用 schema/value index 构建。"""

    database_path = Path(database_path)
    index_path = Path(index_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = _utc_timestamp()
    source_path = Path(source_path or dataset.workbook_path)
    source_fingerprint = _file_fingerprint(source_path)

    with duckdb.connect(str(database_path)) as connection:
        connection.register("source_dataframe", dataset.dataframe)
        quoted_table = _quote_identifier(table_name)
        connection.execute(f"CREATE OR REPLACE TABLE {quoted_table} AS SELECT * FROM source_dataframe")
        _write_metadata(
            connection,
            dataset,
            table_name,
            source_fingerprint=source_fingerprint,
            created_at=created_at,
        )

    registry = SchemaRegistry.from_file(schema_path, dataset.headers)
    index_payload = build_schema_value_index(
        dataset=dataset,
        schema_registry=registry,
        database_path=database_path,
        table_name=table_name,
        source_fingerprint=source_fingerprint,
        created_at=created_at,
    )
    index_path.write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return WarehouseBuildResult(
        database_path=database_path,
        index_path=index_path,
        table_name=table_name,
        source_path=source_path,
        row_count=len(dataset.dataframe),
        column_count=len(dataset.dataframe.columns),
        source_fingerprint=source_fingerprint,
        field_profiles=index_payload.get("fields", {}),
        created_at=created_at,
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
    source_fingerprint: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """生成字段级 value dictionary，供抽取和审查参考。"""

    source_fingerprint = source_fingerprint or _file_fingerprint(dataset.workbook_path)
    created_at = created_at or _utc_timestamp()
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
            "source_path": str(dataset.workbook_path),
            "workbook_path": str(dataset.workbook_path),
            "sheet_name": dataset.sheet_name,
            "header_row": dataset.header_row,
            "fingerprint": source_fingerprint,
            "source_fingerprint": source_fingerprint,
            "created_at": created_at,
        },
        "warehouse": {
            "database_path": str(database_path),
            "table_name": table_name,
            "row_count": len(dataset.dataframe),
            "column_count": len(dataset.dataframe.columns),
            "created_at": created_at,
        },
        "fields": fields,
    }


def audit_data_warehouse_fingerprints(
    workbook_path: str | Path,
    database_path: str | Path,
    index_path: str | Path,
    table_name: str = DEFAULT_TABLE_NAME,
) -> dict[str, Any]:
    """校验 DuckDB、schema/value index 和源 Excel 是否来自同一版本。"""

    workbook_path = Path(workbook_path)
    database_path = Path(database_path)
    index_path = Path(index_path)
    warnings: list[dict[str, Any]] = []

    source_fingerprint = None
    if workbook_path.exists():
        source_fingerprint = _file_fingerprint(workbook_path)
    else:
        warnings.append(
            _warehouse_warning(
                "missing_source_excel",
                f"源 Excel 不存在：{workbook_path}",
                expected=str(workbook_path),
                actual=None,
            )
        )

    warehouse_metadata: dict[str, Any] = {}
    warehouse_profile: dict[str, Any] = {}
    if not database_path.exists():
        warnings.append(
            _warehouse_warning(
                "missing_warehouse",
                f"DuckDB 数据仓库不存在：{database_path}",
                expected=str(database_path),
                actual=None,
            )
        )
    else:
        try:
            warehouse_metadata = read_warehouse_metadata(database_path)
            warehouse_profile = _read_table_profile(database_path, table_name)
        except Exception as exc:
            warnings.append(
                _warehouse_warning(
                    "unreadable_warehouse_metadata",
                    f"DuckDB metadata 读取失败：{exc}",
                    expected=str(database_path),
                    actual=type(exc).__name__,
                )
            )
        if database_path.exists() and not warehouse_metadata:
            warnings.append(
                _warehouse_warning(
                    "missing_warehouse_metadata",
                    "DuckDB 缺少 __metadata 表，不能验证数据来源。",
                    expected="__metadata",
                    actual=None,
                )
            )

    value_index_payload: dict[str, Any] = {}
    if not index_path.exists():
        warnings.append(
            _warehouse_warning(
                "missing_value_index",
                f"schema/value index 不存在：{index_path}",
                expected=str(index_path),
                actual=None,
            )
        )
    else:
        try:
            loaded_index = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded_index, dict):
                value_index_payload = loaded_index
            else:
                warnings.append(
                    _warehouse_warning(
                        "invalid_value_index_metadata",
                        "schema/value index JSON 不是对象，不能验证 metadata。",
                        expected="object",
                        actual=type(loaded_index).__name__,
                    )
                )
        except Exception as exc:
            warnings.append(
                _warehouse_warning(
                    "unreadable_value_index",
                    f"schema/value index 读取失败：{exc}",
                    expected=str(index_path),
                    actual=type(exc).__name__,
                )
            )

    warehouse_fingerprint = _metadata_fingerprint(warehouse_metadata)
    value_index_source = value_index_payload.get("source") or {}
    value_index_warehouse = value_index_payload.get("warehouse") or {}
    value_index_fingerprint = _metadata_fingerprint(value_index_source)

    if source_fingerprint and warehouse_metadata:
        if not warehouse_fingerprint:
            warnings.append(
                _warehouse_warning(
                    "missing_warehouse_fingerprint",
                    "DuckDB metadata 缺少 source_fingerprint。",
                    expected=source_fingerprint,
                    actual=None,
                )
            )
        elif warehouse_fingerprint != source_fingerprint:
            warnings.append(
                _warehouse_warning(
                    "warehouse_fingerprint_mismatch",
                    "DuckDB metadata fingerprint 与源 Excel fingerprint 不一致。",
                    expected=source_fingerprint,
                    actual=warehouse_fingerprint,
                )
            )

    if source_fingerprint and value_index_payload:
        if not value_index_fingerprint:
            warnings.append(
                _warehouse_warning(
                    "missing_value_index_fingerprint",
                    "schema/value index 缺少 source fingerprint。",
                    expected=source_fingerprint,
                    actual=None,
                )
            )
        elif value_index_fingerprint != source_fingerprint:
            warnings.append(
                _warehouse_warning(
                    "value_index_fingerprint_mismatch",
                    "schema/value index fingerprint 与源 Excel fingerprint 不一致。",
                    expected=source_fingerprint,
                    actual=value_index_fingerprint,
                )
            )

    if warehouse_fingerprint and value_index_fingerprint:
        if warehouse_fingerprint != value_index_fingerprint:
            warnings.append(
                _warehouse_warning(
                    "warehouse_value_index_fingerprint_mismatch",
                    "DuckDB metadata 与 schema/value index fingerprint 不一致。",
                    expected=warehouse_fingerprint,
                    actual=value_index_fingerprint,
                )
            )

    warnings.extend(
        _count_mismatch_warnings(
            warehouse_metadata=warehouse_metadata,
            warehouse_profile=warehouse_profile,
            value_index_warehouse=value_index_warehouse,
        )
    )

    return {
        "status": "ok" if not warnings else "warning",
        "ok": not warnings,
        "warnings": warnings,
        "source": {
            "path": str(workbook_path),
            "exists": workbook_path.exists(),
            "fingerprint": source_fingerprint,
        },
        "duckdb": {
            "path": str(database_path),
            "exists": database_path.exists(),
            "metadata": warehouse_metadata,
            "profile": warehouse_profile,
            "fingerprint": warehouse_fingerprint,
        },
        "schema_value_index": {
            "path": str(index_path),
            "exists": index_path.exists(),
            "source": value_index_source,
            "warehouse": value_index_warehouse,
            "fingerprint": value_index_fingerprint,
        },
    }


def read_warehouse_metadata(database_path: str | Path) -> dict[str, str]:
    """读取 DuckDB 仓库的 metadata 表。"""

    with duckdb.connect(str(database_path), read_only=True) as connection:
        return _read_metadata(connection)


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
    source_fingerprint: str | None = None,
    created_at: str | None = None,
) -> None:
    source_fingerprint = source_fingerprint or _file_fingerprint(dataset.workbook_path)
    created_at = created_at or _utc_timestamp()
    metadata = pd.DataFrame(
        [
            {"key": "source_path", "value": str(dataset.workbook_path)},
            {"key": "sheet_name", "value": dataset.sheet_name},
            {"key": "header_row", "value": str(dataset.header_row)},
            {"key": "table_name", "value": table_name},
            {"key": "row_count", "value": str(len(dataset.dataframe))},
            {"key": "column_count", "value": str(len(dataset.dataframe.columns))},
            {"key": "fingerprint", "value": source_fingerprint},
            {"key": "source_fingerprint", "value": source_fingerprint},
            {"key": "created_at", "value": created_at},
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


def _read_table_profile(
    database_path: Path,
    table_name: str,
) -> dict[str, Any]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        table_sql = _quote_identifier(table_name)
        row_count = int(connection.execute(f"SELECT count(*) FROM {table_sql}").fetchone()[0])
        columns = connection.execute(f"DESCRIBE {table_sql}").fetchall()
    return {
        "table_name": table_name,
        "row_count": row_count,
        "column_count": len(columns),
    }


def _count_mismatch_warnings(
    warehouse_metadata: dict[str, Any],
    warehouse_profile: dict[str, Any],
    value_index_warehouse: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = []
    metadata_row_count = _metadata_int(warehouse_metadata.get("row_count"))
    metadata_column_count = _metadata_int(warehouse_metadata.get("column_count"))
    profile_row_count = _metadata_int(warehouse_profile.get("row_count"))
    profile_column_count = _metadata_int(warehouse_profile.get("column_count"))
    value_index_row_count = _metadata_int(value_index_warehouse.get("row_count"))
    value_index_column_count = _metadata_int(value_index_warehouse.get("column_count"))

    if (
        metadata_row_count is not None
        and profile_row_count is not None
        and metadata_row_count != profile_row_count
    ):
        warnings.append(
            _warehouse_warning(
                "warehouse_row_count_mismatch",
                "DuckDB metadata row_count 与实际表行数不一致。",
                expected=metadata_row_count,
                actual=profile_row_count,
            )
        )
    if (
        metadata_column_count is not None
        and profile_column_count is not None
        and metadata_column_count != profile_column_count
    ):
        warnings.append(
            _warehouse_warning(
                "warehouse_column_count_mismatch",
                "DuckDB metadata column_count 与实际表列数不一致。",
                expected=metadata_column_count,
                actual=profile_column_count,
            )
        )
    if (
        metadata_row_count is not None
        and value_index_row_count is not None
        and metadata_row_count != value_index_row_count
    ):
        warnings.append(
            _warehouse_warning(
                "value_index_row_count_mismatch",
                "DuckDB metadata row_count 与 schema/value index row_count 不一致。",
                expected=metadata_row_count,
                actual=value_index_row_count,
            )
        )
    if (
        metadata_column_count is not None
        and value_index_column_count is not None
        and metadata_column_count != value_index_column_count
    ):
        warnings.append(
            _warehouse_warning(
                "value_index_column_count_mismatch",
                "DuckDB metadata column_count 与 schema/value index column_count 不一致。",
                expected=metadata_column_count,
                actual=value_index_column_count,
            )
        )
    return warnings


def _metadata_fingerprint(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("fingerprint") or metadata.get("source_fingerprint")
    return str(value) if value else None


def _metadata_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _warehouse_warning(
    code: str,
    message: str,
    expected: Any,
    actual: Any,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "message": message,
        "expected": expected,
        "actual": actual,
    }


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


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
