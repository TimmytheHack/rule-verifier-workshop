"""家庭资源和就业偏好的确定性解释层。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


EMPTY_GUIDANCE = {
    "status": "reference_only",
    "execution_effect": "does_not_change_sql_or_results",
    "executable": False,
    "matched_rules": [],
    "information_requests": [],
    "no_schema_field_preferences": [],
}


def career_guidance_for_query(
    user_request: str,
    slots: dict[str, Any] | None,
    domain_config: DomainConfig | None = None,
) -> dict[str, Any]:
    """匹配 reviewed career policy，返回不参与 SQL 的证据。"""

    domain_config = domain_config or DomainConfig.load()
    policy_path = domain_config.career_decision_policy_path
    if policy_path is None or not policy_path.exists():
        return dict(EMPTY_GUIDANCE)
    policy = _load_policy(str(policy_path))
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


def _rule_matches(
    rule: dict[str, Any],
    user_request: str,
    slots: dict[str, Any],
) -> bool:
    trigger_terms = [str(term) for term in rule.get("trigger_terms") or []]
    term_matched = not trigger_terms or any(
        term in user_request
        for term in trigger_terms
    )
    slot_matched = _slot_trigger_matches(rule.get("trigger_slots") or {}, slots)
    return term_matched and slot_matched


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
