from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains import DomainConfig
    from src.semantic.capability_graph import DatasetCapabilityGraph


CUSTOM_OPS = {"satisfies_subject_requirement"}


@dataclass(frozen=True)
class ReviewedFieldMapping:
    field_id: str
    source_column: str
    field_type: str
    allowed_ops: tuple[str, ...]
    required_for: tuple[str, ...]
    unsupported_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "field_id": self.field_id,
            "source_column": self.source_column,
            "field_type": self.field_type,
            "allowed_ops": list(self.allowed_ops),
            "required_for": list(self.required_for),
        }
        if self.unsupported_reason:
            payload["unsupported_reason"] = self.unsupported_reason
        return payload


class ReviewedMappingRegistry:
    def __init__(
        self,
        active_fields: dict[str, ReviewedFieldMapping],
        unsupported_fields: dict[str, str],
    ) -> None:
        self._active_fields = active_fields
        self._unsupported_fields = unsupported_fields

    @classmethod
    def from_domain(
        cls,
        domain_config: DomainConfig,
        graph: DatasetCapabilityGraph,
    ) -> "ReviewedMappingRegistry":
        capabilities = domain_config.semantic_capabilities
        active_fields: dict[str, ReviewedFieldMapping] = {}
        unsupported_fields: dict[str, str] = {}
        reviewed_mappings = capabilities.get("reviewed_mappings") or {}
        for field_id, spec in _reviewed_mapping_items(reviewed_mappings):
            source_column = _first_existing_source_column(spec, graph)
            if not source_column:
                unsupported_fields[field_id] = _unsupported_reason(
                    spec,
                    "missing_source_column",
                )
                continue

            graph_field = graph.fields[source_column]
            allowed_ops = _compatible_ops(
                spec.get("allowed_ops") or [],
                graph_field.candidate_ops,
            )
            if not allowed_ops:
                unsupported_fields[field_id] = _unsupported_reason(
                    spec,
                    "no_compatible_ops",
                )
                continue

            active_fields[field_id] = ReviewedFieldMapping(
                field_id=field_id,
                source_column=source_column,
                field_type=str(spec.get("field_type") or graph_field.inferred_type),
                allowed_ops=tuple(allowed_ops),
                required_for=tuple(str(item) for item in spec.get("required_for") or []),
            )
        return cls(active_fields, unsupported_fields)

    def has_field(self, field_id: str) -> bool:
        return field_id in self._active_fields

    def source_column(self, field_id: str) -> str:
        if field_id not in self._active_fields:
            raise KeyError(f"Reviewed semantic field is not active: {field_id}")
        return self._active_fields[field_id].source_column

    def source_column_or_none(self, field_id: str | None) -> str | None:
        if not field_id:
            return None
        mapping = self._active_fields.get(field_id)
        return mapping.source_column if mapping else None

    def has_op(self, field_id: str, op: str) -> bool:
        mapping = self._active_fields.get(field_id)
        return bool(mapping and op in mapping.allowed_ops)

    def unsupported_field_ids(self) -> list[str]:
        return list(self._unsupported_fields)

    def unsupported_reason(self, field_id: str) -> str | None:
        return self._unsupported_fields.get(field_id)

    def active_field_dicts(self) -> list[dict[str, Any]]:
        return [mapping.to_dict() for mapping in self._active_fields.values()]


def _reviewed_mapping_items(
    reviewed_mappings: Any,
) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(reviewed_mappings, dict):
        items: list[tuple[str, dict[str, Any]]] = []
        for field_id, spec in reviewed_mappings.items():
            if not isinstance(spec, dict):
                continue
            normalized = dict(spec)
            normalized.setdefault("field_id", field_id)
            items.append((str(field_id), normalized))
        return items
    if isinstance(reviewed_mappings, list):
        items = []
        for spec in reviewed_mappings:
            if not isinstance(spec, dict) or not spec.get("field_id"):
                continue
            items.append((str(spec["field_id"]), dict(spec)))
        return items
    return []


def _source_columns(spec: dict[str, Any]) -> list[str]:
    configured = spec.get("source_columns")
    if configured is None:
        configured = spec.get("source_column")
    if isinstance(configured, str):
        return [configured]
    if isinstance(configured, list):
        return [str(column) for column in configured if column]
    return []


def _first_existing_source_column(
    spec: dict[str, Any],
    graph: DatasetCapabilityGraph,
) -> str | None:
    for source_column in _source_columns(spec):
        if source_column in graph.fields:
            return source_column
    return None


def _compatible_ops(
    allowed_ops: list[Any],
    graph_ops: list[str],
) -> list[str]:
    graph_op_set = set(graph_ops)
    compatible: list[str] = []
    for op in allowed_ops:
        op_text = str(op)
        if op_text in graph_op_set or op_text in CUSTOM_OPS:
            compatible.append(op_text)
    return compatible


def _unsupported_reason(spec: dict[str, Any], fallback: str) -> str:
    return str(spec.get("unsupported_reason") or fallback)
