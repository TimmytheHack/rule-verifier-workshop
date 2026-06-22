from __future__ import annotations

from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains import DomainConfig
    from src.semantic.capability_graph import DatasetCapabilityGraph


CUSTOM_OPS = {"satisfies_subject_requirement"}


class LLMSemanticCandidateProvider(Protocol):
    def propose(
        self,
        headers: list[str],
        samples: dict[str, list[Any]],
    ) -> list[dict[str, Any]]:
        ...


class RuleBasedSemanticCandidateGenerator:
    def __init__(self, reviewed_mappings: dict[str, Any]) -> None:
        self.reviewed_mappings = reviewed_mappings

    @classmethod
    def from_domain(
        cls,
        domain_config: DomainConfig,
    ) -> "RuleBasedSemanticCandidateGenerator":
        capabilities = domain_config.semantic_capabilities
        reviewed_mappings = capabilities.get("reviewed_mappings") or {}
        return cls(reviewed_mappings)

    def generate(self, graph: DatasetCapabilityGraph) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for field_id, spec in _reviewed_mapping_items(self.reviewed_mappings):
            source_column = _first_existing_source_column(spec, graph)
            if not source_column:
                continue
            field = graph.fields[source_column]
            candidate_ops = _compatible_ops(
                spec.get("allowed_ops") or [],
                field.candidate_ops,
            )
            if not candidate_ops:
                continue
            candidates.append(
                {
                    "source_column": source_column,
                    "canonical_field_id": field_id,
                    "confidence": _confidence(spec),
                    "inferred_type": field.inferred_type,
                    "candidate_ops": candidate_ops,
                    "reason": str(spec.get("reason") or "reviewed_mapping"),
                }
            )
        return candidates


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


def _confidence(spec: dict[str, Any]) -> float:
    value = spec.get("confidence", 1.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0
