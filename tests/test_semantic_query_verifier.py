import unittest

import pydantic

from src.domains import DomainConfig
from src.semantic import (
    QueryAST,
    QueryFilter,
    QuerySort,
    QueryVerificationIssue,
    VerifiedQueryPlan,
)
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.query_verifier import SemanticQueryVerifier
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from tests.semantic_test_utils import new_admissions_dataset


class QueryASTTest(unittest.TestCase):
    def _verified_plan_payload(self) -> dict:
        return {
            "intent": "table_filter",
            "table_name": "admissions",
            "select_columns": [
                {"field_id": "university_name", "source_column": "院校名称"},
            ],
            "filters": [
                {
                    "field_id": "year",
                    "source_column": "年份",
                    "op": "eq",
                    "value": 2025,
                },
            ],
            "sort": [
                {
                    "field_id": "major_min_rank",
                    "source_column": "专业最低位次",
                    "direction": "asc",
                },
            ],
            "limit": 30,
            "answerable_intents": [{"field_id": "year"}],
            "unanswerable_intents": [],
        }

    def test_query_ast_rejects_raw_sql_payload(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "raw_sql": "SELECT * FROM admissions",
                    "filters": [],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_raw_sql_payload_even_when_none(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "raw_sql": None,
                    "filters": [],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_filter_extra_raw_sql(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [
                        {
                            "field_id": "year",
                            "op": "eq",
                            "value": 2025,
                            "raw_sql": "year = 2025",
                        },
                    ],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_filter_value_nested_raw_sql(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [
                        {
                            "field_id": "year",
                            "op": "eq",
                            "value": {
                                "metadata": {"raw_sql": "year = 2025"},
                            },
                        },
                    ],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_sort_extra_raw_sql(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [],
                    "sort": [
                        {
                            "field_id": "major_min_rank",
                            "direction": "asc",
                            "raw_sql": "major_min_rank ASC",
                        },
                    ],
                }
            )

    def test_query_ast_schema_excludes_raw_sql(self) -> None:
        properties = QueryAST.model_json_schema()["properties"]

        self.assertNotIn("raw_sql", properties)

    def test_query_ast_rejects_blank_intent(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "intent": " ",
                    "filters": [],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_blank_source(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "source": " ",
                    "filters": [],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_blank_filter_field_id(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [
                        {"field_id": " ", "op": "eq", "value": 2025},
                    ],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_blank_filter_op(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [
                        {"field_id": "year", "op": " ", "value": 2025},
                    ],
                    "sort": [],
                }
            )

    def test_query_ast_rejects_blank_sort_field_id(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [],
                    "sort": [{"field_id": " ", "direction": "asc"}],
                }
            )

    def test_query_ast_rejects_non_positive_limit(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "filters": [],
                    "sort": [],
                    "limit": 0,
                }
            )

    def test_query_ast_clamps_overlarge_limit(self) -> None:
        query_ast = QueryAST.from_candidate(
            {
                "filters": [],
                "sort": [],
                "limit": 500,
            }
        )

        self.assertEqual(query_ast.limit, 100)

    def test_query_ast_normalizes_filters_and_sort(self) -> None:
        query_ast = QueryAST.from_candidate(
            {
                "intent": "table_filter",
                "select": ["university_name", "major_name"],
                "filters": [
                    {"field_id": "year", "op": "eq", "value": 2025},
                    {
                        "field_id": "major_min_rank",
                        "op": "between",
                        "value": [10000, 15000],
                    },
                ],
                "sort": [{"field_id": "major_min_rank", "direction": "asc"}],
                "limit": 30,
            }
        )

        self.assertEqual(query_ast.intent, "table_filter")
        self.assertEqual(query_ast.select, ["university_name", "major_name"])
        self.assertEqual(
            query_ast.filters,
            [
                QueryFilter(field_id="year", op="eq", value=2025),
                QueryFilter(
                    field_id="major_min_rank",
                    op="between",
                    value=[10000, 15000],
                ),
            ],
        )
        self.assertEqual(
            query_ast.sort,
            [QuerySort(field_id="major_min_rank", direction="asc")],
        )
        self.assertEqual(query_ast.limit, 30)

    def test_verification_issue_serializes(self) -> None:
        issue = QueryVerificationIssue(
            code="missing_field",
            severity="error",
            message="字段不存在。",
            field_id="city",
        )

        self.assertEqual(
            issue.to_dict(),
            {
                "code": "missing_field",
                "severity": "error",
                "message": "字段不存在。",
                "field_id": "city",
            },
        )

    def test_verification_issue_serializes_non_reserved_details(self) -> None:
        issue = QueryVerificationIssue(
            code="missing_field",
            severity="error",
            message="字段不存在。",
            field_id="city",
            details={"candidate_id": "cand_001", "source": "schema"},
        )

        self.assertEqual(
            issue.to_dict(),
            {
                "code": "missing_field",
                "severity": "error",
                "message": "字段不存在。",
                "field_id": "city",
                "candidate_id": "cand_001",
                "source": "schema",
            },
        )
        self.assertNotIn("details", issue.to_dict())

    def test_verification_issue_rejects_nested_raw_sql_details(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryVerificationIssue(
                code="missing_field",
                severity="error",
                message="字段不存在。",
                field_id="city",
                details={"metadata": {"raw_sql": "city = '广州'"}},
            )

    def test_verified_query_plan_accepts_dict_records(self) -> None:
        plan = VerifiedQueryPlan(
            intent="table_filter",
            table_name="admissions",
            select_columns=[
                {"field_id": "university_name", "source_column": "院校名称"},
                {"field_id": "major_name", "source_column": "专业名称"},
            ],
            filters=[
                {
                    "field_id": "year",
                    "source_column": "年份",
                    "op": "eq",
                    "value": 2025,
                },
            ],
            sort=[
                {
                    "field_id": "major_min_rank",
                    "source_column": "专业最低位次",
                    "direction": "ASC",
                },
            ],
            limit=30,
            answerable_intents=[
                {"field_id": "year", "reason": "schema_field"},
            ],
            unanswerable_intents=[
                {"field_id": "city", "reason": "missing_field"},
            ],
        )

        self.assertEqual(
            plan.select_columns,
            [
                {"field_id": "university_name", "source_column": "院校名称"},
                {"field_id": "major_name", "source_column": "专业名称"},
            ],
        )
        self.assertEqual(
            plan.filters,
            [
                {
                    "field_id": "year",
                    "source_column": "年份",
                    "op": "eq",
                    "value": 2025,
                }
            ],
        )
        self.assertEqual(
            plan.sort,
            [
                {
                    "field_id": "major_min_rank",
                    "source_column": "专业最低位次",
                    "direction": "asc",
                }
            ],
        )
        self.assertEqual(
            plan.answerable_intents,
            [{"field_id": "year", "reason": "schema_field"}],
        )
        self.assertEqual(
            plan.unanswerable_intents,
            [{"field_id": "city", "reason": "missing_field"}],
        )

    def test_verified_query_plan_rejects_top_level_extra(self) -> None:
        payload = self._verified_plan_payload()
        payload["raw_sql"] = "SELECT * FROM admissions"

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_select_extra_key(self) -> None:
        payload = self._verified_plan_payload()
        payload["select_columns"][0]["raw_sql"] = "院校名称"

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_filter_extra_key(self) -> None:
        payload = self._verified_plan_payload()
        payload["filters"][0]["raw_sql"] = "年份 = 2025"

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_sort_extra_key(self) -> None:
        payload = self._verified_plan_payload()
        payload["sort"][0]["raw_sql"] = "专业最低位次 ASC"

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_filter_value_nested_raw_sql(self) -> None:
        payload = self._verified_plan_payload()
        payload["filters"][0]["value"] = {
            "metadata": {"raw_sql": "year = 2025"},
        }

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_answerable_intent_raw_sql(self) -> None:
        payload = self._verified_plan_payload()
        payload["answerable_intents"][0]["raw_sql"] = "year = 2025"

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_answerable_intent_nested_raw_sql(self) -> None:
        payload = self._verified_plan_payload()
        payload["answerable_intents"][0]["metadata"] = {
            "raw_sql": "year = 2025",
        }

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_unanswerable_intent_raw_sql(self) -> None:
        payload = self._verified_plan_payload()
        payload["unanswerable_intents"] = [
            {
                "field_id": "city",
                "reason": "missing_field",
                "raw_sql": "city = '广州'",
            }
        ]

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_rejects_unanswerable_intent_nested_raw_sql(self) -> None:
        payload = self._verified_plan_payload()
        payload["unanswerable_intents"] = [
            {
                "field_id": "city",
                "reason": "missing_field",
                "metadata": {"raw_sql": "city = '广州'"},
            }
        ]

        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(**payload)

    def test_verified_query_plan_allows_non_raw_sql_metadata(self) -> None:
        payload = self._verified_plan_payload()
        payload["filters"][0]["value"] = {"metadata": {"basis": "schema"}}
        payload["answerable_intents"][0]["metadata"] = {
            "basis": "schema",
            "capability": "filter",
        }
        payload["unanswerable_intents"] = [
            {
                "field_id": "city",
                "metadata": {"basis": "missing_schema"},
            }
        ]

        plan = VerifiedQueryPlan(**payload)

        self.assertEqual(plan.filters[0]["value"], {"metadata": {"basis": "schema"}})
        self.assertEqual(
            plan.answerable_intents[0]["metadata"],
            {"basis": "schema", "capability": "filter"},
        )
        self.assertEqual(
            plan.unanswerable_intents[0]["metadata"],
            {"basis": "missing_schema"},
        )

    def test_verified_query_plan_rejects_select_without_source_column(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(
                intent="table_filter",
                table_name="admissions",
                select_columns=[
                    {"field_id": "university_name"},
                ],
                filters=[],
                sort=[],
                limit=30,
                answerable_intents=[],
                unanswerable_intents=[],
            )

    def test_verified_query_plan_rejects_filter_without_value_key(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(
                intent="table_filter",
                table_name="admissions",
                select_columns=[],
                filters=[
                    {
                        "field_id": "year",
                        "source_column": "年份",
                        "op": "eq",
                    },
                ],
                sort=[],
                limit=30,
                answerable_intents=[],
                unanswerable_intents=[],
            )

    def test_verified_query_plan_rejects_blank_table_name(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(
                intent="table_filter",
                table_name="",
                select_columns=[],
                filters=[],
                sort=[],
                limit=30,
                answerable_intents=[],
                unanswerable_intents=[],
            )

    def test_verified_query_plan_rejects_non_positive_limit(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            VerifiedQueryPlan(
                intent="table_filter",
                table_name="admissions",
                select_columns=[],
                filters=[],
                sort=[],
                limit=0,
                answerable_intents=[],
                unanswerable_intents=[],
            )

    def test_verification_issue_rejects_reserved_detail_keys(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryVerificationIssue(
                code="missing_field",
                severity="error",
                message="字段不存在。",
                field_id="city",
                details={"severity": "warning"},
            )


class SemanticQueryVerifierTest(unittest.TestCase):
    def test_verifier_accepts_reviewed_fields_and_ops(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(
            DomainConfig.load("admissions"),
            graph,
        )
        ast = QueryAST.from_candidate(
            {
                "intent": "table_filter",
                "select": ["university_name", "major_name", "major_min_rank"],
                "filters": [
                    {"field_id": "year", "op": "eq", "value": 2025},
                    {
                        "field_id": "major_min_rank",
                        "op": "between",
                        "value": [9000, 18000],
                    },
                ],
                "sort": [{"field_id": "major_min_rank", "direction": "asc"}],
                "limit": 20,
            }
        )

        result = SemanticQueryVerifier(registry, table_name="admissions").verify(ast)

        self.assertTrue(result.ok)
        self.assertEqual(result.plan.table_name, "admissions")
        self.assertEqual(result.plan.filters[0]["source_column"], "年份")
        self.assertEqual(result.plan.filters[1]["source_column"], "最低位次")
        self.assertEqual(result.issues, [])

    def test_verifier_rejects_unavailable_city_and_tuition(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(
            DomainConfig.load("admissions"),
            graph,
        )
        ast = QueryAST.from_candidate(
            {
                "intent": "table_filter",
                "select": [
                    "university_name",
                    "major_name",
                    "city",
                    "tuition_yuan_per_year",
                ],
                "filters": [
                    {"field_id": "city", "op": "contains", "value": "广州"},
                    {
                        "field_id": "tuition_yuan_per_year",
                        "op": "<=",
                        "value": 20000,
                    },
                ],
                "sort": [],
                "limit": 20,
            }
        )

        result = SemanticQueryVerifier(registry, table_name="admissions").verify(ast)

        self.assertFalse(result.ok)
        self.assertEqual(
            [issue.code for issue in result.issues],
            ["missing_field", "missing_field", "missing_field", "missing_field"],
        )
        self.assertEqual(
            [item["field_id"] for item in result.unanswerable_intents],
            ["city", "tuition_yuan_per_year", "city", "tuition_yuan_per_year"],
        )


if __name__ == "__main__":
    unittest.main()
