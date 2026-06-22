from __future__ import annotations

import unittest

from src.semantic.query_ast import VerifiedQueryPlan
from src.semantic.sql_builder import SemanticSQLBuilder


class SemanticSQLBuilderTest(unittest.TestCase):
    def test_builds_parameterized_sql(self) -> None:
        plan = VerifiedQueryPlan(
            intent="table_filter",
            table_name="admissions",
            select_columns=[
                {"field_id": "university_name", "source_column": "院校名称"},
                {"field_id": "major_name", "source_column": "专业"},
                {"field_id": "major_min_rank", "source_column": "最低位次"},
            ],
            filters=[
                {"field_id": "year", "source_column": "年份", "op": "eq", "value": 2025},
                {
                    "field_id": "major_min_rank",
                    "source_column": "最低位次",
                    "op": "between",
                    "value": [9000, 18000],
                },
            ],
            sort=[
                {
                    "field_id": "major_min_rank",
                    "source_column": "最低位次",
                    "direction": "asc",
                }
            ],
            limit=20,
            answerable_intents=[],
            unanswerable_intents=[],
        )

        built = SemanticSQLBuilder().build(plan)

        self.assertEqual(
            built.sql,
            'SELECT "院校名称" AS "university_name", "专业" AS "major_name", '
            '"最低位次" AS "major_min_rank" FROM "admissions" '
            'WHERE "年份" = ? AND "最低位次" BETWEEN ? AND ? '
            'ORDER BY "最低位次" ASC NULLS LAST LIMIT ?',
        )
        self.assertEqual(built.params, [2025, 9000, 18000, 20])


if __name__ == "__main__":
    unittest.main()
