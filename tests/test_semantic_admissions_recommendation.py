from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.generate_domain_pack import load_source_dataset
from src.adapters.data_warehouse import build_structured_store_from_dataset
from src.domains import DomainConfig
from src.semantic.admissions_recommendation import (
    SemanticAdmissionsRecommendationPlanner,
)
from src.semantic.intent_models import (
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)
from tests.semantic_test_utils import NEW_ADMISSIONS_ROWS


class SemanticAdmissionsRecommendationPlannerTest(unittest.TestCase):
    def test_recommendation_executes_grounded_filters_and_preserves_no_schema_preference(
        self,
    ) -> None:
        result = self._run(
            SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_rank=15000),
                preferences=[
                    SemanticPreference(
                        source_text="想读人工智能，计算机",
                        semantic="major_name",
                        op="contains_any",
                        value=["人工智能", "计算机"],
                    ),
                    SemanticPreference(
                        source_text="想留在广东省",
                        semantic="school_province",
                        op="in",
                        value=["广东"],
                    ),
                    SemanticPreference(
                        source_text="不想去国外",
                        semantic="school_country_or_region",
                        op="not_in",
                        value=["国外", "境外", "海外"],
                    ),
                ],
                requested_output=["recommendation_sections", "minimum_rank"],
            )
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.query_type, "recommendation")
        self.assertEqual(
            [row["档位"] for row in result.rows],
            ["冲", "冲", "稳", "保"],
        )
        self.assertEqual(result.rows[0]["院校名称"], "深圳理工大学")
        self.assertEqual(result.rows[0]["专业"], "人工智能")
        self.assertEqual(result.rows[0]["最低录取排名"], 14900)
        self.assertEqual(result.result_sections["safety"][0]["院校名称"], "广东工业大学")
        self.assertNotIn("北京大学", [row["院校名称"] for row in result.rows])
        self.assertNotIn("合作大学", [row["院校名称"] for row in result.rows])
        self.assertEqual(
            result.not_executed_preferences[0]["field_id"],
            "school_country_or_region",
        )
        self.assertEqual(
            result.not_executed_preferences[0]["match_type"],
            "no_schema_field",
        )
        self.assertIn("STRPOS", result.execution_summary["sql"])
        self.assertIn("人工智能", result.execution_summary["params"])
        self.assertEqual(result.execution_summary["basis"], "major_min_rank")
        self.assertEqual(result.execution_summary["special_limit_excluded_count"], 1)
        self.assertEqual(
            result.selection_evidence[0]["reason_codes"],
            [
                "verified_sql_filter",
                "rank_distance_bucket",
                "deterministic_rank_distance_order",
            ],
        )

    def test_valid_rerank_can_reorder_within_valid_candidates(self) -> None:
        result = self._run(
            _recommendation_intent(),
            reranker=_FakeReranker(
                {
                    "items": [
                        {
                            "row_id": "candidate_001",
                            "bucket": "reach",
                            "reason_codes": ["school_tier"],
                            "field_refs": ["是否211"],
                        },
                        {
                            "row_id": "candidate_002",
                            "bucket": "reach",
                            "reason_codes": ["rank_distance"],
                            "field_refs": ["最低录取排名"],
                        },
                        {
                            "row_id": "candidate_003",
                            "bucket": "match",
                            "reason_codes": ["province_match"],
                            "field_refs": ["学校所在"],
                        },
                    ]
                }
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.rows[0]["院校名称"], "深圳大学")
        self.assertEqual(result.rows[0]["rerank_reason_codes"], ["school_tier"])
        self.assertFalse(result.execution_summary["rerank_validation"]["fallback_used"])
        self.assertEqual(
            [row["row_id"] for row in result.result_sections["reach"]],
            ["candidate_001", "candidate_002"],
        )

    def test_invalid_rerank_falls_back_to_deterministic_order(self) -> None:
        result = self._run(
            _recommendation_intent(),
            reranker=_FakeReranker(
                {
                    "items": [
                        {
                            "row_id": "outside_001",
                            "bucket": "reach",
                            "reason_codes": ["rank_distance"],
                        }
                    ]
                }
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.rows[0]["院校名称"], "深圳理工大学")
        self.assertTrue(result.execution_summary["rerank_validation"]["fallback_used"])
        self.assertEqual(
            result.execution_summary["rerank_validation"]["issues"][0]["code"],
            "unknown_row_id",
        )

    def test_score_without_rank_requires_confirmation_before_sql(self) -> None:
        result = self._run(
            SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_score=630),
                preferences=[
                    SemanticPreference(
                        source_text="想读人工智能，计算机",
                        semantic="major_name",
                        op="contains_any",
                        value=["人工智能", "计算机"],
                    )
                ],
            )
        )

        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.execution_summary["sql"], "")
        self.assertEqual(
            [warning["code"] for warning in result.warnings],
            ["score_without_rank"],
        )
        self.assertEqual(
            result.unanswerable_intents[0]["field_id"],
            "user_rank",
        )

    def _run(self, intent: SemanticIntent, reranker=None):
        with TemporaryDirectory() as directory:
            rows = [dict(row) for row in NEW_ADMISSIONS_ROWS]
            rows.extend(_recommendation_rows())
            source_path = Path(directory) / "new_admissions.xlsx"
            pd.DataFrame(rows).to_excel(source_path, index=False)
            dataset = load_source_dataset(source_path)
            database_path = Path(directory) / "admissions.duckdb"
            index_path = Path(directory) / "schema_value_index.json"
            domain_config = DomainConfig.load("admissions")
            build_structured_store_from_dataset(
                dataset=dataset,
                schema_path=domain_config.schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name="admissions",
                source_path=dataset.workbook_path,
            )

            return SemanticAdmissionsRecommendationPlanner(
                domain_config=domain_config,
                database_path=database_path,
                table_name="admissions",
                reranker=reranker,
            ).run(intent)


