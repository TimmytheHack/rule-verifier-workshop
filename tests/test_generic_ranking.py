from __future__ import annotations

import unittest

from src.semantic.generic_ranking import GenericRankingEngine
from src.semantic.ranking_plan import RankingCriterion, RankingPlan


def _criterion(
    *,
    criterion_id: str,
    required_field: str,
    operation: str,
    value: object = None,
    priority: int = 1,
    direction: str = "desc",
) -> RankingCriterion:
    return RankingCriterion(
        criterion_id=criterion_id,
        source_text=criterion_id,
        required_field=required_field,
        operation=operation,
        value=value,
        priority=priority,
        direction=direction,
        rationale="按已验证排序条件排序。",
    )


class GenericRankingEngineTest(unittest.TestCase):
    def test_ranks_admissions_rows_with_structured_criterion_evidence(self) -> None:
        plan = RankingPlan(
            criteria=[
                RankingCriterion(
                    criterion_id="major_text_match",
                    source_text="人工智能或计算机",
                    required_field="major_name",
                    operation="text_match",
                    value=["人工智能", "计算机"],
                    priority=1,
                    rationale="按已验证专业文本偏好排序。",
                ),
                RankingCriterion(
                    criterion_id="rank_distance",
                    source_text="位次接近 15000",
                    required_field="major_min_rank",
                    operation="numeric_distance_to_user_value",
                    value=15000,
                    priority=2,
                    rationale="按已验证位次距离排序。",
                ),
            ]
        )
        rows = [
            {"row_id": "r1", "major_name": "软件工程", "major_min_rank": 16000},
            {"row_id": "r2", "major_name": "计算机科学与技术", "major_min_rank": 18000},
            {"row_id": "r3", "major_name": "人工智能", "major_min_rank": 15100},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["r3", "r2", "r1"])
        evidence_by_row_id = {
            item["row_id"]: item["criteria"] for item in result.criterion_evidence
        }
        self.assertEqual(
            evidence_by_row_id["r3"][0]["matched_terms"],
            ["人工智能"],
        )
        self.assertEqual(
            evidence_by_row_id["r3"][1]["derived"],
            {"distance": 100},
        )
        self.assertEqual(evidence_by_row_id["r1"][0]["score"], 0)

    def test_ranks_non_admissions_rows_with_generic_operations(self) -> None:
        plan = RankingPlan(
            criteria=[
                RankingCriterion(
                    criterion_id="city_match",
                    source_text="Austin",
                    required_field="city",
                    operation="equals_preferred_value",
                    value="Austin",
                    priority=1,
                    rationale="按已验证城市偏好排序。",
                ),
                RankingCriterion(
                    criterion_id="rent_low",
                    source_text="低租金",
                    required_field="rent_usd",
                    operation="numeric_lower_is_better",
                    value=None,
                    priority=2,
                    rationale="按已验证租金字段升序偏好排序。",
                ),
            ]
        )
        rows = [
            {"row_id": "h1", "city": "Dallas", "rent_usd": 1200},
            {"row_id": "h2", "city": "Austin", "rent_usd": 1800},
            {"row_id": "h3", "city": "Austin", "rent_usd": 1500},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["h3", "h2", "h1"])

    def test_honors_criterion_direction_for_scores(self) -> None:
        rows = [
            {"row_id": "low", "score": 10},
            {"row_id": "high", "score": 30},
            {"row_id": "mid", "score": 20},
        ]
        descending_plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="score_desc",
                    required_field="score",
                    operation="numeric_higher_is_better",
                    direction="desc",
                )
            ]
        )
        ascending_plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="score_asc",
                    required_field="score",
                    operation="numeric_higher_is_better",
                    direction="asc",
                )
            ]
        )

        descending = GenericRankingEngine().rank(rows=rows, plan=descending_plan)
        ascending = GenericRankingEngine().rank(rows=rows, plan=ascending_plan)

        self.assertEqual([row["row_id"] for row in descending.rows], ["high", "mid", "low"])
        self.assertEqual([row["row_id"] for row in ascending.rows], ["low", "mid", "high"])

    def test_numeric_distance_always_ranks_closer_values_first(self) -> None:
        rows = [
            {"row_id": "far", "rank": 34000},
            {"row_id": "near", "rank": 14831},
            {"row_id": "mid", "rank": 17051},
        ]
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="rank_distance",
                    required_field="rank",
                    operation="numeric_distance_to_user_value",
                    value=15000,
                    direction="asc",
                )
            ]
        )

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["near", "mid", "far"])
        self.assertEqual(
            result.criterion_evidence[0]["criteria"][0]["derived"],
            {"distance": 169},
        )

    def test_preserves_input_order_after_all_criterion_scores_tie(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="city",
                    required_field="city",
                    operation="equals_preferred_value",
                    value="Austin",
                )
            ]
        )
        rows = [
            {"row_id": "z", "city": "Austin"},
            {"row_id": "a", "city": "Austin"},
            {"row_id": "m", "city": "Austin"},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["z", "a", "m"])

    def test_normalizes_numeric_values_for_equality(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="rent",
                    required_field="rent_usd",
                    operation="equals_preferred_value",
                    value=1200,
                )
            ]
        )
        rows = [
            {"row_id": "matched", "rent_usd": "1,200"},
            {"row_id": "unmatched", "rent_usd": "1,201"},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["matched", "unmatched"])
        self.assertEqual(result.criterion_evidence[0]["criteria"][0]["score"], 1)

    def test_normalizes_boolean_values_for_equality(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="public_school",
                    required_field="is_public",
                    operation="equals_preferred_value",
                    value=True,
                )
            ]
        )
        rows = [
            {"row_id": "matched", "is_public": "是"},
            {"row_id": "unmatched", "is_public": "false"},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["matched", "unmatched"])
        self.assertEqual(result.criterion_evidence[0]["criteria"][0]["score"], 1)

    def test_normalizes_values_for_preferred_set_membership(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="preferred_values",
                    required_field="value",
                    operation="in_preferred_set",
                    value=[1200, True],
                )
            ]
        )
        rows = [
            {"row_id": "numeric", "value": "1,200"},
            {"row_id": "boolean", "value": "true"},
            {"row_id": "unmatched", "value": "other"},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual(
            [row["row_id"] for row in result.rows],
            ["numeric", "boolean", "unmatched"],
        )
        evidence_by_row_id = {
            item["row_id"]: item["criteria"][0] for item in result.criterion_evidence
        }
        self.assertEqual(evidence_by_row_id["numeric"]["score"], 1)
        self.assertEqual(evidence_by_row_id["boolean"]["score"], 1)
        self.assertEqual(evidence_by_row_id["unmatched"]["score"], 0)

    def test_preserves_fractional_numeric_distance_evidence(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="distance",
                    required_field="value",
                    operation="numeric_distance_to_user_value",
                    value=10.5,
                )
            ]
        )
        rows = [{"row_id": "fractional", "value": 9.8}]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        distance = result.criterion_evidence[0]["criteria"][0]["derived"]["distance"]
        self.assertEqual(distance, 0.7)

    def test_missing_and_non_finite_numeric_values_sort_last_for_both_directions(self) -> None:
        rows = [
            {"row_id": "missing", "score": None},
            {"row_id": "high", "score": 30},
            {"row_id": "nan", "score": float("nan")},
            {"row_id": "low", "score": 10},
        ]
        descending_plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="score_desc",
                    required_field="score",
                    operation="numeric_higher_is_better",
                    direction="desc",
                )
            ]
        )
        ascending_plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="score_asc",
                    required_field="score",
                    operation="numeric_higher_is_better",
                    direction="asc",
                )
            ]
        )

        descending = GenericRankingEngine().rank(rows=rows, plan=descending_plan)
        ascending = GenericRankingEngine().rank(rows=rows, plan=ascending_plan)

        self.assertEqual(
            [row["row_id"] for row in descending.rows],
            ["high", "low", "missing", "nan"],
        )
        self.assertEqual(
            [row["row_id"] for row in ascending.rows],
            ["low", "high", "missing", "nan"],
        )
        self.assertIsNone(descending.criterion_evidence[-1]["criteria"][0]["score"])

    def test_boolean_preferred_value_scores_normalized_boolean_match(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="has_lab",
                    required_field="has_lab",
                    operation="boolean_preferred_value",
                    value=True,
                )
            ]
        )
        rows = [
            {"row_id": "unmatched", "has_lab": "否"},
            {"row_id": "matched", "has_lab": "1"},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["matched", "unmatched"])
        self.assertEqual(result.criterion_evidence[0]["criteria"][0]["score"], 1)

    def test_boolean_preferred_value_accepts_integer_zero_one_rows(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="has_lab",
                    required_field="has_lab",
                    operation="boolean_preferred_value",
                    value=True,
                )
            ]
        )
        rows = [
            {"row_id": "false_int", "has_lab": 0},
            {"row_id": "arbitrary_int", "has_lab": 2},
            {"row_id": "true_int", "has_lab": 1},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual(
            [row["row_id"] for row in result.rows],
            ["true_int", "false_int", "arbitrary_int"],
        )
        evidence_by_row_id = {
            item["row_id"]: item["criteria"][0] for item in result.criterion_evidence
        }
        self.assertEqual(evidence_by_row_id["true_int"]["score"], 1)
        self.assertEqual(evidence_by_row_id["false_int"]["score"], 0)
        self.assertEqual(evidence_by_row_id["arbitrary_int"]["score"], 0)

    def test_equality_normalizes_integer_zero_one_as_booleans(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="public_school",
                    required_field="is_public",
                    operation="equals_preferred_value",
                    value=True,
                )
            ]
        )
        rows = [
            {"row_id": "false_int", "is_public": 0},
            {"row_id": "true_int", "is_public": 1},
            {"row_id": "arbitrary_int", "is_public": 2},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual(
            [row["row_id"] for row in result.rows],
            ["true_int", "false_int", "arbitrary_int"],
        )
        evidence_by_row_id = {
            item["row_id"]: item["criteria"][0] for item in result.criterion_evidence
        }
        self.assertEqual(evidence_by_row_id["true_int"]["score"], 1)
        self.assertEqual(evidence_by_row_id["false_int"]["score"], 0)
        self.assertEqual(evidence_by_row_id["arbitrary_int"]["score"], 0)

    def test_preferred_set_normalizes_integer_zero_one_as_booleans(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="has_scholarship",
                    required_field="has_scholarship",
                    operation="in_preferred_set",
                    value=[False],
                )
            ]
        )
        rows = [
            {"row_id": "arbitrary_int", "has_scholarship": 2},
            {"row_id": "false_int", "has_scholarship": 0},
            {"row_id": "true_int", "has_scholarship": 1},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual(
            [row["row_id"] for row in result.rows],
            ["false_int", "arbitrary_int", "true_int"],
        )
        evidence_by_row_id = {
            item["row_id"]: item["criteria"][0] for item in result.criterion_evidence
        }
        self.assertEqual(evidence_by_row_id["false_int"]["score"], 1)
        self.assertEqual(evidence_by_row_id["true_int"]["score"], 0)
        self.assertEqual(evidence_by_row_id["arbitrary_int"]["score"], 0)

    def test_missing_value_penalty_keeps_present_values_before_missing_values(self) -> None:
        plan = RankingPlan(
            criteria=[
                _criterion(
                    criterion_id="has_value",
                    required_field="value",
                    operation="missing_value_penalty",
                )
            ]
        )
        rows = [
            {"row_id": "missing", "value": ""},
            {"row_id": "present", "value": "available"},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["present", "missing"])
        self.assertEqual(result.criterion_evidence[-1]["criteria"][0]["status"], "penalized")

    def test_unknown_operation_scores_zero_with_structured_evidence(self) -> None:
        criterion = RankingCriterion.model_construct(
            criterion_id="unknown_operation",
            source_text="unsupported",
            required_field="field",
            operation="unsupported_operation",
            value="preferred",
            priority=1,
            direction="desc",
            rationale="按已验证排序条件排序。",
        )
        plan = RankingPlan.model_construct(criteria=[criterion])
        rows = [{"row_id": "r1", "field": "actual"}]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["r1"])
        self.assertEqual(
            result.criterion_evidence,
            [
                {
                    "row_id": "r1",
                    "criteria": [
                        {
                            "criterion_id": "unknown_operation",
                            "field_id": "field",
                            "operation": "unsupported_operation",
                            "row_value": "actual",
                            "score": 0.0,
                            "status": "unknown_operation",
                        }
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
