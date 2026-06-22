from __future__ import annotations

from typing import Any

from src.semantic.reviewed_mapping import ReviewedMappingRegistry


FILTER_OPS = {"eq", "in", "contains", "contains_any", "between"}


class SemanticQueryOptionsBuilder:
    """从 reviewed mapping 生成 UI 和 LLM 可见的查询能力摘要。"""

    def __init__(self, registry: ReviewedMappingRegistry) -> None:
        self.registry = registry

    def build(self) -> dict[str, Any]:
        fields = {
            item["field_id"]: item for item in self.registry.active_field_dicts()
        }
        query_types: list[str] = []
        if "major_name" in fields and (
            "major_min_rank" in fields or "group_min_rank" in fields
        ):
            query_types.append("semantic_recommendation")
        if "major_min_rank" in fields:
            query_types.append("admissions_major_rank")

        return {
            "query_types": query_types,
            "required_user_context": ["user_rank"] if query_types else [],
            "filters": _filter_options(fields),
            "sort_fields": _sort_options(fields),
            "unsupported_fields": {
                field_id: self.registry.unsupported_reason(field_id)
                for field_id in self.registry.unsupported_field_ids()
            },
        }


def _filter_options(fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        field_id: {
            "source_column": item["source_column"],
            "allowed_ops": item["allowed_ops"],
            "field_type": item["field_type"],
        }
        for field_id, item in fields.items()
        if FILTER_OPS.intersection(item["allowed_ops"])
    }


def _sort_options(fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        field_id: {
            "source_column": item["source_column"],
            "field_type": item["field_type"],
        }
        for field_id, item in fields.items()
        if "sort" in item["allowed_ops"]
    }
