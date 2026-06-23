from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Any

from src.semantic.ranking_plan import (
    ALLOWED_RANKING_OPERATIONS,
    RankingCriterion,
    RankingPlan,
)
from src.semantic.reviewed_mapping import ReviewedMappingRegistry


OP_TO_REVIEWED_OP = {
    "text_match": "contains_any",
    "equals_preferred_value": "eq",
    "in_preferred_set": "in",
    "numeric_distance_to_user_value": "sort",
    "numeric_higher_is_better": "sort",
    "numeric_lower_is_better": "sort",
    "boolean_preferred_value": "eq",
    "missing_value_penalty": "sort",
}

NUMERIC_RANKING_OPERATIONS = frozenset(
    {
        "numeric_distance_to_user_value",
        "numeric_higher_is_better",
        "numeric_lower_is_better",
    }
)
NUMERIC_FIELD_TYPE_MARKERS = ("number", "numeric", "float", "int", "rank")
TEXT_FIELD_TYPE_MARKERS = ("string", "text", "name", "enum", "category")
BOOLEAN_FIELD_TYPE_MARKERS = ("bool", "boolean")
COMPARABLE_FIELD_TYPE_MARKERS = (
    NUMERIC_FIELD_TYPE_MARKERS
    + TEXT_FIELD_TYPE_MARKERS
    + BOOLEAN_FIELD_TYPE_MARKERS
)
TRUSTED_VALUE_EVIDENCE_SOURCES = frozenset(
    {"user_input", "value_index", "confirmed_boundary", "reviewed_policy"}
)
ID_BOUND_VALUE_EVIDENCE_SOURCES = frozenset({"value_index", "reviewed_policy"})
TEXT_BOUND_VALUE_EVIDENCE_SOURCES = frozenset({"user_input", "confirmed_boundary"})
VALUE_EVIDENCE_OPERATIONS = frozenset(
    {
        "text_match",
        "equals_preferred_value",
        "in_preferred_set",
        "numeric_distance_to_user_value",
        "boolean_preferred_value",
    }
)


@dataclass(frozen=True)
class RankingVerificationResult:
    ok: bool
    verified_plan: RankingPlan
    excluded_criteria: list[dict[str, Any]]


