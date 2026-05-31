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
                "schema_grounded": True,
                "field_exists": True,
                "source_column_exists": True,
                "operator_allowed": True,
                "type_valid": True,
                "value_present": self._value_present(rule.get("value")),
                "value_normalized": True,
                "ambiguity_detected": False,
                "ambiguity_level": "none",
                "requires_human_confirmation": False,
                "execution_level": "context_only",
                "executable": False,
            }

        field_id = rule.get("field_id")
        field_exists = self.schema_registry.has_field(field_id)
        field = self.schema_registry.field(field_id) if field_exists else {}
        source_column_exists = bool(field.get("source_column"))
        schema_grounded = field_exists and source_column_exists
        operator_allowed = field_exists and rule.get("operator") in field["allowed_ops"]
        ambiguity_detected = category == "candidate"
        ambiguity_level = "medium" if ambiguity_detected else "none"
        requires_confirmation = bool(rule.get("requires_human_confirmation", False))
        value_present = self._value_present(rule.get("value"))
        type_valid = field_exists
        value_normalized = value_present
        executable = (
            schema_grounded
            and operator_allowed
            and type_valid
            and value_normalized
            and not ambiguity_detected
            and not requires_confirmation
        )
        execution_level = self._execution_level(
            category=category,
            schema_grounded=schema_grounded,
            executable=executable,
            requires_confirmation=requires_confirmation,
            ambiguity_detected=ambiguity_detected,
        )
        return {
            "schema_grounded": schema_grounded,
            "field_exists": field_exists,
            "source_column_exists": source_column_exists,
            "operator_allowed": operator_allowed,
            "type_valid": type_valid,
            "value_present": value_present,
            "value_normalized": value_normalized,
            "ambiguity_detected": ambiguity_detected,
            "ambiguity_level": ambiguity_level,
            "requires_human_confirmation": requires_confirmation,
            "execution_level": execution_level,
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

    def _execution_level(
        self,
        category: str | None,
        schema_grounded: bool,
        executable: bool,
        requires_confirmation: bool,
        ambiguity_detected: bool,
    ) -> str:
        if executable:
            return "executable"
        if category == "candidate" and schema_grounded and (requires_confirmation or ambiguity_detected):
            return "confirmable"
        if not schema_grounded:
            return "rejected"
        return "blocked"
