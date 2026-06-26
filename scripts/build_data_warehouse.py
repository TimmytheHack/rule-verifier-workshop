"""Build the local DuckDB store and schema/value index."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_mvp_demo import REQUIRED_COLUMNS, SCHEMA_PATH, WORKBOOK_NAME
from src.adapters.data_warehouse import build_structured_store


OUTPUT_DIR = Path("outputs/data")
DATABASE_PATH = OUTPUT_DIR / "guangdong_admissions.duckdb"
VALUE_INDEX_PATH = OUTPUT_DIR / "schema_value_index.json"
INGESTION_SUMMARY_PATH = OUTPUT_DIR / "ingestion_summary.json"


def main() -> None:
    result = build_structured_store(
        workbook_path=WORKBOOK_NAME,
        required_columns=REQUIRED_COLUMNS,
        schema_path=SCHEMA_PATH,
        database_path=DATABASE_PATH,
        index_path=VALUE_INDEX_PATH,
    )
    _normalize_value_index_paths()
    summary = _normalized_summary(result.to_dict())
    INGESTION_SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _normalize_value_index_paths() -> None:
    payload = json.loads(VALUE_INDEX_PATH.read_text(encoding="utf-8"))
    source = payload.get("source") or {}
    source["source_path"] = _stable_path(WORKBOOK_NAME)
    source["workbook_path"] = _stable_path(WORKBOOK_NAME)
    payload["source"] = source
    warehouse = payload.get("warehouse") or {}
    warehouse["database_path"] = _stable_path(DATABASE_PATH)
    payload["warehouse"] = warehouse
    VALUE_INDEX_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalized_summary(summary: dict[str, object]) -> dict[str, object]:
    normalized = dict(summary)
    normalized["source_path"] = _stable_path(WORKBOOK_NAME)
    normalized["database_path"] = _stable_path(DATABASE_PATH)
    normalized["index_path"] = _stable_path(VALUE_INDEX_PATH)
    return normalized


def _stable_path(path: str | Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    try:
        return candidate.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return Path(path).as_posix()


if __name__ == "__main__":
    main()
