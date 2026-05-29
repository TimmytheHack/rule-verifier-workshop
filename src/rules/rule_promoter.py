"""Promotion of confirmed candidate rules."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class RulePromoter:
    """Promotes candidate rules only when simulated confirmation is explicitly enabled."""

    def __init__(self, taxonomy_path: str | Path, simulated_confirmation_enabled: bool) -> None:
        self.taxonomy = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
        self.simulated_confirmation_enabled = simulated_confirmation_enabled

    def final_executable_rules(self, classified_rules: dict[str, Any]) -> list[dict[str, Any]]:
        executable_rules = []
        for rule in classified_rules["deterministic_rules"]:
            if not rule["verification"]["executable"]:
                continue
            executable_rules.append(
                {
                    "rule_id": rule["rule_id"].replace("d_", "e_", 1),
                    "derived_from": rule["rule_id"],
                    "field": rule["field"],
                    "operator": rule["operator"],
                    "value": rule["value"],
                }
            )

        if self.simulated_confirmation_enabled:
            executable_rules.extend(copy.deepcopy(self.taxonomy["confirmed_candidate_rules"]))

        return executable_rules
