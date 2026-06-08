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

    def execute(
        self,
        dataframe: pd.DataFrame,
        executable_rules: list[dict[str, Any]],
        user_rank: int | None = None,
    ) -> list[dict[str, Any]]:
        context = _execution_context(executable_rules, user_rank)
        results: list[dict[str, Any]] = []
        for frame_index, row in dataframe.iterrows():
            row_dict = row.to_dict()
            if self._passes(row_dict, executable_rules):
                projected = self._project_row(frame_index, row_dict, context)
                if projected is not None:
                    results.append(projected)
        return sorted(
            results,
            key=lambda item: (
                item["专业组最低位次1"]
                if item.get("专业组最低位次1") is not None
                else 999999999,
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
            if operator in {"in_contains", "contains_any"} and not any(
                item in cell_text(cell) for item in value
            ):
                return False
            if operator == "in" and cell_text(cell) not in {str(item) for item in value}:
                return False
            if operator == "not_in" and cell_text(cell) in {str(item) for item in value}:
                return False
            if operator == "satisfies_subject_requirement" and not _subject_requirement_satisfied(cell, value):
                return False
            if operator == ">=":
                parsed = parse_number(cell)
                if parsed is None or parsed < value:
                    return False
            if operator == "<=":
                parsed = parse_number(cell)
                if parsed is None or parsed > value:
                    return False
            if operator == "between":
                parsed = parse_number(cell)
                lower, upper = _numeric_range(value)
                if parsed is None or lower is None or upper is None:
                    return False
                if parsed < lower or parsed > upper:
                    return False
        return True

    def _project_row(
        self,
        frame_index: Any,
        row: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        group_rank = parse_number(row.get("专业组最低位次1"))
        tuition = parse_number(row.get("学费"))
        if group_rank is None or tuition is None:
            return None
        user_rank = context.get("user_rank")
        ranking_reference = user_rank or context.get("safety_cutoff")
        ranking_key = int(group_rank - ranking_reference) if ranking_reference else None
        safety_margin_pct = (
            round((group_rank - user_rank) / user_rank, 4)
            if user_rank
            else None
        )
        return {
            "excel_row_number": int(frame_index) + 4,
            "ID": clean_value(row.get("ID")),
            "年份": clean_value(row.get("年份")),
            "批次": clean_value(row.get("批次")),
            "院校代码": clean_value(row.get("院校代码")),
            "院校名称": clean_value(row.get("院校名称")),
            "院校专业组代码": clean_value(row.get("院校专业组代码")),
            "专业组名称": clean_value(row.get("专业组名称")),
            "科类": clean_value(row.get("科类")),
            "选科要求": clean_value(row.get("选科要求")),
            "专业代码": clean_value(row.get("专业代码")),
            "专业名称": cell_text(row.get("专业名称")),
            "专业全称": clean_value(row.get("专业全称")),
            "所在省": clean_value(row.get("所在省")),
            "城市": cell_text(row.get("城市")),
            "学费": tuition,
            "专业组最低位次1": int(group_rank),
            "最低位次1": clean_value(row.get("最低位次1")),
            "院校标签": clean_value(row.get("院校标签")),
            "院校排名": clean_value(row.get("院校排名")),
            "ranking_key": ranking_key,
            "safety_margin_pct": safety_margin_pct,
            "cooperation_filter_status": "not_executed_missing_cooperation_type_field",
            "中外合作筛选状态": "未执行：缺少合作办学类型字段",
        }

    def _safety_sort_bucket(self, item: dict[str, Any]) -> int:
        ranking_key = item.get("ranking_key")
        if ranking_key is None:
            return 1
        return 0 if ranking_key >= 0 else 1

    def _school_rank_sort(self, value: Any) -> float:
        parsed = parse_number(value)
        return parsed if parsed is not None else 999999.0


def _execution_context(
    executable_rules: list[dict[str, Any]],
    user_rank: int | None,
) -> dict[str, Any]:
    safety_cutoff = None
    for rule in executable_rules:
        if rule.get("field") == "专业组最低位次1" and rule.get("operator") == ">=":
            parsed = parse_number(rule.get("value"))
            safety_cutoff = int(parsed) if parsed is not None else None
            break
    return {
        "user_rank": user_rank,
        "safety_cutoff": safety_cutoff,
    }


def _numeric_range(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, list) or len(value) != 2:
        return None, None
    first = parse_number(value[0])
    second = parse_number(value[1])
    if first is None or second is None:
        return None, None
    return (min(first, second), max(first, second))


def _subject_requirement_satisfied(requirement: Any, selected_subjects: Any) -> bool:
    required_groups = _required_subject_groups(requirement)
    if not required_groups:
        return True
    selected = {_normalize_subject(subject) for subject in selected_subjects or []}
    selected.discard("")
    return any(group.issubset(selected) for group in required_groups)


def _required_subject_groups(requirement: Any) -> list[set[str]]:
    text = cell_text(requirement)
    if not text or text in {"不限", "无", "nan"}:
        return []
    normalized = text.replace("思想政治", "政治").replace("生物学", "生物")
    if "不限" in normalized:
        return []
    if "或" in normalized:
        return [
            subjects
            for subjects in (_subjects_in_text(part) for part in re.split(r"或|/", normalized))
            if subjects
        ]
    subjects = _subjects_in_text(normalized)
    return [subjects] if subjects else []


def _subjects_in_text(text: str) -> set[str]:
    return {
        subject
        for subject in ["化学", "生物", "政治", "地理"]
        if subject in text
    }


def _normalize_subject(value: Any) -> str:
    text = cell_text(value)
    if "思想政治" in text:
        return "政治"
    if "生物" in text:
        return "生物"
    for subject in ["化学", "政治", "地理"]:
        if subject in text:
            return subject
    return text
