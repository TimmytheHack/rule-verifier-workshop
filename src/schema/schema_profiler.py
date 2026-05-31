"""Offline Excel schema profiling.

The profiler scans columns, not rows one by one. It creates a field catalog that
humans can review before promoting columns into the executable schema registry.

This module is intentionally an offline research/schema-review tool. It should
not be imported by the runtime recommendation or rule execution path.
"""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


KNOWN_FIELD_IDS = {
    "ID": "row_id",
    "年份": "year",
    "生源地": "source_province",
    "批次": "batch",
    "科类": "subject_type",
    "院校代码": "school_code",
    "院校名称": "school_name",
    "院校专业组代码": "school_major_group_code",
    "专业组名称": "major_group_name",
    "专业组代码": "major_group_code",
    "专业代码": "major_code",
    "专业全称": "major_full_name",
    "专业名称": "major_name",
    "专业备注": "major_notes",
    "专业层次": "degree_level",
    "选科要求": "subject_requirement",
    "计划人数": "plan_count",
    "学制": "program_duration",
    "学费": "tuition_yuan_per_year",
    "组内专业": "majors_in_group",
    "门类": "discipline_category",
    "专业类": "major_category",
    "专业组计划人数": "major_group_plan_count",
    "25年预估位次": "estimated_rank_2025",
    "是否新增": "is_new",
    "专业组录取人数1": "major_group_admit_count_2024",
    "专业组最低分1": "major_group_min_score_2024",
    "专业组最低位次1": "major_group_min_rank_2024",
    "录取人数1": "admit_count_2024",
    "最低分1": "min_score_2024",
    "最低位次1": "min_rank_2024",
    "最高分1": "max_score_2024",
    "最高位次1": "max_rank_2024",
    "所在省": "school_province",
    "城市": "city",
    "院校标签": "school_tags",
    "院校水平": "school_level",
    "更名合并转设": "school_change_history",
    "转专业情况": "major_transfer_policy",
    "城市水平标签": "city_level_tag",
    "本科/专科": "undergraduate_or_junior",
    "隶属单位": "supervising_department",
    "类型": "school_type",
    "公私性质": "school_ownership",
    "保研率": "postgraduate_recommendation_rate",
    "院校排名": "school_ranking",
    "全校硕士专业数": "school_master_program_count",
    "全校硕士专业": "school_master_programs",
    "全校博士专业数": "school_phd_program_count",
    "全校博士专业": "school_phd_programs",
    "2024招生章程": "admission_brochure_2024",
    "软科评级": "soft_science_rating",
    "软科排名": "soft_science_ranking",
    "学科评估": "discipline_evaluation",
    "专业水平": "major_level",
    "本专业硕士点": "major_master_program",
    "本专业博士点": "major_phd_program",
}


