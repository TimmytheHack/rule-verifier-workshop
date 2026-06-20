"""受控排位窗口和排序选项建议；只进 EvidencePack，不参与执行。"""

from __future__ import annotations

from typing import Any


def decision_option_suggestions_for_query(
    user_request: str,
    slots: dict[str, Any],
) -> dict[str, Any]:
    text = user_request or ""
    preferences = slots.get("preferences") or {}
    suggestions: dict[str, dict[str, Any]] = {}

    if any(term in text for term in ["稳一点", "稳妥", "保守一点"]):
        suggestions["rank_window"] = {
            "suggested_value": "steady",
            "label": "稳一点",
            "reason": "用户表达了稳妥偏好，但必须由前端控件确认后才执行。",
        }
        suggestions["sort_mode"] = {
            "suggested_value": "rank_desc",
            "label": "按历史位次从低到高看（更稳）",
            "reason": "稳妥偏好通常需要先看更有余量的结果，但排序也必须由用户确认。",
        }
    elif preferences.get("recommendation_request_raw"):
        suggestions["rank_window"] = {
            "suggested_value": "steady",
            "label": "稳一点",
            "reason": "推荐请求需要先选择排位范围，默认建议从稳一点开始确认。",
        }
        suggestions["sort_mode"] = {
            "suggested_value": "rank_asc",
            "label": "按历史位次从高到低看（更冲）",
            "reason": "未表达保守偏好时，可以先按历史位次从高到低浏览。",
        }

    return {
        "status": "reference_only",
        "execution_effect": "does_not_change_sql_or_results",
        "executable": False,
        "source": "fixed_policy",
        "suggestions": suggestions,
    }
