"""Schema registry boundary for executable rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


class SchemaRegistry:
    """根据真实字段过滤 schema 配置。

    配置文件可以记录 missing-but-desired 字段；active registry 只包含真实存在的字段。
    """

    def __init__(self, active_fields: dict[str, dict[str, Any]], configured_fields: dict[str, dict[str, Any]]) -> None:
        self.active_fields = active_fields
        self.configured_fields = configured_fields

    @classmethod
    def from_file(cls, path: str | Path, available_columns: list[str]) -> "SchemaRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        configured_fields = payload["fields"]
        available = set(available_columns)
        active_fields = {
            field_id: spec
            for field_id, spec in configured_fields.items()
            if spec.get("source_column") in available and spec.get("status") != "missing"
        }
        return cls(active_fields=active_fields, configured_fields=configured_fields)

    @classmethod
    def from_domain(
        cls,
        domain_config: DomainConfig,
        available_columns: list[str],
    ) -> "SchemaRegistry":
        return cls.from_file(domain_config.schema_path, available_columns)

    def has_field(self, field_id: str | None) -> bool:
        return bool(field_id and field_id in self.active_fields)

    def field(self, field_id: str) -> dict[str, Any]:
        return self.active_fields[field_id]

    def configured_field(self, field_id: str | None) -> dict[str, Any]:
        """Return a configured field, including missing-but-documented fields."""

        if not field_id:
            return {}
        return self.configured_fields.get(field_id, {})

    def resolve_field_id(
        self,
        field_id: str | None = None,
        source_column: str | None = None,
    ) -> str | None:
        """Resolve a proposed rule field id from an id or source column name."""

        if field_id in self.configured_fields:
            return field_id
        if not source_column:
            return None
        for candidate_id, spec in self.configured_fields.items():
            if spec.get("source_column") == source_column:
                return candidate_id
        return None

    def field_summary_for_llm(self) -> list[dict[str, Any]]:
        """Return a compact schema summary for extraction prompts.

        This intentionally exposes field metadata only, not raw workbook rows.
        """

        summary = []
        for field_id, spec in self.configured_fields.items():
            source_column = spec.get("source_column")
            active = self.has_field(field_id)
            summary.append(
                {
                    "field_id": field_id,
                    "source_column": source_column,
                    "active": active,
                    "status": "active" if active else spec.get("status", "inactive"),
                    "type": spec.get("type"),
                    "aliases": spec.get("aliases", []),
                    "allowed_ops": spec.get("allowed_ops", []),
                    "notes": spec.get("notes"),
                }
            )
        return summary

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return self.active_fields