class RankingVerifier:
    def __init__(
        self,
        registry: ReviewedMappingRegistry,
        value_evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        self._registry = registry
        self._value_evidence = tuple(value_evidence or [])

    def verify(self, plan: RankingPlan) -> RankingVerificationResult:
        verified_criteria: list[RankingCriterion] = []
        excluded_criteria: list[dict[str, Any]] = []

        for criterion in sorted(plan.criteria, key=lambda item: item.priority):
            field_id = criterion.required_field
            if criterion.operation not in ALLOWED_RANKING_OPERATIONS:
                excluded_criteria.append(
                    self._excluded(
                        criterion,
                        reason="unsupported_operation",
                        message=f"排序操作 {criterion.operation} 不在通用排序白名单中。",
                    )
                )
                continue

            if not self._registry.has_field(field_id):
                excluded_criteria.append(
                    self._excluded(
                        criterion,
                        reason="missing_field",
                        message=(
                            self._registry.unsupported_reason(field_id)
                            or f"字段 {field_id} 不在已审查语义映射中，不能用于排序。"
                        ),
                    )
                )
                continue

            reviewed_op = OP_TO_REVIEWED_OP[criterion.operation]
            if not self._registry.has_op(field_id, reviewed_op):
                excluded_criteria.append(
                    self._excluded(
                        criterion,
                        reason="unsupported_operation",
                        message=f"字段 {field_id} 不支持排序映射操作 {reviewed_op}。",
                    )
                )
                continue

            field_type = self._field_type(field_id)
            if not _field_type_supports_operation(field_type, criterion.operation):
                excluded_criteria.append(
                    self._excluded(
                        criterion,
                        reason="unsupported_operation",
                        message=(
                            f"字段 {field_id} 的类型 {field_type or 'unknown'} "
                            f"不支持排序操作 {criterion.operation}。"
                        ),
                    )
                )
                continue

            value_message = _incompatible_value_message(
                field_type,
                criterion.operation,
                criterion.value,
            )
            if value_message:
                excluded_criteria.append(
                    self._excluded(
                        criterion,
                        reason="unsupported_operation",
                        message=value_message,
                    )
                )
                continue

            if (
                criterion.operation in VALUE_EVIDENCE_OPERATIONS
                and not self._has_trusted_value_evidence(criterion, field_type)
            ):
                excluded_criteria.append(
                    self._excluded(
                        criterion,
                        reason="unverified_value",
                        message=(
                            f"排序条件 {criterion.criterion_id} 的 value "
                            "缺少可信来源证据，不能验证执行。"
                        ),
                    )
                )
                continue

            verified_criteria.append(criterion)

        verified_plan = RankingPlan(
            criteria=verified_criteria,
            rationale_summary=plan.rationale_summary,
        )
        has_unsupported_operation = any(
            item["reason"] in {"unsupported_operation", "unverified_value"}
            for item in excluded_criteria
        )
        ok = bool(verified_criteria) and not has_unsupported_operation
        return RankingVerificationResult(
            ok=ok,
            verified_plan=verified_plan,
            excluded_criteria=excluded_criteria,
        )

    def _field_type(self, field_id: str) -> str:
        for mapping in self._registry.active_field_dicts():
            if mapping.get("field_id") == field_id:
                return str(mapping.get("field_type") or "").lower()
        return ""

    def _has_trusted_value_evidence(
        self,
        criterion: RankingCriterion,
        field_type: str,
    ) -> bool:
        expected_value = _normalized_value(
            criterion.value,
            operation=criterion.operation,
            field_type=field_type,
        )
        for evidence in self._value_evidence:
            if not isinstance(evidence, dict):
                continue
            source = str(evidence.get("source") or "")
            if source not in TRUSTED_VALUE_EVIDENCE_SOURCES:
                continue
            if (
                "criterion_id" in evidence
                and evidence["criterion_id"] != criterion.criterion_id
            ):
                continue
            if not _evidence_source_binds_criterion(
                source,
                evidence,
                criterion,
            ):
                continue
            if evidence.get("field_id") != criterion.required_field:
                continue
            if evidence.get("operation") != criterion.operation:
                continue
            if "value" not in evidence:
                continue
            evidence_value = _normalized_value(
                evidence["value"],
                operation=criterion.operation,
                field_type=field_type,
            )
            if evidence_value == expected_value:
                return True
        return False

    @staticmethod
    def _excluded(
        criterion: RankingCriterion,
        *,
        reason: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "criterion_id": criterion.criterion_id,
            "source_text": criterion.source_text,
            "required_field": criterion.required_field,
            "operation": criterion.operation,
            "reason": reason,
            "message": message,
        }


def _field_type_supports_operation(field_type: str, operation: str) -> bool:
    if operation in NUMERIC_RANKING_OPERATIONS:
        return _has_field_type_marker(field_type, NUMERIC_FIELD_TYPE_MARKERS)
    if operation == "text_match":
        return (
            _has_field_type_marker(field_type, TEXT_FIELD_TYPE_MARKERS)
            and not _has_field_type_marker(field_type, NUMERIC_FIELD_TYPE_MARKERS)
        )
    if operation == "boolean_preferred_value":
        return _has_field_type_marker(field_type, BOOLEAN_FIELD_TYPE_MARKERS)
    if operation in {"equals_preferred_value", "in_preferred_set"}:
        return _has_field_type_marker(field_type, COMPARABLE_FIELD_TYPE_MARKERS)
    if operation == "missing_value_penalty":
        return True
    return False


def _evidence_source_binds_criterion(
    source: str,
    evidence: dict[str, Any],
    criterion: RankingCriterion,
) -> bool:
    if source in ID_BOUND_VALUE_EVIDENCE_SOURCES:
        return evidence.get("criterion_id") == criterion.criterion_id
    if source in TEXT_BOUND_VALUE_EVIDENCE_SOURCES:
        has_criterion_id = "criterion_id" in evidence
        has_source_text = "source_text" in evidence
        if not has_criterion_id and not has_source_text:
            return False
        if has_criterion_id:
            return True
        return _normalized_text(evidence.get("source_text")) == _normalized_text(
            criterion.source_text
        )
    return False


def _incompatible_value_message(
    field_type: str,
    operation: str,
    value: Any,
) -> str | None:
    if _is_numeric_field_type(field_type):
        if operation == "equals_preferred_value" and not _is_numeric_value(value):
            return "数值字段的 equals_preferred_value 必须使用有限数值或数值字符串。"
        if operation == "in_preferred_set" and not _is_numeric_value_list(value):
            return "数值字段的 in_preferred_set 必须使用有限数值或数值字符串列表。"
    if _is_boolean_field_type(field_type):
        if operation == "equals_preferred_value" and not _is_boolean_value(value):
            return "布尔字段的 equals_preferred_value 必须使用布尔兼容值。"
        if operation == "in_preferred_set" and not _is_boolean_value_list(value):
            return "布尔字段的 in_preferred_set 必须使用布尔兼容值列表。"
    return None


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _is_numeric_field_type(field_type: str) -> bool:
    return _has_field_type_marker(field_type, NUMERIC_FIELD_TYPE_MARKERS)


def _is_boolean_field_type(field_type: str) -> bool:
    return _has_field_type_marker(field_type, BOOLEAN_FIELD_TYPE_MARKERS)


def _is_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str) and value.strip():
        try:
            return math.isfinite(float(value.strip()))
        except ValueError:
            return False
    return False


