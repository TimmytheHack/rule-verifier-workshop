"""Attribute-level schema grounding for extracted preferences.

This layer audits extracted slots before rule construction. It does not execute
anything; it explains whether an extracted attribute can be grounded to the
current Excel schema, is context-only, requires confirmation, or is unsupported.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.adapters.data_warehouse import SchemaValueIndex
from src.schema.schema_registry import SchemaRegistry


DEFAULT_POLICY_PATH = Path("schemas/attribute_grounding.json")


def _value_at(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


class AttributeGrounder:
    """Audits extracted attributes against the active schema registry."""

    def __init__(
        self,
        schema_registry: SchemaRegistry,
        policy_path: str | Path = DEFAULT_POLICY_PATH,
        value_index: SchemaValueIndex | None = None,
    ) -> None:
        self.schema_registry = schema_registry
        self.value_index = value_index
        payload = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        self.slot_policies = {
            tuple(path.split(".")): policy
            for path, policy in payload["slot_policies"].items()
        }
        self.other_vague_policies = payload["other_vague_policies"]

    def ground(self, slots: dict[str, Any]) -> dict[str, Any]:
        records = []
        known_paths = set(self.slot_policies)
        known_paths.add(("preferences", "other_vague_preferences"))
        for path, policy in self.slot_policies.items():
            value = _value_at(slots, path)
            if not _present(value):
                continue
            records.append(self._record(".".join(path), value, policy))

        for term in (slots.get("preferences") or {}).get("other_vague_preferences") or []:
            policy = self.other_vague_policies.get(
                term,
                {"field_id": None, "status": "unmapped_attribute", "reason": "没有属性接地策略。"},
            )
            records.append(self._record("preferences.other_vague_preferences[]", term, policy))

        records.extend(self._unknown_preference_records(slots, known_paths))
        return {
            "attributes": records,
            "summary": self._summary(records),
        }

    def _record(self, slot_path: str, value: Any, policy: dict[str, Any]) -> dict[str, Any]:
        field_id = policy.get("field_id")
        field_exists = self.schema_registry.has_field(field_id)
        configured = self.schema_registry.configured_fields.get(field_id or "", {})
        source_column = configured.get("source_column")
        source_column_exists = bool(field_exists and source_column)
        requires_confirmation = bool(policy.get("requires_human_confirmation", False))
        explicit_status = policy.get("status")

        if explicit_status:
            status = explicit_status
        elif policy.get("attribute_class") == "context_only":
            status = "context_only"
        elif field_exists and requires_confirmation:
            status = "confirmable"
        elif field_exists:
            status = "schema_grounded"
        else:
            status = "missing_schema"

        execution_allowed = status == "schema_grounded"
        return {
            "slot_path": slot_path,
            "value": value,
            "field_id": field_id,
            "source_column": source_column,
            "field_exists_in_excel_schema": field_exists,
            "source_column_exists": source_column_exists,
            "attribute_class": policy.get("attribute_class", status),
            "requires_human_confirmation": requires_confirmation or status == "confirmable",
            "status": status,
            "execution_allowed_without_rule_verification": False,
            "can_become_executable_rule": execution_allowed or status == "confirmable",
            "reason": policy.get("reason", self._reason(status)),
            "value_index_audit": self._value_index_audit(field_id, value),
        }

    def _unknown_preference_records(
        self,
        slots: dict[str, Any],
        known_paths: set[tuple[str, ...]],
    ) -> list[dict[str, Any]]:
        records = []
        for parent_key in ["user_context", "preferences"]:
            section = slots.get(parent_key) or {}
            if not isinstance(section, dict):
                continue
            for key, value in section.items():
                path = (parent_key, key)
                if path in known_paths or not _present(value):
                    continue
                records.append(
                    {
                        "slot_path": ".".join(path),
                        "value": value,
                        "field_id": None,
                        "source_column": None,
                        "field_exists_in_excel_schema": False,
                        "source_column_exists": False,
                        "attribute_class": "unrecognized_extractor_output",
                        "requires_human_confirmation": False,
                        "status": "ignored_not_schema_mapped",
                        "execution_allowed_without_rule_verification": False,
                        "can_become_executable_rule": False,
                        "reason": "抽取器输出了未登记属性，规则构造会忽略它。",
                    }
                )
        return records

    def _summary(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = {}
        for record in records:
            statuses[record["status"]] = statuses.get(record["status"], 0) + 1
        value_statuses = {}
        for record in records:
            value_audit = record.get("value_index_audit") or {}
            status = value_audit.get("status")
            if not status:
                continue
            value_statuses[status] = value_statuses.get(status, 0) + 1
        unsafe = [
            record
            for record in records
            if record["execution_allowed_without_rule_verification"]
            and not record["field_exists_in_excel_schema"]
        ]
        return {
            "total_attributes": len(records),
            "status_counts": statuses,
            "value_index_status_counts": value_statuses,
            "unsafe_ungrounded_executable_attributes": len(unsafe),
        }

    def _value_index_audit(
        self,
        field_id: str | None,
        value: Any,
    ) -> dict[str, Any] | None:
        if self.value_index is None or not field_id:
            return None
        return self.value_index.audit_value(field_id, value)

    def _reason(self, status: str) -> str:
        if status == "schema_grounded":
            return "该属性已映射到当前数据字段，但仍需经过规则验证。"
        if status == "confirmable":
            return "该属性有对应字段，但语义或边界需要确认。"
        if status == "context_only":
            return "该属性只作为上下文，不能直接作为筛表条件。"
        if status == "missing_schema":
            return "当前数据中没有可执行字段，不能进入筛表。"
        return "该属性不可执行。"
