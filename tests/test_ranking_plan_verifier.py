from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.semantic.ranking_plan import RankingPlan
from src.semantic.ranking_verifier import RankingVerifier
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry


def _criterion_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "criterion_id": "major_text_match",
        "source_text": "人工智能，计算机",
        "required_field": "major_name",
        "operation": "text_match",
        "value": ["人工智能", "计算机"],
        "priority": 1,
        "rationale": "专业名称字段已审查，可用于文本匹配排序。",
    }
    payload.update(overrides)
    return payload


def _evidence(
    *,
    criterion_id: str = "major_text_match",
    field_id: str = "major_name",
    operation: str = "text_match",
    value: object = None,
    source: str = "user_input",
) -> dict[str, object]:
    return {
        "criterion_id": criterion_id,
        "field_id": field_id,
        "operation": operation,
        "value": ["人工智能", "计算机"] if value is None else value,
        "source": source,
    }


def _base_value_evidence() -> list[dict[str, object]]:
    return [
        _evidence(value=["计算机", "人工智能"]),
        _evidence(
            criterion_id="province_match",
            field_id="school_province",
            operation="equals_preferred_value",
            value="广东",
        ),
    ]


def _registry() -> ReviewedMappingRegistry:
    return ReviewedMappingRegistry(
        active_fields={
            "major_name": ReviewedFieldMapping(
                field_id="major_name",
                source_column="专业",
                field_type="string",
                allowed_ops=("contains_any", "contains", "text_match", "sort"),
                required_for=("filter", "display"),
            ),
            "school_province": ReviewedFieldMapping(
                field_id="school_province",
                source_column="学校所在",
                field_type="enum_or_category",
                allowed_ops=("in", "eq", "equals_preferred_value"),
                required_for=("filter", "display"),
            ),
            "major_min_rank": ReviewedFieldMapping(
                field_id="major_min_rank",
                source_column="最低位次",
                field_type="number",
                allowed_ops=(
                    "between",
                    "eq",
                    "in",
                    "sort",
                    "numeric_distance_to_user_value",
                ),
                required_for=("rank_analysis", "display"),
            ),
            "has_public_dorm": ReviewedFieldMapping(
                field_id="has_public_dorm",
                source_column="是否公办住宿",
                field_type="boolean",
                allowed_ops=("eq", "in"),
                required_for=("rank_analysis", "display"),
            ),
        },
        unsupported_fields={
            "school_country_or_region": "current data lacks country/region.",
        },
    )


