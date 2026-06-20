from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pandas as pd

from src.executors.duckdb_executor import DuckDBExecutor


def _write_database(path: Path, dataframe: pd.DataFrame) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.register("source_dataframe", dataframe)
        connection.execute(
            'CREATE OR REPLACE TABLE "admissions" AS SELECT * FROM source_dataframe'
        )


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": 1,
                "生源地": "广东",
                "科类": "物理",
                "选科要求": "不限",
                "院校名称": "广州大学",
                "院校专业组代码": "201",
                "专业代码": "001",
                "专业名称": "计算机科学与技术",
                "专业全称": "计算机科学与技术",
                "城市": "广州",
                "学费": "6850元/年",
                "专业组最低位次1": 32000,
                "最低位次1": 30000,
                "院校排名": 100,
            },
            {
                "ID": 2,
                "生源地": "广东",
                "科类": "物理",
                "选科要求": "不限",
                "院校名称": "深圳大学",
                "院校专业组代码": "202",
                "专业代码": "002",
                "专业名称": "软件工程",
                "专业全称": "软件工程",
                "城市": "深圳",
                "学费": "45000元/年",
                "专业组最低位次1": 42000,
                "最低位次1": 39000,
                "院校排名": 80,
            },
            {
                "ID": 3,
                "生源地": "广东",
                "科类": "历史",
                "选科要求": "不限",
                "院校名称": "佛山大学",
                "院校专业组代码": "203",
                "专业代码": "003",
                "专业名称": "法学",
                "专业全称": "法学",
                "城市": "佛山",
                "学费": "6000元/年",
                "专业组最低位次1": 25000,
                "最低位次1": 24000,
                "院校排名": 200,
            },
        ]
    )


