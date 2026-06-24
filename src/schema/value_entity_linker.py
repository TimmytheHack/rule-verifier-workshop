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
NEGATION_TERMS = ("不要", "不想", "排除", "别", "不去", "不是", "不考虑", "除了")
DISTANCE_AFTER_TERMS = ("近", "远", "太远")
BOUNDARY_AFTER_TERMS = ("附近", "周边", "旁边")
IDENTITY_TERMS = ("户籍", "考生", "生源", "籍贯")
INCOMPLETE_LOOKUP_REASON = "字段值索引不完整，不能直接执行实体筛选。"
NEARBY_REASON = "附近/周边表达需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。"
NEGATED_ENTITY_REASON = "否定/排除上下文不能直接执行为正向实体筛选。"
DISTANCE_REASON = "距离/模糊地理边界需要地理距离或用户确认边界，不能直接执行为城市筛选。"
ENTITY_DISTANCE_REASON = "距离/模糊地理边界需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。"
IDENTITY_REASON = "身份/户籍上下文不能直接执行为城市筛选。"


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
        proposed_rules = _proposed_rules(accepted)
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
            if indexed_field.get("active") is not True:
                continue
            values = [str(value) for value in indexed_field.get("lookup_values") or []]
            if not values:
                continue
            lookup_complete = indexed_field.get("lookup_complete") is True
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
    context_window = 8
    return {
        "source_text": text[span[0]:span[1]],
        "span": span,
        "context_before": text[max(0, span[0] - context_window):span[0]],
        "context_after": text[span[1]:span[1] + context_window],
        "input_text": text,
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
    ambiguous = _ambiguous_exact_span_links(candidates)
    ambiguous_keys = {_link_key(link) for link in ambiguous}
    non_ambiguous = [
        candidate
        for candidate in candidates
        if _link_key(candidate) not in ambiguous_keys
    ]
    context_blocked = [
        {
            **candidate,
            "executable": False,
            "reason": reason,
        }
        for candidate in non_ambiguous
        for reason in [_non_executable_context_reason(candidate)]
        if reason is not None
    ]
    context_blocked_keys = {_link_key(link) for link in context_blocked}
    not_executed = [
        {
            **candidate,
            "executable": False,
            "reason": INCOMPLETE_LOOKUP_REASON,
        }
        for candidate in non_ambiguous
        if not candidate.get("value_evidence", {}).get("lookup_complete")
        and _link_key(candidate) not in context_blocked_keys
    ]
    executable = [
        candidate
        for candidate in non_ambiguous
        if candidate.get("value_evidence", {}).get("lookup_complete")
        and _link_key(candidate) not in context_blocked_keys
    ]
    remaining = executable

    accepted_entities: list[dict[str, Any]] = []
    for entity in sorted(_non_location_links(remaining), key=_candidate_sort_key):
        if _is_contained_by_longer_link(entity, accepted_entities):
            continue
        accepted_entities.append({**entity, "resolution": "accepted_longest_exact_entity"})

    accepted: list[dict[str, Any]] = list(accepted_entities)
    suppressed: list[dict[str, Any]] = []
    blocker_entities = accepted_entities + _non_location_links(not_executed + context_blocked)
    for location in sorted(_location_links(remaining), key=_span_start):
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

    not_executed.extend(context_blocked)
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


def _span_start(candidate: dict[str, Any]) -> int:
    span = candidate.get("span")
    if not _valid_span(span):
        return 0
    return int(span[0])


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
    text = str(candidate.get("input_text") or "")
    source_text = str(candidate.get("source_text") or "")
    span = candidate.get("span")
    if not _valid_span(span):
        return False
    if text.strip() == source_text:
        return True
    after = text[int(span[1]):]
    local_after = after[:8]
    return any(pattern in local_after for pattern in LOCATION_PATTERNS)


def _non_executable_context_reason(candidate: dict[str, Any]) -> str | None:
    if _has_distance_context(candidate):
        if candidate.get("mode") == "location":
            return DISTANCE_REASON
        return ENTITY_DISTANCE_REASON
    if candidate.get("mode") == "location":
        if _has_identity_context(candidate):
            return IDENTITY_REASON
        if _has_negation_context(candidate):
            return NEGATED_ENTITY_REASON
        return None
    if _has_negation_context(candidate):
        return NEGATED_ENTITY_REASON
    return None


def _has_negation_context(candidate: dict[str, Any]) -> bool:
    before = str(candidate.get("context_before") or "")
    after = str(candidate.get("context_after") or "")
    return any(term in before or term in after for term in NEGATION_TERMS)


def _has_distance_context(candidate: dict[str, Any]) -> bool:
    before = str(candidate.get("context_before") or "")
    after = str(candidate.get("context_after") or "")
    near_before = before[-4:]
    near_after = after[:4]
    if any(term in near_after for term in BOUNDARY_AFTER_TERMS):
        return True
    if "太远" in near_after:
        return True
    return "离" in near_before and any(term in near_after for term in DISTANCE_AFTER_TERMS)


def _has_identity_context(candidate: dict[str, Any]) -> bool:
    after = str(candidate.get("context_after") or "")
    return any(term in after for term in IDENTITY_TERMS)


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


def _proposed_rules(accepted_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for link in accepted_links:
        op = str(link.get("op") or "")
        if op not in {"in_contains", "contains_any"}:
            passthrough.append(link)
            continue
        grouped.setdefault((str(link.get("field_id")), op), []).append(link)

    rule_links: list[dict[str, Any]] = list(passthrough)
    for group in grouped.values():
        ordered = sorted(group, key=_span_start)
        if len(ordered) == 1:
            rule_links.append(ordered[0])
            continue
        first = ordered[0]
        merged_values = [link.get("value") for link in ordered]
        rule_links.append(
            {
                **first,
                "source_text": "、".join(str(link.get("source_text")) for link in ordered),
                "value": merged_values,
                "merged_links": ordered,
            }
        )

    return [
        _proposed_rule(index, link)
        for index, link in enumerate(sorted(rule_links, key=_span_start), start=1)
    ]


def _proposed_rule(index: int, link: dict[str, Any]) -> dict[str, Any]:
    value: Any = link.get("value")
    if link.get("op") in {"in_contains", "contains_any"} and not isinstance(value, list):
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