class RankingPlanVerifierTest(unittest.TestCase):
    def test_ranking_plan_rejects_raw_sql_inside_criteria(self) -> None:
        with self.assertRaises(ValidationError):
            RankingPlan.model_validate(
                {
                    "criteria": [
                        {
                            "criterion_id": "unsafe",
                            "source_text": "按 SQL 排序",
                            "required_field": "major_name",
                            "operation": "text_match",
                            "value": {"raw_sql": "SELECT * FROM admissions"},
                            "priority": 1,
                            "rationale": "不允许候选排序合同携带 SQL。",
                        }
                    ],
                }
            )

    def test_ranking_plan_rejects_plain_sql_inside_unsupported_criteria(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            RankingPlan.model_validate(
                {
                    "criteria": [
                        {
                            "criterion_id": "unsafe",
                            "source_text": "按 SQL 排序",
                            "required_field": "major_name",
                            "operation": "external_prestige_score",
                            "value": {"sql": "SELECT * FROM admissions"},
                            "priority": 1,
                            "rationale": "不允许候选排序合同携带 SQL。",
                        }
                    ],
                }
            )

    def test_verifier_accepts_reviewed_criteria_and_excludes_missing_field(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    {
                        "criterion_id": "province_match",
                        "source_text": "留在广东",
                        "required_field": "school_province",
                        "operation": "equals_preferred_value",
                        "value": "广东",
                        "priority": 2,
                        "rationale": "省份字段已审查，可作为偏好排序条件。",
                    },
                    {
                        "criterion_id": "overseas",
                        "source_text": "不想去境外",
                        "required_field": "school_country_or_region",
                        "operation": "equals_preferred_value",
                        "value": "中国",
                        "priority": 3,
                        "rationale": "当前 schema 缺少国家或地区字段。",
                    },
                    {
                        "criterion_id": "major_text_match",
                        "source_text": "人工智能，计算机",
                        "required_field": "major_name",
                        "operation": "text_match",
                        "value": ["人工智能", "计算机"],
                        "priority": 1,
                        "rationale": "专业名称字段已审查，可用于文本匹配排序。",
                    },
                ],
                "rationale_summary": "先看专业相关性，再看省份偏好。",
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=_base_value_evidence(),
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["major_text_match", "province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual("先看专业相关性，再看省份偏好。", result.verified_plan.rationale_summary)
        self.assertEqual(1, len(result.excluded_criteria))
        self.assertEqual("overseas", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("missing_field", result.excluded_criteria[0]["reason"])
        self.assertEqual(
            "current data lacks country/region.",
            result.excluded_criteria[0]["message"],
        )

    def test_value_bearing_criterion_without_evidence_is_unverified_value(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="near_home",
                        source_text="离家近",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(_registry()).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual([], result.verified_plan.criteria)
        self.assertEqual("near_home", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_untrusted_value_evidence_source_is_unverified_value(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="离家近",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="province_match",
                    field_id="school_province",
                    operation="equals_preferred_value",
                    value="北京",
                    source="llm",
                )
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_mismatched_value_evidence_is_unverified_value(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="广东",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="province_match",
                    field_id="school_province",
                    operation="equals_preferred_value",
                    value="北京",
                )
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_value_evidence_without_field_and_operation_does_not_verify(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[{"source": "value_index", "value": "北京"}],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_value_evidence_missing_operation_does_not_verify(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "field_id": "school_province",
                    "source": "value_index",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_value_evidence_missing_field_id_does_not_verify(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "operation": "equals_preferred_value",
                    "source": "value_index",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_value_index_evidence_without_criterion_id_does_not_verify(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "value_index",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_value_index_evidence_with_matching_criterion_id_verifies(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "criterion_id": "province_match",
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "value_index",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_user_input_evidence_can_bind_by_source_text_without_criterion_id(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="想去北京",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "user_input",
                    "source_text": "想去北京",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_user_input_evidence_with_wrong_source_text_does_not_verify(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="想去北京",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "user_input",
                    "source_text": "想去上海",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_user_input_evidence_with_matching_criterion_id_ignores_source_text(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="想去北京",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "criterion_id": "province_match",
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "user_input",
                    "source_text": "想去上海",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_confirmed_boundary_matching_criterion_id_ignores_source_text(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="想去北京",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "criterion_id": "province_match",
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "confirmed_boundary",
                    "source_text": "想去上海",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_user_input_evidence_wrong_criterion_id_does_not_bind_by_source_text(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="想去北京",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "criterion_id": "other_candidate",
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "user_input",
                    "source_text": "想去北京",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_confirmed_boundary_source_text_only_verifies(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        source_text="确认去北京",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "confirmed_boundary",
                    "source_text": "确认去北京",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_reviewed_policy_without_criterion_id_does_not_verify(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "reviewed_policy",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("province_match", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])

    def test_reviewed_policy_with_matching_criterion_id_verifies(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_match",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                {
                    "criterion_id": "province_match",
                    "field_id": "school_province",
                    "operation": "equals_preferred_value",
                    "source": "reviewed_policy",
                    "value": "北京",
                }
            ],
        ).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["province_match"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_numeric_distance_requires_matching_value_evidence(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="rank_distance",
                        source_text="我的位次是 12000",
                        required_field="major_min_rank",
                        operation="numeric_distance_to_user_value",
                        value="12000",
                    )
                ]
            }
        )

        missing_result = RankingVerifier(_registry()).verify(plan)
        verified_result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="rank_distance",
                    field_id="major_min_rank",
                    operation="numeric_distance_to_user_value",
                    value=12000,
                )
            ],
        ).verify(plan)

        self.assertFalse(missing_result.ok)
        self.assertEqual("unverified_value", missing_result.excluded_criteria[0]["reason"])
        self.assertTrue(verified_result.ok)
        self.assertEqual(
            ["rank_distance"],
            [
                criterion.criterion_id
                for criterion in verified_result.verified_plan.criteria
            ],
        )

    def test_numeric_directional_operations_do_not_require_value_evidence(
        self,
    ) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="rank_higher",
                        source_text="位次更靠前更好",
                        required_field="major_min_rank",
                        operation="numeric_higher_is_better",
                        value=None,
                    ),
                    _criterion_payload(
                        criterion_id="rank_lower",
                        source_text="位次数值越小越好",
                        required_field="major_min_rank",
                        operation="numeric_lower_is_better",
                        value=None,
                        priority=2,
                    ),
                ]
            }
        )

        result = RankingVerifier(_registry()).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            ["rank_higher", "rank_lower"],
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
        )
        self.assertEqual([], result.excluded_criteria)

    def test_numeric_operation_on_string_field_is_excluded(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="major_numeric",
                        operation="numeric_higher_is_better",
                        value=None,
                    )
                ]
            }
        )

        result = RankingVerifier(_registry()).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual([], result.verified_plan.criteria)
        self.assertEqual("major_numeric", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_invalid_direction_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            RankingPlan.model_validate(
                {
                    "criteria": [
                        _criterion_payload(direction="sideways"),
                    ]
                }
            )

    def test_text_match_rejects_plain_string_empty_list_and_non_string_items(
        self,
    ) -> None:
        for value in ("计算机", [], ["计算机", 1]):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    RankingPlan.model_validate(
                        {"criteria": [_criterion_payload(value=value)]}
                    )

    def test_in_preferred_set_rejects_non_list_and_empty_list(self) -> None:
        for value in ("广东", []):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    RankingPlan.model_validate(
                        {
                            "criteria": [
                                _criterion_payload(
                                    operation="in_preferred_set",
                                    value=value,
                                )
                            ]
                        }
                    )

    def test_numeric_distance_rejects_dict_and_nonnumeric_string(self) -> None:
        for value in ({"target": 1000}, "一万名"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    RankingPlan.model_validate(
                        {
                            "criteria": [
                                _criterion_payload(
                                    operation="numeric_distance_to_user_value",
                                    required_field="major_min_rank",
                                    value=value,
                                )
                            ]
                        }
                    )

    def test_boolean_preferred_value_rejects_unsupported_shape(self) -> None:
        for value in ("maybe", ["是"]):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    RankingPlan.model_validate(
                        {
                            "criteria": [
                                _criterion_payload(
                                    operation="boolean_preferred_value",
                                    value=value,
                                )
                            ]
                        }
                    )

    def test_numeric_equals_rejects_nonnumeric_string_value(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="rank_equals_city",
                        source_text="最低位次等于广东",
                        required_field="major_min_rank",
                        operation="equals_preferred_value",
                        value="广东",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="rank_equals_city",
                    field_id="major_min_rank",
                    operation="equals_preferred_value",
                    value="广东",
                )
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual([], result.verified_plan.criteria)
        self.assertEqual("rank_equals_city", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_numeric_in_set_rejects_mixed_nonnumeric_values(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="rank_in_mixed_set",
                        source_text="最低位次在混合集合内",
                        required_field="major_min_rank",
                        operation="in_preferred_set",
                        value=[1000, "广东"],
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="rank_in_mixed_set",
                    field_id="major_min_rank",
                    operation="in_preferred_set",
                    value=[1000, "广东"],
                )
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual([], result.verified_plan.criteria)
        self.assertEqual(
            "rank_in_mixed_set",
            result.excluded_criteria[0]["criterion_id"],
        )
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_boolean_preferred_value_requires_boolean_field_type(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="province_boolean",
                        source_text="省份为是",
                        required_field="school_province",
                        operation="boolean_preferred_value",
                        value="是",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="province_boolean",
                    field_id="school_province",
                    operation="boolean_preferred_value",
                    value="是",
                )
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual([], result.verified_plan.criteria)
        self.assertEqual("province_boolean", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_boolean_preferred_value_verifies_on_boolean_field(self) -> None:
        for value in (True, "是"):
            with self.subTest(value=value):
                plan = RankingPlan.model_validate(
                    {
                        "criteria": [
                            _criterion_payload(
                                criterion_id="dorm_boolean",
                                source_text="希望公办住宿",
                                required_field="has_public_dorm",
                                operation="boolean_preferred_value",
                                value=value,
                            )
                        ]
                    }
                )

                result = RankingVerifier(
                    _registry(),
                    value_evidence=[
                        _evidence(
                            criterion_id="dorm_boolean",
                            field_id="has_public_dorm",
                            operation="boolean_preferred_value",
                            value=value,
                        )
                    ],
                ).verify(plan)

                self.assertTrue(result.ok)
                self.assertEqual(
                    ["dorm_boolean"],
                    [
                        criterion.criterion_id
                        for criterion in result.verified_plan.criteria
                    ],
                )
                self.assertEqual([], result.excluded_criteria)

    def test_boolean_equals_rejects_non_boolean_compatible_value(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="dorm_maybe",
                        source_text="也许有住宿",
                        required_field="has_public_dorm",
                        operation="equals_preferred_value",
                        value="maybe",
                    )
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[
                _evidence(
                    criterion_id="dorm_maybe",
                    field_id="has_public_dorm",
                    operation="equals_preferred_value",
                    value="maybe",
                )
            ],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual("dorm_maybe", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_boolean_equals_verifies_boolean_compatible_value_with_evidence(
        self,
    ) -> None:
        for value in (True, "是"):
            with self.subTest(value=value):
                plan = RankingPlan.model_validate(
                    {
                        "criteria": [
                            _criterion_payload(
                                criterion_id="dorm_equals",
                                source_text="希望公办住宿",
                                required_field="has_public_dorm",
                                operation="equals_preferred_value",
                                value=value,
                            )
                        ]
                    }
                )

                result = RankingVerifier(
                    _registry(),
                    value_evidence=[
                        _evidence(
                            criterion_id="dorm_equals",
                            field_id="has_public_dorm",
                            operation="equals_preferred_value",
                            value=value,
                        )
                    ],
                ).verify(plan)

                self.assertTrue(result.ok)
                self.assertEqual(
                    ["dorm_equals"],
                    [
                        criterion.criterion_id
                        for criterion in result.verified_plan.criteria
                    ],
                )

    def test_unknown_operation_is_preserved_and_excluded_by_verifier(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(
                        criterion_id="prestige",
                        source_text="学校好一点",
                        operation="external_prestige_score",
                        value={"source": "not executable"},
                        rationale="外部声望分不在通用排序操作白名单内。",
                    )
                ]
            }
        )

        result = RankingVerifier(_registry()).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual([], result.verified_plan.criteria)
        self.assertEqual("prestige", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_missing_field_unknown_operation_is_unsupported_operation(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(),
                    _criterion_payload(
                        criterion_id="missing_prestige",
                        source_text="境外名校优先",
                        required_field="school_country_or_region",
                        operation="external_prestige_score",
                        value=None,
                        priority=2,
                    ),
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[_evidence()],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual(["major_text_match"], [
            criterion.criterion_id for criterion in result.verified_plan.criteria
        ])
        self.assertEqual("missing_prestige", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unsupported_operation", result.excluded_criteria[0]["reason"])

    def test_mixed_verified_and_unsupported_operation_has_ok_false(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(),
                    _criterion_payload(
                        criterion_id="prestige",
                        source_text="学校好一点",
                        operation="external_prestige_score",
                        value=None,
                        priority=2,
                    ),
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[_evidence()],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual(["major_text_match"], [
            criterion.criterion_id for criterion in result.verified_plan.criteria
        ])
        self.assertEqual("prestige", result.excluded_criteria[0]["criterion_id"])

    def test_mixed_verified_and_unverified_value_has_ok_false(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    _criterion_payload(),
                    _criterion_payload(
                        criterion_id="near_home",
                        source_text="离家近",
                        required_field="school_province",
                        operation="equals_preferred_value",
                        value="北京",
                        priority=2,
                    ),
                ]
            }
        )

        result = RankingVerifier(
            _registry(),
            value_evidence=[_evidence()],
        ).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual(["major_text_match"], [
            criterion.criterion_id for criterion in result.verified_plan.criteria
        ])
        self.assertEqual("near_home", result.excluded_criteria[0]["criterion_id"])
        self.assertEqual("unverified_value", result.excluded_criteria[0]["reason"])


if __name__ == "__main__":
    unittest.main()
