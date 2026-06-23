from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from src.semantic.ranking_plan import RankingCriterion, RankingPlan


@dataclass(frozen=True)
class GenericRankingResult:
    rows: list[dict[str, Any]]
    criterion_evidence: list[dict[str, Any]] = field(default_factory=list)


class GenericRankingEngine:
    """基于已验证 RankingPlan 对传入行做确定性排序并生成结构化证据。"""

    def rank(
        self,
        *,
        rows: list[dict[str, Any]],
        plan: RankingPlan,
    ) -> GenericRankingResult:
        criteria = sorted(plan.criteria, key=lambda criterion: criterion.priority)
        scored_rows: list[dict[str, Any]] = []

        for index, row in enumerate(rows):
            row_copy = dict(row)
            criterion_scores: list[float] = []
            criteria_evidence: list[dict[str, Any]] = []

            for criterion in criteria:
                score, evidence = self._score_criterion(row_copy, criterion)
                criterion_scores.append(score)
                criteria_evidence.append(evidence)

            row_id = self._row_id(row_copy, index)
            scored_rows.append(
                {
                    "row": row_copy,
                    "scores": criterion_scores,
                    "evidence": {
                        "row_id": row_id,
                        "criteria": criteria_evidence,
                    },
                    "index": index,
                }
            )

        ordered = sorted(
            scored_rows,
            key=lambda item: self._sort_key(item["scores"], criteria, item["index"]),
        )
        return GenericRankingResult(
            rows=[item["row"] for item in ordered],
            criterion_evidence=[item["evidence"] for item in ordered],
        )

    def _sort_key(
        self,
        scores: list[float],
        criteria: list[RankingCriterion],
        index: int,
    ) -> tuple[Any, ...]:
        criterion_keys = tuple(
            self._sort_score(score, criterion.direction)
            for score, criterion in zip(scores, criteria)
        )
        return criterion_keys + (index,)

    def _sort_score(self, score: float, direction: str) -> tuple[int, float]:
        if not math.isfinite(score):
            return (1, 0.0)
        if direction == "asc":
            return (0, score)
        return (0, -score)

    def _score_criterion(
        self,
        row: dict[str, Any],
        criterion: RankingCriterion,
    ) -> tuple[float, dict[str, Any]]:
        field_id = criterion.required_field
        row_value = row.get(field_id)
        operation = criterion.operation

        if operation == "text_match":
            return self._score_text_match(criterion, field_id, row_value)
        if operation == "equals_preferred_value":
            score = float(self._values_equal(row_value, criterion.value))
            status = "matched" if score else "not_matched"
            return score, self._evidence(criterion, field_id, row_value, score, status)
        if operation == "in_preferred_set":
            score = float(
                any(
                    self._values_equal(row_value, preferred_value)
                    for preferred_value in self._as_list(criterion.value)
                )
            )
            status = "matched" if score else "not_matched"
            return score, self._evidence(criterion, field_id, row_value, score, status)
        if operation == "numeric_distance_to_user_value":
            return self._score_numeric_distance(criterion, field_id, row_value)
        if operation == "numeric_higher_is_better":
            return self._score_numeric_order(criterion, field_id, row_value, higher=True)
        if operation == "numeric_lower_is_better":
            return self._score_numeric_order(criterion, field_id, row_value, higher=False)
        if operation == "boolean_preferred_value":
            return self._score_boolean_preference(criterion, field_id, row_value)
        if operation == "missing_value_penalty":
            score = -1.0 if self._is_empty(row_value) else 0.0
            status = "penalized" if score < 0 else "scored"
            return score, self._evidence(criterion, field_id, row_value, score, status)

        score = 0.0
        return score, self._evidence(
            criterion,
            field_id,
            row_value,
            score,
            "unknown_operation",
        )

    def _score_text_match(
        self,
        criterion: RankingCriterion,
        field_id: str,
        row_value: Any,
    ) -> tuple[float, dict[str, Any]]:
        row_text = self._string_value(row_value)
        terms = [term for term in self._as_list(criterion.value) if isinstance(term, str)]
        matched_terms = [term for term in terms if term in row_text]
        score = 1.0 if matched_terms else 0.0
        status = "matched" if matched_terms else "not_matched"
        evidence = self._evidence(criterion, field_id, row_value, score, status)
        evidence["matched_terms"] = matched_terms
        return score, evidence

    def _score_numeric_distance(
        self,
        criterion: RankingCriterion,
        field_id: str,
        row_value: Any,
    ) -> tuple[float, dict[str, Any]]:
        row_number = self._number(row_value)
        target_number = self._number(criterion.value)
        distance: float | None = None
        score = -math.inf

        if row_number is not None and target_number is not None:
            distance = abs(row_number - target_number)
            score = 1.0 / (1.0 + distance)

        evidence = self._evidence(
            criterion,
            field_id,
            row_value,
            score,
            "scored" if math.isfinite(score) else "missing_or_invalid",
            derived={
                "distance": self._distance_evidence(distance),
            },
        )
        return score, evidence

    def _score_numeric_order(
        self,
        criterion: RankingCriterion,
        field_id: str,
        row_value: Any,
        *,
        higher: bool,
    ) -> tuple[float, dict[str, Any]]:
        number = self._number(row_value)
        score = number if number is not None else -math.inf
        if number is not None and not higher:
            score = -number
        return score, self._evidence(
            criterion,
            field_id,
            row_value,
            score,
            "scored" if math.isfinite(score) else "missing_or_invalid",
        )

    def _score_boolean_preference(
        self,
        criterion: RankingCriterion,
        field_id: str,
        row_value: Any,
    ) -> tuple[float, dict[str, Any]]:
        row_bool = self._boolean_value(row_value)
        preferred_bool = self._boolean_value(criterion.value)
        score = float(row_bool is not None and row_bool == preferred_bool)
        status = "matched" if score else "not_matched"
        return score, self._evidence(criterion, field_id, row_value, score, status)

    def _evidence(
        self,
        criterion: RankingCriterion,
        field_id: str,
        row_value: Any,
        score: float,
        status: str,
        *,
        derived: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "criterion_id": criterion.criterion_id,
            "field_id": field_id,
            "operation": criterion.operation,
            "row_value": row_value,
            "score": score if math.isfinite(score) else None,
            "status": status,
        }
        if derived is not None:
            evidence["derived"] = derived
        return evidence

    def _number(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return float(value)
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, str):
            normalized = value.strip().replace(",", "").replace("，", "")
            if not normalized:
                return None
            try:
                parsed = float(normalized)
            except ValueError:
                return None
            return parsed if math.isfinite(parsed) else None
        return None

    def _distance_evidence(self, distance: float | None) -> int | float | None:
        if distance is None:
            return None
        normalized = round(distance, 12)
        if normalized.is_integer():
            return int(normalized)
        return normalized

    def _values_equal(self, left: Any, right: Any) -> bool:
        left_bool = self._boolean_value(left)
        right_bool = self._boolean_value(right)
        if isinstance(left, bool) or isinstance(right, bool):
            return (
                left_bool is not None
                and right_bool is not None
                and left_bool == right_bool
            )

        left_number = self._number(left)
        right_number = self._number(right)
        if left_number is not None and right_number is not None:
            return left_number == right_number

        if left_bool is not None and right_bool is not None:
            return left_bool == right_bool

        return self._string_value(left) == self._string_value(right)

    def _boolean_value(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "是", "yes", "y"}:
                return True
            if normalized in {"false", "0", "否", "no", "n"}:
                return False
        return None

    def _string_value(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _as_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        return [value]

    def _is_empty(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, set, dict)):
            return not value
        return False

    def _row_id(self, row: dict[str, Any], index: int) -> Any:
        row_id = row.get("row_id")
        if row_id is not None and row_id != "":
            return row_id
        return f"__row_{index}"


__all__ = ["GenericRankingEngine", "GenericRankingResult"]
