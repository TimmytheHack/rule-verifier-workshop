"""Schema registry boundary for executable rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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

    def has_field(self, field_id: str | None) -> bool:
        return bool(field_id and field_id in self.active_fields)

    def field(self, field_id: str) -> dict[str, Any]:
        return self.active_fields[field_id]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return self.active_fields
