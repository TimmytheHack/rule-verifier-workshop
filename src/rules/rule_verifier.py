"""Deterministic verifier for preference-derived rules."""

from __future__ import annotations

from typing import Any

from src.schema.schema_registry import SchemaRegistry


class RuleVerifier:
    """Verifies whether a rule is executable without using an LLM."""

    def __init__(self, schema_registry: SchemaRegistry) -> None:
        self.schema_registry = schema_registry

    def verify(self, rule: dict[str, Any]) -> dict[str, Any]:
        category = rule.get("category")
        if category == "context":
            return {
                "field_exists": True,
                "operator_allowed": True,
                "ambiguity_detected": False,
                "requires_human_confirmation": False,
                "executable": False,
            }

        field_id = rule.get("field_id")
        field_exists = self.schema_registry.has_field(field_id)
        operator_allowed = field_exists and rule.get("operator") in self.schema_registry.field(field_id)["allowed_ops"]
        ambiguity_detected = category == "candidate"
        requires_confirmation = bool(rule.get("requires_human_confirmation", False))
        value_present = self._value_present(rule.get("value"))
        executable = field_exists and operator_allowed and value_present and not ambiguity_detected and not requires_confirmation
        return {
            "field_exists": field_exists,
            "operator_allowed": operator_allowed,
            "value_present": value_present,
            "ambiguity_detected": ambiguity_detected,
            "requires_human_confirmation": requires_confirmation,
            "executable": executable,
        }

    def attach_verification(self, rule: dict[str, Any]) -> dict[str, Any]:
        verified = dict(rule)
        verification = self.verify(verified)
        verified["verification"] = verification
        if verified.get("category") == "deterministic":
            verified["status"] = "verified" if verification["executable"] else "blocked"
        return verified

    def _value_present(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if isinstance(value, list) and not value:
            return False
        return True