def _is_numeric_value_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        _is_numeric_value(item) for item in value
    )


def _is_boolean_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int) and value in {0, 1}:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"是", "否", "true", "false", "1", "0"}
    return False


def _is_boolean_value_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        _is_boolean_value(item) for item in value
    )


def _normalized_value(value: Any, *, operation: str, field_type: str) -> Any:
    if operation in {"text_match", "in_preferred_set"} and isinstance(value, list):
        normalized_items = (
            _normalized_scalar(item, operation=operation, field_type=field_type)
            for item in value
        )
        return tuple(sorted(normalized_items, key=repr))
    return _normalized_scalar(value, operation=operation, field_type=field_type)


def _normalized_scalar(value: Any, *, operation: str, field_type: str) -> Any:
    if _is_boolean_field_type(field_type) or operation == "boolean_preferred_value":
        boolean_value = _boolean_value_or_none(value)
        if boolean_value is not None:
            return ("bool", boolean_value)
    if _is_numeric_field_type(field_type) or operation == "numeric_distance_to_user_value":
        numeric_value = _numeric_value_or_none(value)
        if numeric_value is not None:
            return ("number", numeric_value)
    if isinstance(value, str):
        return ("string", value.strip())
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("number", str(Decimal(value).normalize()))
    if isinstance(value, float) and math.isfinite(value):
        return ("number", str(Decimal(str(value)).normalize()))
    return (type(value).__name__, value)


def _boolean_value_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"是", "true", "1"}:
            return True
        if normalized in {"否", "false", "0"}:
            return False
    return None


def _numeric_value_or_none(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(Decimal(value).normalize())
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return str(Decimal(str(value)).normalize())
    if isinstance(value, str) and value.strip():
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation:
            return None
        if not parsed.is_finite():
            return None
        return str(parsed.normalize())
    return None


def _has_field_type_marker(field_type: str, markers: tuple[str, ...]) -> bool:
    return any(marker in field_type for marker in markers)


__all__ = [
    "OP_TO_REVIEWED_OP",
    "RankingVerificationResult",
    "RankingVerifier",
]
