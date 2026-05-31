"""Offline tool: generate an automatic profile for every Excel column."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.excel_adapter import ExcelAdapter
from src.schema.schema_profiler import SchemaProfiler, build_markdown_report


WORKBOOK_NAME = "广东省2025年志愿填报大数据（24-25）0523.xlsx"
REQUIRED_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]
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
