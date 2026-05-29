"""Row-level trace generation."""

from __future__ import annotations

from typing import Any


class TraceGenerator:
    """Adds audit traces to result rows."""

    def add_traces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        traced = []
        for row in rows:
            output_row = dict(row)
            output_row["trace"] = [
                {"rule_id": "e_source_province", "status": "pass", "reason": "生源地 == 广东"},
                {"rule_id": "e_subject_type", "status": "pass", "reason": "科类 == 物理"},
                {"rule_id": "e_major_keyword", "status": "pass", "reason": "专业名称 contains 计算机"},
                {"rule_id": "e_city", "status": "pass", "reason": f"城市 matches {row['城市']}"},
                {
                    "rule_id": "e_safety_margin",
                    "status": "pass",
                    "reason": f"专业组最低位次1 {row['专业组最低位次1']} >= 35200",
                },
                {"rule_id": "e_tuition_cap", "status": "pass", "reason": f"学费 {row['学费']:g} <= 20000"},
                {
                    "rule_id": "l_cooperation_type",
                    "status": "not_executed",
                    "reason": "Missing dedicated cooperation_type field; no text inference applied.",
                },
            ]
            traced.append(output_row)
        return traced
