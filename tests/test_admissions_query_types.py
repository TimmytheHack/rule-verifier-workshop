from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.api.workbench import WorkbenchConfig, run_workbench
from tests.warehouse_test_utils import (
    _test_warehouse_paths,
    run_workbench_with_test_warehouse,
)
from tests.workbench_contract_utils import assert_workbench_contract


GROUP_DETAIL_QUERY = (
    "列出 2025 年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数"
)
GROUP_DETAIL_NO_YEAR_QUERY = (
    "列出深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数"
)
RECOMMENDATION_QUERY = (
    "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省"
)


class AdmissionsQueryTypesTest(unittest.TestCase):
    def test_group_detail_report_returns_top_group_and_nested_majors(self) -> None:
        result = _run(GROUP_DETAIL_QUERY)

        assert_workbench_contract(self, result)
        self.assertEqual(result["query_type"], "group_detail_report")
        self.assertEqual(result["status"], "ok")
        groups = result["result_sections"]["groups"]
        self.assertGreaterEqual(len(groups), 1)
        self.assertEqual(groups[0]["group_code"], "10590221")
        self.assertEqual(groups[0]["group_metric_score"], 628)
        self.assertTrue(groups[0]["majors"])
        self.assertIn("min_score", groups[0]["majors"][0])
        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(execution["query_type"], "group_detail_report")
        self.assertEqual(execution["group_by"], ["院校专业组代码", "专业组名称"])
        self.assertEqual(execution["metric"]["field_id"], "group_min_score_2024")
        self.assertGreater(execution["nested_result_count"], 0)

    def test_group_detail_defaults_latest_year_when_missing(self) -> None:
        result = _run(GROUP_DETAIL_NO_YEAR_QUERY)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["query_type"], "group_detail_report")
        self.assertIn("default_year_used", _warning_codes(result))
        self.assertEqual(result["evidence_pack"]["execution_summary"]["params"][0], 2024)

    def test_group_detail_uses_configured_default_for_highest_metric(self) -> None:
        result = _run(GROUP_DETAIL_QUERY)

        self.assertIn("metric_default_used", _warning_codes(result))
        metric = result["evidence_pack"]["execution_summary"]["metric"]
        self.assertEqual(metric["field"], "专业组最低分1")
        self.assertEqual(metric["direction"], "DESC")

    def test_score_based_recommendation_returns_reach_match_safety(self) -> None:
        result = _run(RECOMMENDATION_QUERY)

        assert_workbench_contract(self, result)
        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(result["result_sections"]), {"reach", "match", "safety"})
        self.assertGreater(result["result_count"], 0)
        self.assertTrue(
            any(
                section["items"]
                for section in result["result_sections"].values()
            )
        )
        self.assertNotIn("录取概率高", result["answer"])
        self.assertIn("不是录取概率判断", result["answer"])
        self.assertIn("历史最低分/最低位次", result["answer"])

    def test_score_without_rank_adds_warning(self) -> None:
        result = _run(RECOMMENDATION_QUERY)

        self.assertIn("score_without_rank", _warning_codes(result))
        self.assertEqual(
            result["evidence_pack"]["execution_summary"]["metric"],
            "score_margin",
        )

    def test_rank_margin_takes_priority_when_rank_is_available(self) -> None:
        query = "我今年高考分数 630，位次 9000，想读人工智能、计算机，想留在广东省"
        result = _run(query)

        self.assertEqual(result["query_type"], "recommendation")
        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(execution["metric"], "rank_margin")
        self.assertEqual(execution["sort"], [{"field": "rank_margin", "direction": "ASC"}])
        self.assertTrue(
            any(
                "rank_margin" in item
                for section in result["result_sections"].values()
                for item in section["items"]
            )
        )

    def test_overseas_preference_is_not_executed_without_schema_field(self) -> None:
        result = _run(RECOMMENDATION_QUERY)

        self.assertIn(
            "school_country_or_region",
            [item["field_id"] for item in result["no_schema_field_preferences"]],
        )
        self.assertNotIn(
            "planned_exclude_school_country_or_region",
            [item["id"] for item in result["executed_filters"]],
        )
        sql = result["evidence_pack"]["execution_summary"]["sql"]
        self.assertNotIn("school_country_or_region", sql)

    def test_overseas_preference_executes_when_reviewed_field_exists(self) -> None:
        with TemporaryDirectory() as directory:
            domain_dir = _copy_admissions_domain(Path(directory))
            schema_path = domain_dir / "schema_registry.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["fields"]["school_country_or_region"]["source_column"] = "所在省"
            schema["fields"]["school_country_or_region"]["status"] = "approved"
            schema_path.write_text(
                json.dumps(schema, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            workbook_path, database_path, index_path = _test_warehouse_paths()
            with patch("src.api.workbench.WORKBOOK_NAME", workbook_path):
                with patch("src.api.workbench.WAREHOUSE_DATABASE_PATH", database_path):
                    with patch(
                        "src.api.workbench.WAREHOUSE_VALUE_INDEX_PATH",
                        index_path,
                    ):
                        result = run_workbench(
                            WorkbenchConfig(
                                domain_name="admissions",
                                domain_path=str(domain_dir),
                                user_input=RECOMMENDATION_QUERY,
                                soft_preferences={"prompt": RECOMMENDATION_QUERY},
                                extractor="regex",
                            )
                        )

        self.assertIn(
            "planned_exclude_school_country_or_region",
            [item["id"] for item in result["executed_filters"]],
        )
        self.assertFalse(result["no_schema_field_preferences"])

    def test_guangdong_school_province_filter_executes(self) -> None:
        result = _run(RECOMMENDATION_QUERY)

        self.assertIn(
            "planned_school_province",
            [item["id"] for item in result["executed_filters"]],
        )
        self.assertTrue(
            all(
                item["school_province"] == "广东"
                for section in result["result_sections"].values()
                for item in section["items"]
            )
        )

    def test_frontend_deterministic_fields_override_natural_language(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input="我今年高考分数 630，想读人工智能，想留在广东省",
                hard_filters={
                    "user_score": 630,
                    "major_keywords": ["软件工程"],
                    "preferred_school_provinces": ["广东"],
                },
                soft_preferences={
                    "prompt": "我今年高考分数 630，想读人工智能，想留在广东省"
                },
                extractor="regex",
            )
        )

        self.assertEqual(result["query_type"], "recommendation")
        executed = {
            item["id"]: item
            for item in result["executed_filters"]
        }
        self.assertEqual(executed["planned_major_keywords"]["value"], ["软件工程"])
        params = result["evidence_pack"]["execution_summary"]["params"]
        self.assertIn("软件工程", params)
        self.assertNotIn("人工智能", params)

    def test_planned_sql_is_parameterized_and_traced(self) -> None:
        result = _run(GROUP_DETAIL_QUERY)

        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(result["query_type"], execution["query_type"])
        self.assertEqual(result["debug_trace"]["execution"]["sql"], execution["sql"])
        self.assertEqual(result["debug_trace"]["execution"]["params"], execution["params"])
        self.assertNotIn("深圳大学", execution["sql"])
        self.assertIn("深圳大学", execution["params"])
        self.assertNotIn("2025", execution["sql"])


def _run(query: str) -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=query,
            soft_preferences={"prompt": query},
            extractor="regex",
        )
    )


def _warning_codes(result: dict[str, object]) -> set[str]:
    return {warning["code"] for warning in result["warnings"]}


def _copy_admissions_domain(root: Path) -> Path:
    source = Path("domains/admissions")
    target = root / "admissions"
    shutil.copytree(source, target)
    return target


if __name__ == "__main__":
    unittest.main()
