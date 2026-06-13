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
    summary = result.to_dict()
    INGESTION_SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