class DuckDBExecutorTest(unittest.TestCase):
    def test_compiles_rank_tuition_city_major_and_group_code_as_params(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_source_province",
                        "field": "生源地",
                        "operator": "eq",
                        "value": "广东",
                    },
                    {
                        "rule_id": "e_subject_type",
                        "field": "科类",
                        "operator": "eq",
                        "value": "物理",
                    },
                    {
                        "rule_id": "e_city",
                        "field": "城市",
                        "operator": "in_contains",
                        "value": ["广州", "深圳"],
                    },
                    {
                        "rule_id": "e_major_keyword",
                        "field": "专业名称",
                        "operator": "contains_any",
                        "value": ["计算机"],
                    },
                    {
                        "rule_id": "e_group_code",
                        "field": "院校专业组代码",
                        "operator": "eq",
                        "value": "201",
                    },
                    {
                        "rule_id": "e_rank_floor",
                        "field": "专业组最低位次1",
                        "operator": ">=",
                        "value": 30000,
                    },
                    {
                        "rule_id": "e_tuition_cap_explicit",
                        "field": "学费",
                        "operator": "<=",
                        "value": 20000,
                    },
                ],
                user_rank=30000,
                top_k=3,
            )

        self.assertEqual([row["ID"] for row in result.rows], [1])
        self.assertEqual(result.audit.input_row_count, 3)
        self.assertEqual(result.audit.filtered_row_count, 1)
        self.assertEqual(result.audit.top_k, 3)
        self.assertIn("院校专业组代码", result.audit.sql)
        for user_value in ["广东", "物理", "广州", "深圳", "计算机", "201"]:
            self.assertNotIn(user_value, result.audit.sql)
            self.assertIn(user_value, result.audit.params)
        self.assertIn(30000.0, result.audit.params)
        self.assertIn(20000.0, result.audit.params)

    def test_empty_result_keeps_sql_audit(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_city",
                        "field": "城市",
                        "operator": "in_contains",
                        "value": ["珠海"],
                    }
                ],
                user_rank=30000,
            )

        self.assertEqual(result.rows, [])
        self.assertEqual(result.audit.filtered_row_count, 0)
        self.assertNotIn("珠海", result.audit.sql)
        self.assertEqual(result.audit.params, ["珠海"])

    def test_illegal_field_fails_instead_of_weakening_filter(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            with self.assertRaisesRegex(ValueError, "unknown field"):
                DuckDBExecutor(database_path).execute(
                    [
                        {
                            "rule_id": "e_bad",
                            "field": "不存在字段",
                            "operator": "eq",
                            "value": "广东",
                        }
                    ]
                )

    def test_confirmed_candidate_rules_enter_hard_filter(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_source_province",
                        "derived_from": "d_source_province",
                        "field": "生源地",
                        "operator": "eq",
                        "value": "广东",
                    },
                    {
                        "rule_id": "e_city",
                        "derived_from": "d_city",
                        "field": "城市",
                        "operator": "in_contains",
                        "value": ["广州", "深圳"],
                    },
                    {
                        "rule_id": "e_tuition_cap",
                        "derived_from": "c_tuition_cap",
                        "field": "学费",
                        "operator": "<=",
                        "value": 20000,
                        "confirmation": "费用上限已确认",
                    },
                ],
                user_rank=30000,
            )

        self.assertEqual([row["ID"] for row in result.rows], [1])
        self.assertEqual(result.audit.skipped_soft_rule_ids, [])
        self.assertIn(20000.0, result.audit.params)
        self.assertEqual(
            result.audit.hard_rule_ids,
            ["e_source_province", "e_city", "e_tuition_cap"],
        )

    def test_confirmed_safety_margin_filters_rank_window(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_source_province",
                        "field": "生源地",
                        "operator": "eq",
                        "value": "广东",
                    },
                    {
                        "rule_id": "e_subject_type",
                        "field": "科类",
                        "operator": "eq",
                        "value": "物理",
                    },
                    {
                        "rule_id": "e_safety_margin",
                        "derived_from": "c_safety_margin",
                        "field": "专业组最低位次1",
                        "operator": "between",
                        "value": [28800, 35200],
                        "confirmation": "位次窗口已确认",
                    },
                ],
                user_rank=32000,
            )

        self.assertEqual([row["ID"] for row in result.rows], [1])
        self.assertEqual(result.audit.skipped_soft_rule_ids, [])
        self.assertEqual(result.audit.params, ["广东", "物理", 28800.0, 35200.0])
        self.assertIn("e_safety_margin", result.audit.hard_rule_ids)

    def test_sort_override_can_show_safer_rank_first(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_source_province",
                        "field": "生源地",
                        "operator": "eq",
                        "value": "广东",
                    },
                    {
                        "rule_id": "e_subject_type",
                        "field": "科类",
                        "operator": "eq",
                        "value": "物理",
                    },
                    {
                        "rule_id": "e_safety_margin",
                        "field": "专业组最低位次1",
                        "operator": "<=",
                        "value": 48000,
                    },
                ],
                user_rank=32000,
                sort_policy_override=[
                    {
                        "helper": "__group_rank_num",
                        "label_field_id": "group_min_rank_2024",
                        "direction": "DESC",
                        "nulls": "LAST",
                    },
                    {
                        "helper": "__id_num",
                        "label_field_id": "row_id",
                        "direction": "ASC",
                        "nulls": "LAST",
                        "optional": True,
                    },
                ],
            )

        self.assertTrue(result.audit.sort_key[0].endswith("DESC NULLS LAST"))
        self.assertEqual([row["ID"] for row in result.rows], [2, 1])
        self.assertIn("ORDER BY", result.audit.sql)
        self.assertIn('"__group_rank_num" DESC NULLS LAST', result.audit.sql)
        self.assertEqual(result.audit.skipped_soft_rule_ids, [])

    def test_sort_override_rejects_unknown_helper(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            with self.assertRaisesRegex(ValueError, "unknown helper"):
                DuckDBExecutor(database_path).execute(
                    [],
                    sort_policy_override=[
                        {
                            "helper": "__not_allowed",
                            "direction": "ASC",
                            "nulls": "LAST",
                        }
                    ],
                )

    def test_sort_override_rejects_invalid_direction(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            with self.assertRaisesRegex(ValueError, "sort direction"):
                DuckDBExecutor(database_path).execute(
                    [],
                    sort_policy_override=[
                        {
                            "helper": "__group_rank_num",
                            "direction": "SIDEWAYS",
                            "nulls": "LAST",
                        }
                    ],
                )

    def test_sort_override_rejects_invalid_nulls(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            with self.assertRaisesRegex(ValueError, "sort nulls"):
                DuckDBExecutor(database_path).execute(
                    [],
                    sort_policy_override=[
                        {
                            "helper": "__group_rank_num",
                            "direction": "ASC",
                            "nulls": "MIDDLE",
                        }
                    ],
                )

    def test_untrusted_or_disabled_rules_do_not_enter_hard_filter(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_source_province",
                        "field": "生源地",
                        "operator": "eq",
                        "value": "广东",
                    },
                    {
                        "rule_id": "e_school_quality",
                        "field": "院校排名",
                        "operator": "<=",
                        "value": 100,
                        "verification_origin": "verified_proposed_rule",
                    },
                    {
                        "rule_id": "e_disabled",
                        "field": "学费",
                        "operator": "<=",
                        "value": 20000,
                        "hard_filter_allowed": False,
                    },
                ],
                user_rank=30000,
            )

        self.assertEqual([row["ID"] for row in result.rows], [3, 1, 2])
        self.assertEqual(
            result.audit.skipped_soft_rule_ids,
            ["e_school_quality", "e_disabled"],
        )
        self.assertEqual(result.audit.hard_rule_ids, ["e_source_province"])
        self.assertNotIn(100.0, result.audit.params)
        self.assertNotIn(20000.0, result.audit.params)


if __name__ == "__main__":
    unittest.main()
