import unittest

import pydantic

from src.semantic import (
    QueryAST,
    QueryFilter,
    QuerySort,
    QueryVerificationIssue,
    VerifiedQueryPlan,
)


class QueryASTTest(unittest.TestCase):
    def test_query_ast_rejects_raw_sql_payload(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            QueryAST.from_candidate(
                {
                    "raw_sql": "SELECT * FROM admissions",
                    "filters": [],
                    "sort": [],
                }
            )

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

    def test_verified_query_plan_accepts_dict_records(self) -> None:
        plan = VerifiedQueryPlan(
            intent="table_filter",
            table_name="admissions",
            select_columns=[
                {"field_id": "university_name", "column": "院校名称"},
                {"field_id": "major_name", "column": "专业名称"},
            ],
            filters=[
                {"field_id": "year", "op": "eq", "value": 2025},
            ],
            sort=[
                {"field_id": "major_min_rank", "direction": "asc"},
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
                {"field_id": "university_name", "column": "院校名称"},
                {"field_id": "major_name", "column": "专业名称"},
            ],
        )
        self.assertEqual(
            plan.filters,
            [{"field_id": "year", "op": "eq", "value": 2025}],
        )
        self.assertEqual(
            plan.sort,
            [{"field_id": "major_min_rank", "direction": "asc"}],
        )
        self.assertEqual(
            plan.answerable_intents,
            [{"field_id": "year", "reason": "schema_field"}],
        )
        self.assertEqual(
            plan.unanswerable_intents,
            [{"field_id": "city", "reason": "missing_field"}],
        )


if __name__ == "__main__":
    unittest.main()
