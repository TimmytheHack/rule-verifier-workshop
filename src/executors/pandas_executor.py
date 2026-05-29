"""pandas executor for Excel/CSV-style MVP data."""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


def parse_number(value: Any) -> float | None:
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


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


class PandasExecutor:
    """Executes verified rules against a pandas DataFrame.

    pandas is only the MVP executor for Excel/CSV data. It does not verify rules.
    """

    def execute(self, dataframe: pd.DataFrame, executable_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for frame_index, row in dataframe.iterrows():
            row_dict = row.to_dict()
            if self._passes(row_dict, executable_rules):
                results.append(self._project_row(frame_index, row_dict))
        return sorted(
            results,
            key=lambda item: (
                item["ranking_key"],
                self._school_rank_sort(item["院校排名"]),
                item["ID"] if isinstance(item["ID"], (int, float)) else 999999,
            ),
        )

    def _passes(self, row: dict[str, Any], executable_rules: list[dict[str, Any]]) -> bool:
        for rule in executable_rules:
            field = rule["field"]
            operator = rule["operator"]
            value = rule["value"]
            cell = row.get(field)
            if operator == "eq" and cell_text(cell) != value:
                return False
            if operator == "contains" and value not in cell_text(cell):
                return False
            if operator == "in_contains" and not any(item in cell_text(cell) for item in value):
                return False
            if operator == ">=":
                parsed = parse_number(cell)
                if parsed is None or parsed < value:
                    return False
            if operator == "<=":
                parsed = parse_number(cell)
                if parsed is None or parsed > value:
                    return False
        return True

    def _project_row(self, frame_index: Any, row: dict[str, Any]) -> dict[str, Any]:
        group_rank = parse_number(row.get("专业组最低位次1"))
        tuition = parse_number(row.get("学费"))
        if group_rank is None or tuition is None:
            raise ValueError("Executable rules should have filtered out rows without rank or tuition.")
        return {
            "excel_row_number": int(frame_index) + 4,
            "ID": clean_value(row.get("ID")),
            "年份": clean_value(row.get("年份")),
            "批次": clean_value(row.get("批次")),
            "院校代码": clean_value(row.get("院校代码")),
            "院校名称": clean_value(row.get("院校名称")),
            "院校专业组代码": clean_value(row.get("院校专业组代码")),
            "专业组名称": clean_value(row.get("专业组名称")),
            "专业代码": clean_value(row.get("专业代码")),
            "专业名称": cell_text(row.get("专业名称")),
            "专业全称": clean_value(row.get("专业全称")),
            "城市": cell_text(row.get("城市")),
            "学费": tuition,
            "专业组最低位次1": int(group_rank),
            "最低位次1": clean_value(row.get("最低位次1")),
            "院校标签": clean_value(row.get("院校标签")),
            "院校排名": clean_value(row.get("院校排名")),
            "ranking_key": int(group_rank - 35200),
            "safety_margin_pct": round((group_rank - 32000) / 32000, 4),
            "cooperation_filter_status": "not_executed_missing_cooperation_type_field",
        }

    def _school_rank_sort(self, value: Any) -> float:
        parsed = parse_number(value)
        return parsed if parsed is not None else 999999.0
