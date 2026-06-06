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
            item = copy.deepcopy(part)
            item["verification"] = {
                "field_exists": self.verifier.schema_registry.has_field(item.get("field_id")),
                "schema_grounded": False,
                "executable": False,
            }
            llm_needed_parts.append(item)

        return {
            "deterministic_rules": deterministic_rules,
            "context_rules": context_rules,
            "candidate_rules": candidate_rules,
            "llm_needed_parts": llm_needed_parts,
            "confirmation_questions": copy.deepcopy(self.taxonomy["confirmation_questions"]),
            "simulated_confirmations": copy.deepcopy(self.taxonomy["simulated_confirmations"]),
            "non_executable_preferences": copy.deepcopy(self.taxonomy["non_executable_preferences"]),
        }


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True