def _recommendation_rows() -> list[dict[str, object]]:
    base = NEW_ADMISSIONS_ROWS[0]
    return [
        {
            **base,
            "院校名称": "深圳理工大学",
            "专业": "人工智能",
            "专业代码": "080717",
            "所属专业组": "（201）",
            "专业备注": "（普通类）",
            "最低分数": 629,
            "最低位次": 14900,
            "学校所在": "广东",
            "是否985": "否",
            "是否211": "否",
        },
        {
            **base,
            "院校名称": "华南师范大学",
            "专业": "计算机科学与技术",
            "专业代码": "080901",
            "所属专业组": "（236）",
            "专业备注": "（普通类）",
            "最低分数": 620,
            "最低位次": 21000,
            "学校所在": "广东",
            "是否985": "否",
            "是否211": "是",
        },
        {
            **base,
            "院校名称": "广东工业大学",
            "专业": "人工智能",
            "专业代码": "080717",
            "所属专业组": "（206）",
            "专业备注": "（普通类）",
            "最低分数": 610,
            "最低位次": 27000,
            "学校所在": "广东",
            "是否985": "否",
            "是否211": "否",
        },
        {
            **base,
            "院校名称": "合作大学",
            "专业": "计算机科学与技术",
            "专业代码": "080901",
            "所属专业组": "（204）",
            "专业备注": "（中外合作办学）",
            "最低分数": 618,
            "最低位次": 22000,
            "学校所在": "广东",
            "是否985": "否",
            "是否211": "否",
        },
        {
            **base,
            "院校名称": "北京大学",
            "专业": "人工智能",
            "专业代码": "080717",
            "所属专业组": "（203）",
            "专业备注": "（普通类）",
            "最低分数": 690,
            "最低位次": 14800,
            "学校所在": "北京",
            "是否985": "是",
            "是否211": "是",
        },
    ]


def _recommendation_intent() -> SemanticIntent:
    return SemanticIntent(
        query_type="semantic_recommendation",
        user_context=SemanticUserContext(user_rank=15000),
        preferences=[
            SemanticPreference(
                source_text="想读人工智能，计算机",
                semantic="major_name",
                op="contains_any",
                value=["人工智能", "计算机"],
            ),
            SemanticPreference(
                source_text="想留在广东省",
                semantic="school_province",
                op="in",
                value=["广东"],
            ),
        ],
        requested_output=["recommendation_sections", "minimum_rank"],
    )


class _FakeReranker:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def rerank(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


if __name__ == "__main__":
    unittest.main()
