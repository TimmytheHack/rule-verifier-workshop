"""Promotion of confirmed candidate rules."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


class RulePromoter:
    """Promotes candidate rules only when simulated confirmation is explicitly enabled."""

    def __init__(
        self,
        taxonomy_path: str | Path,
        simulated_confirmation_enabled: bool,
        domain_config: DomainConfig | None = None,
    ) -> None:
        self.taxonomy = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
        self.simulated_confirmation_enabled = simulated_confirmation_enabled
        self.domain_config = domain_config or DomainConfig.load()

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
            candidate_rule_ids = {
                rule["rule_id"] for rule in classified_rules.get("candidate_rules", [])
            }
            simulated = classified_rules.get("simulated_confirmations", {})
            for rule in self.taxonomy["confirmed_candidate_rules"]:
                if rule.get("derived_from") not in candidate_rule_ids:
                    continue
                if rule.get("derived_from") == "c_safety_margin" and "safety_margin" not in simulated:
                    continue
                if rule.get("derived_from") == "c_tuition_cap" and "tuition_threshold" not in simulated:
                    continue
                if (
                    rule.get("derived_from") == "c_recommendation_rank_floor"
                    and "recommendation_rank_floor" not in simulated
                ):
                    continue
                promoted_rule = copy.deepcopy(rule)
                promoted_rule = self.domain_config.canonicalize_rule_field(promoted_rule)
                if promoted_rule["rule_id"] == "e_recommendation_rank_floor":
                    confirmation = simulated.get("recommendation_rank_floor", {})
                    promoted_rule["operator"] = confirmation.get(
                        "operator",
                        promoted_rule["operator"],
                    )
                    promoted_rule["value"] = confirmation.get("value", promoted_rule["value"])
                    promoted_rule["confirmation"] = "基本可达边界已确认"
                if promoted_rule["rule_id"] == "e_safety_margin":
                    confirmation = simulated.get("safety_margin", {})
                    promoted_rule["operator"] = confirmation.get(
                        "operator",
                        promoted_rule["operator"],
                    )
                    promoted_rule["value"] = confirmation.get("value", promoted_rule["value"])
                    promoted_rule["confirmation"] = "位次窗口已确认"
                if promoted_rule["rule_id"] == "e_tuition_cap":
                    confirmation = simulated.get("tuition_threshold", {})
                    promoted_rule["value"] = confirmation.get("value", promoted_rule["value"])
                executable_rules.append(promoted_rule)

        return executable_rules
