"""Rule classifier for the fixed MVP taxonomy."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.rules.rule_verifier import RuleVerifier


def _slot_value(slots: dict[str, Any], path: list[str]) -> Any:
    value: Any = slots
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


class RuleClassifier:
    """Builds rule classes from extracted slots and taxonomy config."""

    def __init__(self, taxonomy_path: str | Path, verifier: RuleVerifier) -> None:
        self.taxonomy = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
        self.verifier = verifier

    def classify(self, slots: dict[str, Any]) -> dict[str, Any]:
        deterministic_rules = []
        for template in self.taxonomy["deterministic_rules"]:
            rule = copy.deepcopy(template)
            rule["value"] = _slot_value(slots, rule.pop("slot_path"))
            if rule.pop("skip_if_missing", False) and not _value_present(rule["value"]):
                continue
            deterministic_rules.append(self.verifier.attach_verification(rule))

        context_rules = []
        for template in self.taxonomy["context_rules"]:
            rule = copy.deepcopy(template)
            rule["value"] = _slot_value(slots, rule.pop("slot_path"))
            context_rules.append(self.verifier.attach_verification(rule))

        candidate_rules = []
        for template in self.taxonomy["candidate_rules"]:
            rule = copy.deepcopy(template)
            slot_path = rule.pop("slot_path", None)
            if slot_path:
                rule["value"] = _slot_value(slots, slot_path)
                if rule.pop("skip_if_missing", False) and not _value_present(rule["value"]):
                    continue
            candidate_rules.append(self.verifier.attach_verification(rule))

        llm_needed_parts = []
        for part in self.taxonomy["llm_needed_parts"]:
            if not _llm_needed_part_is_relevant(part, slots):
                continue
            item = copy.deepcopy(part)
            source_text = _llm_needed_source_text(item, slots)
            if source_text:
                item["source_text"] = source_text
            item["verification"] = {
                "field_exists": self.verifier.schema_registry.has_field(item.get("field_id")),
                "schema_grounded": False,
                "executable": False,
            }
            llm_needed_parts.append(item)

        candidate_rule_ids = {rule["rule_id"] for rule in candidate_rules}
        llm_needed_part_ids = {part["part_id"] for part in llm_needed_parts}

        return {
            "deterministic_rules": deterministic_rules,
            "context_rules": context_rules,
            "candidate_rules": candidate_rules,
            "llm_needed_parts": llm_needed_parts,
            "confirmation_questions": _relevant_confirmation_questions(
                self.taxonomy["confirmation_questions"],
                candidate_rule_ids,
            ),
            "simulated_confirmations": _relevant_simulated_confirmations(
                self.taxonomy["simulated_confirmations"],
                candidate_rule_ids,
                llm_needed_part_ids,
                slots,
            ),
            "non_executable_preferences": _relevant_non_executable_preferences(
                self.taxonomy["non_executable_preferences"],
                llm_needed_part_ids,
                slots,
            ),
        }


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


def _llm_needed_part_is_relevant(part: dict[str, Any], slots: dict[str, Any]) -> bool:
    if part.get("part_id") == "l_cooperation_type":
        return _value_present(_slot_value(slots, ["preferences", "cooperation_preference_raw"]))
    if part.get("part_id") == "l_overseas_scope":
        return _value_present(_slot_value(slots, ["preferences", "overseas_preference_raw"]))
    return True


def _llm_needed_source_text(part: dict[str, Any], slots: dict[str, Any]) -> str | None:
    if part.get("part_id") == "l_cooperation_type":
        return _slot_value(slots, ["preferences", "cooperation_preference_raw"])
    if part.get("part_id") == "l_overseas_scope":
        return _slot_value(slots, ["preferences", "overseas_preference_raw"])
    return None


def _relevant_confirmation_questions(
    questions: list[dict[str, Any]],
    candidate_rule_ids: set[str],
) -> list[dict[str, Any]]:
    question_by_candidate = {
        "q_recommendation_rank_floor": "c_recommendation_rank_floor",
        "q_safety_margin": "c_safety_margin",
        "q_tuition_cap": "c_tuition_cap",
        "q_major_expansion": "c_major_expansion",
    }
    return [
        copy.deepcopy(question)
        for question in questions
        if question_by_candidate.get(question["question_id"]) in candidate_rule_ids
    ]


def _relevant_simulated_confirmations(
    confirmations: dict[str, Any],
    candidate_rule_ids: set[str],
    llm_needed_part_ids: set[str],
    slots: dict[str, Any],
) -> dict[str, Any]:
    confirmation_by_candidate = {
        "recommendation_rank_floor": "c_recommendation_rank_floor",
        "safety_margin": "c_safety_margin",
        "tuition_threshold": "c_tuition_cap",
        "major_expansion": "c_major_expansion",
    }
    relevant = {
        confirmation_id: copy.deepcopy(confirmation)
        for confirmation_id, confirmation in confirmations.items()
        if confirmation_by_candidate.get(confirmation_id) in candidate_rule_ids
    }
    if "safety_margin" in relevant:
        rank = _slot_value(slots, ["user_context", "user_rank"])
        if isinstance(rank, (int, float)):
            lower_bound = max(1, int(rank * 0.9))
            upper_bound = int(rank * 1.1)
            relevant["safety_margin"]["operator"] = "between"
            relevant["safety_margin"]["value"] = [lower_bound, upper_bound]
            relevant["safety_margin"]["source_expression"] = (
                f"{rank} * 0.90 到 {rank} * 1.10"
            )
    if "recommendation_rank_floor" in relevant:
        rank = _slot_value(slots, ["user_context", "user_rank"])
        if isinstance(rank, (int, float)):
            relevant["recommendation_rank_floor"]["operator"] = ">="
            relevant["recommendation_rank_floor"]["value"] = int(rank)
            relevant["recommendation_rank_floor"]["source_expression"] = f"用户排位 {rank}"
        else:
            relevant.pop("recommendation_rank_floor")
    if "l_cooperation_type" in llm_needed_part_ids and "cooperation_type" in confirmations:
        relevant["cooperation_type"] = copy.deepcopy(confirmations["cooperation_type"])
    return relevant


def _relevant_non_executable_preferences(
    preferences: list[dict[str, Any]],
    llm_needed_part_ids: set[str],
    slots: dict[str, Any],
) -> list[dict[str, Any]]:
    relevant = []
    for preference in preferences:
        if preference.get("part_id") not in llm_needed_part_ids:
            continue
        item = copy.deepcopy(preference)
        source_text = _llm_needed_source_text(item, slots)
        if source_text:
            item["source_text"] = source_text
        relevant.append(item)
    return relevant
