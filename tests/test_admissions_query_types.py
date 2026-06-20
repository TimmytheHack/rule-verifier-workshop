from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.api.admissions_query_planner import AdmissionsQueryPlanner
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
SCORE_ONLY_RECOMMENDATION_QUERY = (
    "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省"
)
RANK_RECOMMENDATION_QUERY = (
    "我今年高考分数 630，位次 9000，想读人工智能、计算机，不想去国外，想留在广东省"
)
RANK_ONLY_RECOMMENDATION_QUERY = (
    "我今年位次 9000，想读人工智能、计算机，想留在广东省，请推荐"
)
RECOMMENDATION_QUERY = RANK_RECOMMENDATION_QUERY


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
        self.assertIn("位次 margin", result["answer"])
        self.assertIn("历史最低分/最低位次", result["answer"])

    def test_score_only_recommendation_requires_rank_and_does_not_execute_sql(self) -> None:
        result = _run(SCORE_ONLY_RECOMMENDATION_QUERY)

        assert_workbench_contract(self, result)
        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["result_sections"], {
            "reach": {"label": "冲", "items": []},
            "match": {"label": "稳", "items": []},
            "safety": {"label": "保", "items": []},
        })
        self.assertIn("score_without_rank", _warning_codes(result))
        self.assertNotIn("needs_confirmation", _warning_codes(result))
        execution = result["evidence_pack"]["execution_summary"]
        self.assertIsNone(execution["executor"])
        self.assertEqual(execution["sql"], "")
        self.assertEqual(execution["params"], [])
        self.assertNotIn("录取概率", result["answer"])
        score_preferences = [
            item
            for item in result["evidence_pack"]["extracted_preferences"]
            if item["id"] == "pref_score"
        ]
        self.assertEqual(score_preferences[0]["status"], "等待补充位次，未用于执行")

    def test_score_only_recommendation_returns_before_planner_readiness_sql(self) -> None:
        with patch.object(
            AdmissionsQueryPlanner,
            "_query_readiness",
            side_effect=AssertionError("score-only should not check table readiness"),
        ):
            with patch.object(
                AdmissionsQueryPlanner,
                "_available_years",
                side_effect=AssertionError("score-only should not resolve years"),
            ):
                result = _run(SCORE_ONLY_RECOMMENDATION_QUERY)

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["evidence_pack"]["execution_summary"]["sql"], "")

    def test_rank_only_recommendation_query_is_detected(self) -> None:
        result = _run(RANK_ONLY_RECOMMENDATION_QUERY)

        assert_workbench_contract(self, result)
        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(result["status"], "ok")
        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(execution["metric"], "rank_margin")
        self.assertEqual(execution["sort"], [{"field": "rank_margin", "direction": "ASC"}])
        self.assertNotIn("score_without_rank", _warning_codes(result))

    def test_decimal_rank_quantities_are_parsed_for_recommendations(self) -> None:
        examples = [
            "我今年位次3.2万，想读人工智能、计算机，想留在广东省，请推荐",
            "我今年排名3.2万，想读人工智能、计算机，想留在广东省，请推荐",
            "我今年省排3.2w，想读人工智能、计算机，想留在广东省，请推荐",
            "我今年位次3.2 万，想读人工智能、计算机，想留在广东省，请推荐",
            "我今年省排3.2 w，想读人工智能、计算机，想留在广东省，请推荐",
        ]
        for query in examples:
            with self.subTest(query=query):
                result = _run(query)

                self.assertEqual(result["query_type"], "recommendation")
                self.assertEqual(result["status"], "ok")
                execution = result["evidence_pack"]["execution_summary"]
                self.assertEqual(execution["metric"], "rank_margin")
                self.assertIn(32000, execution["params"])
                self.assertNotIn(3, execution["params"])

    def test_hard_filter_rank_quantity_accepts_spaced_unit(self) -> None:
        query = "我今年想读人工智能、计算机，想留在广东省，请推荐"
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=query,
                hard_filters={"user_rank": "3.2 万"},
                soft_preferences={"prompt": query},
                extractor="regex",
            )
        )

        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(result["status"], "ok")
        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(execution["metric"], "rank_margin")
        self.assertIn(32000, execution["params"])
        self.assertNotIn(3, execution["params"])

    def test_recommendation_evidence_records_calibration_policy(self) -> None:
        result = _run(RECOMMENDATION_QUERY)

        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(execution["major_match"]["mode"], "exact_major_keywords")
        self.assertEqual(execution["major_match"]["terms"], ["计算机", "人工智能"])
        self.assertEqual(
            set(execution["bucket_counts"]),
            {"reach", "match", "safety"},
        )
        self.assertIn("score_margin", execution["margin_policy"])
        self.assertIn("rank_margin", execution["margin_policy"])
        self.assertEqual(
            execution["year_weighting"]["mode"],
            "latest_available_year",
        )
        self.assertFalse(
            execution["year_weighting"]["executed_cross_year_weighting"]
        )

    def test_score_without_rank_adds_warning(self) -> None:
        result = _run(SCORE_ONLY_RECOMMENDATION_QUERY)

        self.assertIn("score_without_rank", _warning_codes(result))
        self.assertNotIn("needs_confirmation", _warning_codes(result))
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIsNone(result["evidence_pack"]["execution_summary"]["metric"])
        self.assertEqual(result["evidence_pack"]["execution_summary"]["sql"], "")

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
                user_input="我今年高考分数 630，位次 9000，想读人工智能，想留在广东省",
                hard_filters={
                    "user_score": 630,
                    "user_rank": 9000,
                    "major_keywords": ["软件工程"],
                    "preferred_school_provinces": ["广东"],
                },
                soft_preferences={
                    "prompt": "我今年高考分数 630，位次 9000，想读人工智能，想留在广东省"
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

    def test_confirmed_major_candidate_records_match_mode(self) -> None:
        query = "我今年高考分数 630，位次 9000，想读计算机相关，想留在广东省"
        first = _run(query)
        candidate_id = first["candidates_to_confirm"][0]["candidate_id"]

        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=query,
                soft_preferences={"prompt": query},
                extractor="regex",
                confirmed_candidates=[candidate_id],
            )
        )

        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(execution["major_match"]["mode"], "confirmed_candidates")
        self.assertIn("软件工程", execution["major_match"]["terms"])
        self.assertFalse(result["candidates_to_confirm"])

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