SEMANTIC_HINTS = {
    "source_province": ["广东", "生源地"],
    "subject_type": ["物理类", "历史类", "科类"],
    "school_name": ["学校", "院校"],
    "major_name": ["专业", "计算机", "法学"],
    "city": ["城市", "广州", "深圳"],
    "tuition_yuan_per_year": ["学费", "费用", "太贵"],
    "major_group_min_rank_2024": ["最低位次", "稳一点", "保底", "冲一冲"],
    "min_rank_2024": ["最低位次", "录取位次"],
    "school_ownership": ["公办", "民办", "公私性质"],
    "school_level": ["学校好", "院校水平", "名气"],
    "school_ranking": ["排名", "名气", "学校好"],
    "city_level_tag": ["城市水平", "偏远", "城市不要太差"],
    "major_category": ["专业相关", "专业类", "冷门"],
    "major_level": ["专业水平", "专业不要太冷门"],
    "school_tags": ["院校标签", "985", "211", "双一流"],
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


class SchemaProfiler:
    """Profiles every Excel column into reviewable schema metadata."""

    def __init__(self, max_samples: int = 8) -> None:
        self.max_samples = max_samples

    def profile(self, dataframe: pd.DataFrame, headers: list[str], workbook_name: str, sheet_name: str, header_row: int) -> dict[str, Any]:
        columns = []
        row_count = len(dataframe)
        for index, column in enumerate([header for header in headers if header]):
            if column not in dataframe.columns:
                continue
            series = dataframe[column]
            non_null = series.dropna()
            non_empty = [value for value in non_null.tolist() if clean_text(value)]
            samples = self._samples(non_empty)
            type_guess = self._type_guess(non_empty, samples)
            field_id = KNOWN_FIELD_IDS.get(column, f"column_{index + 1:02d}")
            columns.append(
                {
                    "column_index": index + 1,
                    "source_column": column,
                    "suggested_field_id": field_id,
                    "type_guess": type_guess,
                    "non_empty_count": len(non_empty),
                    "coverage_pct": round(len(non_empty) / row_count, 4) if row_count else 0,
                    "unique_count": int(pd.Series(non_empty).nunique(dropna=True)) if non_empty else 0,
                    "sample_values": samples,
                    "semantic_hints": SEMANTIC_HINTS.get(field_id, []),
                    "allowed_ops_suggestion": self._allowed_ops(type_guess),
                    "registry_action_suggestion": self._registry_action(field_id, type_guess),
                }
            )
        return {
            "workbook": workbook_name,
            "sheet": sheet_name,
            "header_row": header_row,
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "methodology_note": (
                "This profile is a field catalog for human review. A column is not executable "
                "until it is promoted into schema_registry.json with allowed operators and notes."
            ),
        }

    def _samples(self, values: list[Any]) -> list[str]:
        samples = []
        seen = set()
        for value in values:
            text = clean_text(value)
            if not text or text in seen:
                continue
            seen.add(text)
            samples.append(text[:120])
            if len(samples) >= self.max_samples:
                break
        return samples

    def _type_guess(self, values: list[Any], samples: list[str]) -> str:
        if not values:
            return "mostly_empty"
        numeric = [parse_number(value) for value in values[:1000]]
        numeric_count = sum(1 for value in numeric if value is not None)
        numeric_ratio = numeric_count / min(len(values), 1000)
        if numeric_ratio >= 0.95:
            if all(isinstance(value, (int, float)) for value in values[: min(len(values), 100)]):
                return "number"
            return "number_from_string"
        if len(set(samples)) <= 20 and max((len(sample) for sample in samples), default=0) <= 30:
            return "enum_or_category"
        if max((len(sample) for sample in samples), default=0) > 60:
            return "long_text"
        return "string"

    def _allowed_ops(self, type_guess: str) -> list[str]:
        if type_guess in {"number", "number_from_string"}:
            return ["eq", "<=", ">=", "between", "sort"]
        if type_guess == "enum_or_category":
            return ["eq", "in", "not_in"]
        if type_guess in {"string", "long_text"}:
            return ["contains", "eq"]
        return []

    def _registry_action(self, field_id: str, type_guess: str) -> str:
        if type_guess == "mostly_empty":
            return "review_before_use"
        if field_id.startswith("column_"):
            return "needs_field_id_review"
        return "candidate_for_schema_registry"


def build_markdown_report(profile: dict[str, Any]) -> str:
    lines = [
        "# Excel Schema Profile",
        "",
        "This report is generated automatically from the workbook. It is not an executable schema by itself.",
        "",
        f"- Workbook: `{profile['workbook']}`",
        f"- Sheet: `{profile['sheet']}`",
        f"- Header row: `{profile['header_row']}`",
        f"- Data rows: `{profile['row_count']}`",
        f"- Columns profiled: `{profile['column_count']}`",
        "",
        "## Methodology",
        "",
        "The system should not inspect every row manually. Instead, it should:",
        "",
        "1. Detect the real header row.",
        "2. Profile every column automatically.",
        "3. Generate a field catalog with types, coverage, examples, and semantic hints.",
        "4. Let a human promote only trusted fields into `schema_registry.json`.",
        "5. Keep unsupported preferences non-executable until a verified field exists.",
        "",
        "## Field Catalog",
        "",
        "| # | Source column | Suggested field ID | Type | Coverage | Unique | Registry action | Samples |",
        "|---:|---|---|---|---:|---:|---|---|",
    ]
    for column in profile["columns"]:
        samples = "<br>".join(column["sample_values"][:3]).replace("|", "\\|")
        lines.append(
            "| {idx} | `{source}` | `{field}` | `{typ}` | {coverage:.1%} | {unique} | `{action}` | {samples} |".format(
                idx=column["column_index"],
                source=column["source_column"],
                field=column["suggested_field_id"],
                typ=column["type_guess"],
                coverage=column["coverage_pct"],
                unique=column["unique_count"],
                action=column["registry_action_suggestion"],
                samples=samples,
            )
        )
    lines.extend(
        [
            "",
            "## Important Consequence",
            "",
            "Some user preferences that were previously treated as missing may actually have candidate columns:",
            "",
            "- `公办` may map to `公私性质` after verification.",
            "- `学校好一点` or `学校名气` may map to `院校水平`, `院校排名`, `院校标签`, or `软科排名`, but only after policy review.",
            "- `城市不要太差` or `偏远` may map to `城市水平标签`, but only after confirming the semantics.",
            "- `中外合作` still needs careful handling; it should not be inferred from free text until a dedicated or verified derived field exists.",
            "",
            "The next step is not to execute all these fields automatically. The next step is to review and promote safe fields into the schema registry with allowed operators and trace notes.",
        ]
    )
    return "\n".join(lines) + "\n"
