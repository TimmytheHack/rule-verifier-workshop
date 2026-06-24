"""基于 reviewed schema/value index 的实体链接。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.adapters.data_warehouse import SchemaValueIndex
from src.schema.schema_registry import SchemaRegistry


TEXT_FIELD_TYPES = {"string", "enum", "enum_or_category", "category"}
DEFAULT_LINKABLE_FIELDS: dict[str, dict[str, str]] = {
    "university_name": {"operator": "eq", "mode": "entity"},
    "city": {"operator": "in_contains", "mode": "location"},
    "major_name": {"operator": "contains_any", "mode": "major"},
}
NEARBY_TERMS = ("附近", "周边", "旁边", "那边")
LOCATION_PATTERNS = ("的大学", "市高校", "高校", "读大学", "上大学")
INCOMPLETE_LOOKUP_REASON = "字段值索引不完整，不能直接执行实体筛选。"
NEARBY_REASON = "附近/周边表达需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。"


@dataclass(frozen=True)
class EntityLinkingResult:
    status: str
    accepted_links: list[dict[str, Any]] = field(default_factory=list)
    suppressed_links: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_links: list[dict[str, Any]] = field(default_factory=list)
    not_executed_links: list[dict[str, Any]] = field(default_factory=list)
    proposed_rules: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted_links": self.accepted_links,
            "suppressed_links": self.suppressed_links,
            "ambiguous_links": self.ambiguous_links,
            "not_executed_links": self.not_executed_links,
            "proposed_rules": self.proposed_rules,
        }


class ReviewedValueEntityLinker:
    """用 reviewed schema/value index 识别显式实体，不执行查询。"""

    def __init__(
        self,
        schema_registry: SchemaRegistry,
        value_index: SchemaValueIndex | None,
        linkable_fields: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.schema_registry = schema_registry
        self.value_index = value_index
        self.linkable_fields = linkable_fields or DEFAULT_LINKABLE_FIELDS

    def link(self, text: str) -> EntityLinkingResult:
        if self.value_index is None:
            return EntityLinkingResult(status="value_index_unavailable")

        nearby_link = _nearby_not_executed(text)
        if nearby_link is not None:
            return EntityLinkingResult(
                status="applied",
                not_executed_links=[nearby_link],
            )

        candidates = self._candidates(text)
        accepted, suppressed, ambiguous, not_executed = _resolve_candidates(candidates)
        proposed_rules = [
            _proposed_rule(index, link)
            for index, link in enumerate(accepted, start=1)
        ]
        return EntityLinkingResult(
            status="applied",
            accepted_links=accepted,
            suppressed_links=suppressed,
            ambiguous_links=ambiguous,
            not_executed_links=not_executed,
            proposed_rules=proposed_rules,
        )

    def _candidates(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []

        candidates: list[dict[str, Any]] = []
        assert self.value_index is not None
        for field_id, policy in self._linkable_field_policies().items():
            if not self.schema_registry.has_field(field_id):
                continue
            field = self.schema_registry.configured_field(field_id)
            if str(field.get("type") or "") not in TEXT_FIELD_TYPES:
                continue
            indexed_field = (self.value_index.fields or {}).get(field_id) or {}
            if not indexed_field.get("active", True):
                continue
            values = [str(value) for value in indexed_field.get("lookup_values") or []]
            if not values:
                continue
            lookup_complete = bool(indexed_field.get("lookup_complete"))
            for value in values:
                for span in _find_spans(text, value):
                    candidates.append(
                        _candidate_record(
                            text=text,
                            field_id=field_id,
                            field=field,
                            policy=policy,
                            value=value,
                            span=span,
                            lookup_complete=lookup_complete,
                        )
                    )
        return candidates

    def _linkable_field_policies(self) -> dict[str, dict[str, Any]]:
        policies = {
            field_id: dict(policy)
            for field_id, policy in self.linkable_fields.items()
        }
        assert self.value_index is not None
        # 已审核的额外文本字段只允许 exact entity 级链接，用于暴露跨字段歧义。
        for field_id, indexed_field in (self.value_index.fields or {}).items():
            if field_id in policies:
                continue
            if not self.schema_registry.has_field(field_id):
                continue
            field = self.schema_registry.configured_field(field_id)
            field_type = str(field.get("type") or indexed_field.get("type") or "")
            if field_type not in TEXT_FIELD_TYPES:
                continue
            allowed_ops = field.get("allowed_ops") or indexed_field.get("allowed_ops") or []
            if "eq" not in allowed_ops:
                continue
            policies[field_id] = {"operator": "eq", "mode": "entity"}
        return policies


def _candidate_record(
    *,
    text: str,
    field_id: str,
    field: dict[str, Any],
    policy: dict[str, Any],
    value: str,
    span: tuple[int, int],
    lookup_complete: bool,
) -> dict[str, Any]:
    return {
        "source_text": text[span[0]:span[1]],
        "span": span,
        "field_id": field_id,
        "source_column": field.get("source_column"),
        "value": value,
        "op": policy.get("operator") or "eq",
        "match_type": "exact_full_span",
        "mode": policy.get("mode") or "entity",
        "executable": lookup_complete,
        "value_evidence": {
            "source": "schema_value_index",
            "status": "exact_match",
            "lookup_complete": lookup_complete,
            "matched_values": [value],
        },
    }


def _find_spans(text: str, value: str) -> list[tuple[int, int]]:
    if not text or not value:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(value, start)
        if index < 0:
            return spans
        spans.append((index, index + len(value)))
        start = index + 1


def _nearby_not_executed(text: str) -> dict[str, Any] | None:
    for term in NEARBY_TERMS:
        index = text.find(term)
        if index < 0:
            continue
        start = max(0, index - 4)
        return {
            "source_text": text[start:index + len(term)],
            "span": (start, index + len(term)),
            "field_id": None,
            "match_type": "entity_linking_boundary_required",
            "executable": False,
            "reason": NEARBY_REASON,
        }
    return None


def _resolve_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    not_executed = [
        {
            **candidate,
            "executable": False,
            "reason": INCOMPLETE_LOOKUP_REASON,
        }
        for candidate in candidates
        if not candidate.get("value_evidence", {}).get("lookup_complete")
    ]
    executable = [
        candidate
        for candidate in candidates
        if candidate.get("value_evidence", {}).get("lookup_complete")
    ]
    ambiguous = _ambiguous_exact_span_links(executable)
    ambiguous_keys = {_link_key(link) for link in ambiguous}
    remaining = [link for link in executable if _link_key(link) not in ambiguous_keys]

    accepted_entities: list[dict[str, Any]] = []
    for entity in sorted(_non_location_links(remaining), key=_candidate_sort_key):
        if _is_contained_by_longer_link(entity, accepted_entities):
            continue
        accepted_entities.append({**entity, "resolution": "accepted_longest_exact_entity"})

    accepted: list[dict[str, Any]] = list(accepted_entities)
    suppressed: list[dict[str, Any]] = []
    blocker_entities = accepted_entities + _non_location_links(not_executed)
    for location in _location_links(remaining):
        suppressor = _containing_link(location, blocker_entities)
        if suppressor is not None:
            suppressed.append(
                {
                    **location,
                    "match_type": "substring_inside_exact_entity",
                    "executable": False,
                    "resolution": f"suppressed_by_{suppressor['field_id']}_exact_full_span",
                }
            )
            continue
        if _looks_like_location_expression(location):
            accepted.append({**location, "resolution": "accepted_location_expression"})

    return _dedupe_links(accepted), _dedupe_links(suppressed), ambiguous, not_executed


def _ambiguous_exact_span_links(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        span = candidate.get("span")
        if not _valid_span(span):
            continue
        groups.setdefault((span[0], span[1], str(candidate.get("source_text"))), []).append(candidate)
    return [
        {**candidate, "executable": False, "resolution": "ambiguous_exact_span"}
        for group in groups.values()
        if len({candidate.get("field_id") for candidate in group}) > 1
        for candidate in group
    ]


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int]:
    span = candidate.get("span") or (0, 0)
    return (-(int(span[1]) - int(span[0])), int(span[0]))


def _location_links(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [candidate for candidate in candidates if candidate.get("mode") == "location"]


def _non_location_links(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [candidate for candidate in candidates if candidate.get("mode") != "location"]


def _is_contained_by_longer_link(
    candidate: dict[str, Any],
    accepted_links: list[dict[str, Any]],
) -> bool:
    span = candidate.get("span")
    if not _valid_span(span):
        return False
    for accepted in accepted_links:
        accepted_span = accepted.get("span")
        if not _valid_span(accepted_span):
            continue
        if (
            int(accepted_span[0]) <= int(span[0])
            and int(span[1]) <= int(accepted_span[1])
        ):
            return (int(accepted_span[1]) - int(accepted_span[0])) > (
                int(span[1]) - int(span[0])
            )
    return False


def _containing_link(
    candidate: dict[str, Any],
    containing_links: list[dict[str, Any]],
) -> dict[str, Any] | None:
    span = candidate.get("span")
    if not _valid_span(span):
        return None
    start, end = int(span[0]), int(span[1])
    for link in containing_links:
        link_span = link.get("span")
        if not _valid_span(link_span):
            continue
        if int(link_span[0]) <= start and end <= int(link_span[1]):
            return link
    return None


def _looks_like_location_expression(candidate: dict[str, Any]) -> bool:
    source_text = str(candidate.get("source_text") or "")
    return any(pattern in source_text for pattern in LOCATION_PATTERNS) or bool(source_text)


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, tuple[int, int]]] = set()
    output: list[dict[str, Any]] = []
    for link in links:
        key = _link_key(link)
        if key in seen:
            continue
        output.append(link)
        seen.add(key)
    return output


def _link_key(link: dict[str, Any]) -> tuple[str, str, str, tuple[int, int]]:
    span = link.get("span")
    return (
        str(link.get("field_id")),
        str(link.get("op")),
        str(link.get("value")),
        span if _valid_span(span) else (0, 0),
    )


def _valid_span(span: Any) -> bool:
    return (
        isinstance(span, tuple)
        and len(span) == 2
        and isinstance(span[0], int)
        and isinstance(span[1], int)
    )


def _proposed_rule(index: int, link: dict[str, Any]) -> dict[str, Any]:
    value: Any = link.get("value")
    if link.get("op") in {"in_contains", "contains_any"}:
        value = [value]
    return {
        "rule_id": f"value_entity_{index:03d}",
        "source_text": link.get("source_text"),
        "category": "deterministic",
        "field_id": link.get("field_id"),
        "field": link.get("source_column"),
        "operator": link.get("op"),
        "value": value,
        "semantic_type": "explicit_user_fact",
        "value_source": "explicit_user_fact",
        "requires_human_confirmation": False,
        "reason": "reviewed value index exact match",
        "proposed_by": "reviewed_value_entity_linker",
    }
