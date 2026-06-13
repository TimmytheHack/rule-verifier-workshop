"""Offline tool: generate an automatic profile for every Excel column."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.excel_adapter import ExcelAdapter
from src.domains import DomainConfig
from src.schema.schema_profiler import SchemaProfiler, build_markdown_report


ADMISSIONS_DOMAIN = DomainConfig.load("admissions")
WORKBOOK_NAME = ADMISSIONS_DOMAIN.workbook_path
REQUIRED_COLUMNS = ADMISSIONS_DOMAIN.required_columns
JSON_OUTPUT = Path("schemas/excel_schema_profile.json")
MD_OUTPUT = Path("docs/excel_schema_profile.md")


def main() -> None:
    dataset = ExcelAdapter(WORKBOOK_NAME, REQUIRED_COLUMNS).load()
    profile = SchemaProfiler().profile(
        dataframe=dataset.dataframe,
        headers=dataset.headers,
        workbook_name=str(dataset.workbook_path),
        sheet_name=dataset.sheet_name,
        header_row=dataset.header_row,
    )
    JSON_OUTPUT.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUTPUT.write_text(build_markdown_report(profile), encoding="utf-8")
    print(f"Wrote {JSON_OUTPUT}")
    print(f"Wrote {MD_OUTPUT}")
    print(f"Profiled {profile['column_count']} columns over {profile['row_count']} rows")


if __name__ == "__main__":
    main()
