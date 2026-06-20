"""家庭资源和就业偏好的确定性解释层。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


def career_guidance_for_query(
    user_request: str,
    slots: dict[str, Any] | None,
    domain_config: DomainConfig | None = None,
) -> dict[str, Any]:
    """匹配 reviewed career policy，返回不参与 SQL 的证据。"""

    domain_config = domain_config or DomainConfig.load()
    policy_path = domain_config.career_decision_policy_path
    if policy_path is None or not policy_path.exists():
        return _empty_guidance()
    policy = _load_policy(str(policy_path))
    if policy.get("status") != "approved":
        return _empty_guidance()
    matched_rules = []
    information_requests = []
    no_schema_preferences = []
    for rule in policy.get("rules") or []:
        if not _rule_matches(rule, user_request, slots or {}):
            continue
        matched_rules.append(
            {
                "rule_id": rule["rule_id"],
                "label": rule["label"],
                "effect": policy.get(
                    "execution_effect",
                    "does_not_change_sql_or_results",
                ),
            }
        )
        information_requests.extend(
            _request_with_rule_id(rule["rule_id"], item)
            for item in rule.get("information_requests") or []
        )
        no_schema_preferences.extend(
            _preference_with_rule_id(rule["rule_id"], item)
            for item in rule.get("no_schema_field_preferences") or []
        )
    return {
        "status": "reference_only",
        "execution_effect": policy.get(
            "execution_effect",
            "does_not_change_sql_or_results",
        ),
        "executable": False,
        "matched_rules": matched_rules,
        "information_requests": _dedupe_by_key(information_requests, "question_id"),
        "no_schema_field_preferences": _dedupe_by_pair(
            no_schema_preferences,
            "field_id",
            "source_text",
        ),
    }


@lru_cache(maxsize=16)
def _load_policy(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _empty_guidance() -> dict[str, Any]:
    return {
        "status": "reference_only",
        "execution_effect": "does_not_change_sql_or_results",
        "executable": False,
        "matched_rules": [],
        "information_requests": [],
        "no_schema_field_preferences": [],
    }


def _rule_matches(
    rule: dict[str, Any],
    user_request: str,
    slots: dict[str, Any],
) -> bool:
    trigger_terms = [str(term) for term in rule.get("trigger_terms") or []]
    term_matched = _trigger_terms_match(trigger_terms, user_request)
    slot_matched = _slot_trigger_matches(rule.get("trigger_slots") or {}, slots)
    return term_matched and slot_matched


def _trigger_terms_match(trigger_terms: list[str], user_request: str) -> bool:
    if not trigger_terms:
        return True
    return any(_positive_term_present(user_request, term) for term in trigger_terms)


def _positive_term_present(text: str, term: str) -> bool:
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return False
        if not _term_is_negated(text, index, len(term)):
            return True
        start = index + len(term)


def _term_is_negated(
    text: str,
    term_index: int,
    term_length: int = 0,
) -> bool:
    clause_start = (
        max(text.rfind(punctuation, 0, term_index) for punctuation in "，。,.；;")
        + 1
    )
    suffix_start = term_index + term_length
    clause_ends = [
        text.find(punctuation, suffix_start)
        for punctuation in "，。,.；;"
        if text.find(punctuation, suffix_start) >= 0
    ]
    clause_end = min(clause_ends) if clause_ends else len(text)
    prefix = _prefix_after_boundary(text[clause_start:term_index])
    suffix = _suffix_before_boundary(text[suffix_start:clause_end])
    prefix_markers = [
        "不优先考虑",
        "不优先看重",
        "不优先选择",
        "不要求",
        "不需要",
        "不用考虑",
        "不想",
        "不考虑",
        "不要",
        "不看重",
        "无需",
    ]
    suffix_markers = [
        "不重要",
        "不看重",
        "不是重点",
        "无所谓",
        "不优先",
    ]
    return any(marker in prefix for marker in prefix_markers) or any(
        marker in suffix[:10]
        for marker in suffix_markers
    )


def _prefix_after_boundary(prefix: str) -> str:
    boundary_ends = []
    for marker in ["但是", "不过", "只是", "但"]:
        start = 0
        while True:
            index = prefix.find(marker, start)
            if index < 0:
                break
            if _contrast_marker_is_negated(prefix, index, marker):
                start = index + len(marker)
                continue
            boundary_ends.append(index + len(marker))
            start = index + len(marker)
    if not boundary_ends:
        return prefix
    return prefix[max(boundary_ends):]


def _suffix_before_boundary(suffix: str) -> str:
    boundary_indexes = []
    for marker in ["但是", "不过", "只是", "但"]:
        start = 0
        while True:
            index = suffix.find(marker, start)
            if index < 0:
                break
            if _contrast_marker_is_negated(suffix, index, marker):
                start = index + len(marker)
                continue
            boundary_indexes.append(index)
            break
    if not boundary_indexes:
        return suffix
    return suffix[:min(boundary_indexes)]


def _contrast_marker_is_negated(text: str, index: int, marker: str) -> bool:
    return marker in {"但", "但是"} and index > 0 and text[index - 1] == "不"


def _slot_trigger_matches(
    trigger_slots: dict[str, list[str]],
    slots: dict[str, Any],
) -> bool:
    if not trigger_slots:
        return True
    for path, expected_values in trigger_slots.items():
        value = _value_at(slots, path.split("."))
        if value is None:
            continue
        text = str(value)
        if any(str(expected) in text for expected in expected_values):
            return True
    return False


def _value_at(payload: dict[str, Any], path: list[str]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _request_with_rule_id(rule_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"rule_id": rule_id, **dict(item)}


def _preference_with_rule_id(rule_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"rule_id": rule_id, **dict(item)}


def _dedupe_by_key(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        value = item.get(key)
        if value in seen:
            continue
        seen.add(value)
        result.append(item)
    return result


def _dedupe_by_pair(
    items: list[dict[str, Any]],
    first_key: str,
    second_key: str,
) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = (item.get(first_key), item.get(second_key))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
