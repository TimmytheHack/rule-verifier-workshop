"""Deterministic verifier for preference-derived rules."""

from __future__ import annotations

from typing import Any

from src.domains import DomainConfig
from src.schema.schema_registry import SchemaRegistry


AMBIGUOUS_SEMANTIC_TYPES = {
    "vague_preference",
    "semantic_expansion",
    "external_info",
    "unsupported_structured_preference",
    "inferred_proxy",
}

class RuleVerifier:
    """Verifies whether a rule is executable without using an LLM."""

    def __init__(
        self,
        schema_registry: SchemaRegistry,
        domain_config: DomainConfig | None = None,
    ) -> None:
        self.schema_registry = schema_registry
        self.domain_config = domain_config or DomainConfig.load()

    def verify(self, rule: dict[str, Any]) -> dict[str, Any]:
        rule = self._canonical_rule(rule)
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
                "terminal_status": "context_only",
                "executable": False,
            }

        field_id = rule.get("field_id")
        field_exists = self.schema_registry.has_field(field_id)
        field = (
            self.schema_registry.field(field_id)
            if field_exists
            else self.schema_registry.configured_field(field_id)
        )
        source_column_exists = bool(field.get("source_column"))
        schema_grounded = field_exists and source_column_exists
        operator_allowed = field_exists and rule.get("operator") in field.get("allowed_ops", [])
        semantic_ambiguity = self._semantic_ambiguity_detected(rule)
        ambiguity_detected = category == "candidate" or semantic_ambiguity
        ambiguity_level = self._ambiguity_level(
            category=category,
            semantic_ambiguity=semantic_ambiguity,
        )
        requires_confirmation = bool(
            rule.get("requires_human_confirmation", False) or semantic_ambiguity
        )
        value_present = self._value_present(rule.get("value"))
        value_check = self._value_check(
            rule=rule,
            field=field,
            field_exists=field_exists,
            value_present=value_present,
            requires_confirmation=requires_confirmation,
        )
        type_valid = value_check["type_valid"]
        value_normalized = value_check["value_normalized"]
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
            operator_allowed=operator_allowed,
            value_present=value_present,
            type_valid=type_valid,
        )
        terminal_status = self._terminal_status(
            category=category,
            schema_grounded=schema_grounded,
            operator_allowed=operator_allowed,
            value_present=value_present,
            type_valid=type_valid,
            value_normalized=value_normalized,
            ambiguity_detected=ambiguity_detected,
            requires_confirmation=requires_confirmation,
            executable=executable,
        )
        return {
            "schema_grounded": schema_grounded,
            "field_exists": field_exists,
            "source_column_exists": source_column_exists,
            "operator_allowed": operator_allowed,
            "type_valid": type_valid,
            "value_present": value_present,
            "value_normalized": value_normalized,
            "normalized_value": value_check.get("normalized_value"),
            "value_error": value_check.get("value_error"),
            "ambiguity_detected": ambiguity_detected,
            "ambiguity_level": ambiguity_level,
            "requires_human_confirmation": requires_confirmation,
            "execution_level": execution_level,
            "terminal_status": terminal_status,
            "executable": executable,
        }

    def attach_verification(self, rule: dict[str, Any]) -> dict[str, Any]:
        verified = dict(rule)
        verification = self.verify(verified)
        verified["verification"] = verification
        if verified.get("category") == "deterministic":
            verified["status"] = "verified" if verification["executable"] else "blocked"
        return verified

    def audit_proposed_rules(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Verify LLM-proposed rule shapes without trusting LLM executability."""

        audited = []
        for index, rule in enumerate(rules, start=1):
            audited.append(self.attach_proposed_verification(rule, index=index))
        return audited

    def attach_proposed_verification(
        self,
        rule: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        """Attach symbolic verification to one LLM/adapter proposed rule."""

        proposed = self._canonical_proposed_rule(rule, index=index)
        verification = self.verify(proposed)
        proposed["verification"] = verification
        proposed["status"] = verification["terminal_status"]
        return proposed

    def _value_present(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if isinstance(value, list) and not value:
            return False
        return True

    def _canonical_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        field_id = self.schema_registry.resolve_field_id(
            field_id=rule.get("field_id"),
            source_column=rule.get("field") or rule.get("source_column"),
        )
        if field_id == rule.get("field_id"):
            return rule
        canonical = dict(rule)
        canonical["field_id"] = field_id
        return canonical

    def _canonical_proposed_rule(
        self,
        rule: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        field_id = self.schema_registry.resolve_field_id(
            field_id=rule.get("field_id"),
            source_column=rule.get("field") or rule.get("source_column"),
        )
        configured = self.schema_registry.configured_field(field_id)
        category = str(rule.get("category") or "deterministic")
        if category not in {"deterministic", "candidate", "context", "explain_only"}:
            category = "candidate" if rule.get("requires_human_confirmation") else "deterministic"
        if category == "explain_only":
            category = "candidate"

        return {
            "rule_id": rule.get("rule_id") or f"p_llm_{index:03d}",
            "source_text": rule.get("source_text"),
            "category": category,
            "field_id": field_id,
            "field": rule.get("field") or configured.get("source_column") or field_id,
            "operator": rule.get("operator"),
            "value": rule.get("value"),
            "semantic_type": rule.get("semantic_type") or rule.get("value_source"),
            "value_source": rule.get("value_source"),
            "requires_human_confirmation": bool(
                rule.get("requires_human_confirmation", False)
            ),
            "reason": rule.get("reason"),
            "proposed_by": rule.get("proposed_by", "llm_extractor"),
        }

    def _semantic_ambiguity_detected(self, rule: dict[str, Any]) -> bool:
        semantic_type = str(rule.get("semantic_type") or rule.get("value_source") or "")
        return semantic_type in AMBIGUOUS_SEMANTIC_TYPES

    def _ambiguity_level(
        self,
        category: str | None,
        semantic_ambiguity: bool,
    ) -> str:
        if semantic_ambiguity:
            return "high"
        if category == "candidate":
            return "medium"
        return "none"

    def _value_check(
        self,
        rule: dict[str, Any],
        field: dict[str, Any],
        field_exists: bool,
        value_present: bool,
        requires_confirmation: bool,
    ) -> dict[str, Any]:
        if not field_exists:
            return {
                "type_valid": False,
                "value_normalized": False,
                "normalized_value": None,
                "value_error": "missing_schema",
            }
        if not value_present:
            return {
                "type_valid": False,
                "value_normalized": False,
                "normalized_value": None,
                "value_error": "missing_value",
            }

        if rule.get("category") == "candidate" and requires_confirmation:
            return {
                "type_valid": True,
                "value_normalized": False,
                "normalized_value": None,
                "value_error": "confirmation_value_required",
            }

        value = rule.get("value")
        operator = rule.get("operator")
        field_type = field.get("type")

        if operator == "satisfies_subject_requirement":
            subjects = self._normalized_subjects(value)
            return {
                "type_valid": bool(subjects),
                "value_normalized": bool(subjects),
                "normalized_value": subjects,
                "value_error": None if subjects else "invalid_subject_selection",
            }

        if field_type in {"number", "number_from_string"}:
            if operator == "between":
                values = value if isinstance(value, list) else []
                normalized = [self._number(item) for item in values]
                valid = len(normalized) == 2 and all(item is not None for item in normalized)
                return {
                    "type_valid": valid,
                    "value_normalized": valid,
                    "normalized_value": normalized if valid else None,
                    "value_error": None if valid else "invalid_numeric_range",
                }
            normalized_number = self._number(value)
            valid = normalized_number is not None
            return {
                "type_valid": valid,
                "value_normalized": valid,
                "normalized_value": normalized_number,
                "value_error": None if valid else "invalid_number",
            }

        if operator in {"in_contains", "contains_any", "in", "not_in"}:
            values = value if isinstance(value, list) else [value]
            normalized_values = [
                str(item).strip() for item in values if str(item).strip()
            ]
            return {
                "type_valid": bool(normalized_values),
                "value_normalized": bool(normalized_values),
                "normalized_value": normalized_values,
                "value_error": None if normalized_values else "invalid_list",
            }

        normalized_text = str(value).strip()
        return {
            "type_valid": bool(normalized_text),
            "value_normalized": bool(normalized_text),
            "normalized_value": normalized_text,
            "value_error": None if normalized_text else "invalid_text",
        }

    def _normalized_subjects(self, value: Any) -> list[str]:
        values = value if isinstance(value, list) else [value]
        normalized = []
        policy = self.domain_config.subject_policy
        subjects = policy.get("subjects") or []
        replacements = policy.get("normalization") or {}
        for item in values:
            text = str(item)
            for source, target in replacements.items():
                text = text.replace(source, target)
            for subject in subjects:
                if subject in text and subject not in normalized:
                    normalized.append(subject)
        return normalized[:2]

    def _number(self, value: Any) -> int | float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        text = str(value)
        digits = "".join(char for char in text if char.isdigit() or char == ".")
        if not digits:
            return None
        try:
            parsed = float(digits)
        except ValueError:
            return None
        return int(parsed) if parsed.is_integer() else parsed

    def _execution_level(
        self,
        category: str | None,
        schema_grounded: bool,
        executable: bool,
        requires_confirmation: bool,
        ambiguity_detected: bool,
        operator_allowed: bool,
        value_present: bool,
        type_valid: bool,
    ) -> str:
        if executable:
            return "executable"
        if (
            category == "candidate"
            and schema_grounded
            and operator_allowed
            and value_present
            and type_valid
            and (requires_confirmation or ambiguity_detected)
        ):
            return "confirmable"
        if not schema_grounded:
            return "rejected"
        return "blocked"

    def _terminal_status(
        self,
        category: str | None,
        schema_grounded: bool,
        operator_allowed: bool,
        value_present: bool,
        type_valid: bool,
        value_normalized: bool,
        ambiguity_detected: bool,
        requires_confirmation: bool,
        executable: bool,
    ) -> str:
        if category == "context":
            return "context_only"
        if executable:
            return "executable"
        if not schema_grounded:
            return "rejected_missing_schema"
        if not operator_allowed:
            return "rejected_invalid_operator"
        if not value_present or not type_valid:
            return "rejected_invalid_value"
        if requires_confirmation or ambiguity_detected or not value_normalized:
            return "confirmable"
        return "blocked"
