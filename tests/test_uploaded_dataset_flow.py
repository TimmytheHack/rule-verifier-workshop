from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
import yaml

from src.api.dataset_service import DatasetService, DatasetServiceError
from src.api.workbench import WorkbenchConfig, run_workbench
from tests.semantic_test_utils import NEW_ADMISSIONS_ROWS, write_new_admissions_excel
from tests.workbench_contract_utils import assert_workbench_contract


GROUP_DETAIL_QUERY = (
    "列出 2025 年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数"
)
RECOMMENDATION_QUERY = (
    "我今年高考分数 630，位次 9000，想读人工智能、计算机，不想去国外，想留在广东省"
)


class UploadedDatasetFlowTest(unittest.TestCase):
    def test_upload_csv_generates_dataset_id(self) -> None:
        with TemporaryDirectory() as directory:
            source = _write_generic_csv(Path(directory))
            service = DatasetService(Path(directory) / "managed")

            result = service.upload(
                filename="housing.csv",
                content=source.read_bytes(),
            )

        self.assertTrue(result["dataset_id"].startswith("ds_"))
        self.assertEqual(result["status"], "uploaded")
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["column_count"], 4)
        self.assertEqual(len(result["source_fingerprint"]), 64)

    def test_upload_excel_generates_dataset_id(self) -> None:
        with TemporaryDirectory() as directory:
            source = _write_generic_excel(Path(directory))
            service = DatasetService(Path(directory) / "managed")

            result = service.upload(
                filename="housing.xlsx",
                content=source.read_bytes(),
            )

        self.assertTrue(result["dataset_id"].startswith("ds_"))
        self.assertEqual(result["sheet_name"], "Sheet1")
        self.assertEqual(result["status"], "uploaded")

    def test_draft_domain_query_is_blocked_before_sql(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_usd": 1900},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["domain_pack_status"], "needs_review")
        self.assertEqual(response["debug_trace"]["execution"]["sql"], "")

    def test_approve_then_build_warehouse_and_query(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            _approve_generic_dataset(service, dataset_id)
            built = service.build_warehouse(dataset_id)

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_usd": 1900},
            )

        self.assertEqual(built["status"], "queryable")
        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result_count"], 1)
        self.assertTrue(response["items"])

    def test_generic_domain_forbidden_soft_preference_does_not_leak(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            _approve_generic_dataset(service, dataset_id)
            service.build_warehouse(dataset_id)

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_usd": 1900},
                soft_preferences={"SQL": "SELECT * FROM leases"},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM leases", serialized)
        self.assertNotIn('"SQL"', serialized)
        self.assertIn(
            "[redacted_forbidden_payload]",
            response["query"]["soft_preferences"],
        )

    def test_generic_domain_forbidden_hard_filter_does_not_leak(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            _approve_generic_dataset(service, dataset_id)
            service.build_warehouse(dataset_id)

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={
                    "city": ["Austin"],
                    "rent_usd": 1900,
                    "SQL": "SELECT * FROM leases",
                    "note": "SELECT * FROM leases",
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM leases", serialized)
        self.assertNotIn('"SQL"', serialized)
        self.assertIn(
            "[redacted_forbidden_payload]",
            response["query"]["hard_filters"],
        )
        self.assertEqual(
            response["query"]["hard_filters"]["note"],
            "[redacted_forbidden_payload]",
        )

    def test_admissions_hard_filter_sql_text_does_not_leak(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                hard_filters={"major_keyword": "SELECT * FROM admissions"},
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                },
            )

        assert_workbench_contract(self, response)
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertEqual(
            response["hard_filters"]["major_keyword"],
            "[redacted_forbidden_payload]",
        )

    def test_admissions_hard_filter_scalar_select_does_not_leak(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                hard_filters={"major_keyword": "SELECT count(*)"},
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                },
            )

        assert_workbench_contract(self, response)
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT count(*)", serialized)
        self.assertEqual(
            response["hard_filters"]["major_keyword"],
            "[redacted_forbidden_payload]",
        )

    def test_generic_domain_structured_prompt_payload_does_not_leak(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            _approve_generic_dataset(service, dataset_id)
            service.build_warehouse(dataset_id)

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_usd": 1900},
                soft_preferences={
                    "prompt": {"SQL": "SELECT * FROM leases"},
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM leases", serialized)
        self.assertNotIn('"SQL"', serialized)
        self.assertEqual(
            response["query"]["soft_preferences"]["prompt"],
            "[redacted_forbidden_payload]",
        )

    def test_stale_fingerprint_blocks_uploaded_dataset_query(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            _approve_generic_dataset(service, dataset_id)
            service.build_warehouse(dataset_id)
            metadata = _dataset_metadata(service, dataset_id)
            Path(metadata["source_path"]).write_text(
                "listing_id,city,rent_usd,bedrooms\n9,Austin,1000,1\n",
                encoding="utf-8",
            )

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_usd": 1900},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "blocked")
        self.assertIn(
            "warehouse_fingerprint_mismatch",
            [warning["code"] for warning in response["warnings"]],
        )
        self.assertEqual(response["debug_trace"]["execution"]["sql"], "")

    def test_failed_rebuild_keeps_previous_queryable_warehouse(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            _approve_generic_dataset(service, dataset_id)
            service.build_warehouse(dataset_id)

            with patch(
                "src.api.dataset_service.build_structured_store_from_dataset",
                side_effect=RuntimeError("simulated build failure"),
            ):
                with self.assertRaises(RuntimeError):
                    service.build_warehouse(dataset_id)

            response = service.query(
                dataset_id,
                user_input="Austin under 1900",
                hard_filters={"city": ["Austin"], "rent_usd": 1900},
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result_count"], 1)

    def test_unsafe_dataset_id_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            service = DatasetService(Path(directory) / "managed")
            source = _write_generic_csv(Path(directory))

            with self.assertRaises(DatasetServiceError):
                service.upload(
                    filename="housing.csv",
                    content=source.read_bytes(),
                    dataset_id="../bad",
                )

    def test_profile_returns_field_facts_and_risk_flags(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))

            profile = service.profile(dataset_id)
            fields = {field["field_id"]: field for field in profile["fields"]}

        self.assertEqual(fields["rent_usd"]["inferred_type"], "number")
        self.assertEqual(fields["rent_usd"]["null_rate"], 0.0)
        self.assertEqual(fields["city"]["unique_count"], 2)
        self.assertIn("Austin", fields["city"]["sample_values"])

    def test_review_approve_and_block_records_audit_history(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _generated_generic_dataset(Path(directory))
            service.approve_op(dataset_id, "city", "in", reviewed_by="tester")
            service.block_field(dataset_id, "bedrooms", reviewed_by="tester")
            metadata = _dataset_metadata(service, dataset_id)
            review = yaml.safe_load(
                (Path(metadata["domain_dir"]) / "review.yaml").read_text(
                    encoding="utf-8"
                )
            )

        actions = [item["action"] for item in review["approval_history"]]
        self.assertIn("approve-op", actions)
        self.assertIn("block-field", actions)

    def test_uploaded_admissions_group_detail_report(self) -> None:
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=True,
            )

            response = service.query(
                dataset_id,
                user_input=GROUP_DETAIL_QUERY,
                soft_preferences={"prompt": GROUP_DETAIL_QUERY},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "group_detail_report")
        self.assertTrue(response["result_sections"]["groups"])
        self.assertIn("university_name", response["top_results"][0])

    def test_uploaded_admissions_recommendation(self) -> None:
        query = RECOMMENDATION_QUERY
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={"prompt": query},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "recommendation")
        self.assertTrue(response["items"])
        self.assertEqual(set(response["result_sections"]), {"reach", "match", "safety"})
        self.assertNotIn("score_without_rank", [w["code"] for w in response["warnings"]])


class UploadedSemanticAdmissionsFlowTest(unittest.TestCase):
    def test_semantic_probe_import_does_not_load_deepseek_modules(self) -> None:
        script = """
import json
import sys

import scripts.run_semantic_capability_probe

print(json.dumps({
    "llm_semantic_candidates": "src.semantic.llm_semantic_candidates" in sys.modules,
    "deepseek_extractor": "src.extractors.deepseek_extractor" in sys.modules,
}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        loaded = json.loads(completed.stdout)

        self.assertFalse(loaded["llm_semantic_candidates"])
        self.assertFalse(loaded["deepseek_extractor"])

    def test_dataset_service_import_does_not_load_deepseek_modules(self) -> None:
        script = """
import json
import sys

import src.api.dataset_service

print(json.dumps({
    "llm_semantic_candidates": "src.semantic.llm_semantic_candidates" in sys.modules,
    "deepseek_extractor": "src.extractors.deepseek_extractor" in sys.modules,
}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        loaded = json.loads(completed.stdout)

        self.assertFalse(loaded["llm_semantic_candidates"])
        self.assertFalse(loaded["deepseek_extractor"])

    def test_default_probe_run_does_not_load_deepseek_modules(self) -> None:
        script = """
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_semantic_capability_probe import run_probe

with TemporaryDirectory() as directory:
    try:
        run_probe(
            workbook_path=Path(directory) / "missing.xlsx",
            dataset_id="ds_missing_probe",
            query="probe",
            root=Path(directory) / "managed",
        )
    except FileNotFoundError:
        pass

print(json.dumps({
    "llm_semantic_candidates": "src.semantic.llm_semantic_candidates" in sys.modules,
    "deepseek_extractor": "src.extractors.deepseek_extractor" in sys.modules,
}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        loaded = json.loads(completed.stdout)

        self.assertFalse(loaded["llm_semantic_candidates"])
        self.assertFalse(loaded["deepseek_extractor"])

    def test_profile_exposes_candidate_only_semantic_mapping_records(self) -> None:
        with TemporaryDirectory() as directory:
            source = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_candidate_profile",
            )
            service.generate_domain_pack(
                "ds_candidate_profile",
                domain_name="admissions",
                base_domain="admissions",
            )

            profile = service.profile("ds_candidate_profile")

        self.assertIn("semantic_mapping_candidates", profile)
        candidates = profile["semantic_mapping_candidates"]["rule_based"]
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["status"], "candidate_only")

    def test_generic_recommendation_prompt_uses_legacy_planner(self) -> None:
        query = "我今年广东物理类位次 9000，请推荐冲稳保"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={"prompt": query},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["query_type"], "recommendation")

    def test_uploaded_new_admissions_major_rank_query(self) -> None:
        query = "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
        with TemporaryDirectory() as directory:
            source = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_new_admissions",
            )
            service.generate_domain_pack(
                "ds_new_admissions",
                domain_name="admissions",
                base_domain="admissions",
            )
            profile = service.profile("ds_new_admissions")
            self.assertIn("capability_graph", profile)
            self.assertIn("最低位次", profile["capability_graph"]["fields"])
            approved = service.approve_domain("ds_new_admissions")
            self.assertTrue(approved["ok"])
            built = service.build_warehouse("ds_new_admissions")
            self.assertEqual(built["status"], "queryable")

            response = service.query(
                "ds_new_admissions",
                user_input=query,
                soft_preferences={"prompt": query},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "admissions_major_rank")
        self.assertEqual(
            [item["raw"]["档位"] for item in response["items"]],
            ["冲", "稳", "保"],
        )
        self.assertEqual(response["items"][0]["raw"]["最低录取排名"], 9850)
        self.assertIn(
            "group_min_rank",
            [
                item["field_id"]
                for item in response["evidence_pack"]["unanswerable_intents"]
            ],
        )

    def test_uploaded_new_admissions_projects_available_context_fields(self) -> None:
        query = "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
        with TemporaryDirectory() as directory:
            source = _write_new_admissions_with_context(
                Path(directory) / "new_admissions_context.xlsx"
            )
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_new_admissions_context",
            )
            service.generate_domain_pack(
                "ds_new_admissions_context",
                domain_name="admissions",
                base_domain="admissions",
            )
            approved = service.approve_domain("ds_new_admissions_context")
            self.assertTrue(approved["ok"])
            built = service.build_warehouse("ds_new_admissions_context")
            self.assertEqual(built["status"], "queryable")

            response = service.query(
                "ds_new_admissions_context",
                user_input=query,
                soft_preferences={"prompt": query},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["query_type"], "admissions_major_rank")
        self.assertEqual(response["top_results"][0]["city"], "深圳")
        self.assertEqual(response["top_results"][0]["tuition"], 7660)
        self.assertEqual(response["top_results"][0]["group_min_rank"], 9900)
        unanswerable = [
            item["field_id"]
            for item in response["evidence_pack"]["unanswerable_intents"]
        ]
        self.assertNotIn("city", unanswerable)
        self.assertNotIn("tuition_yuan_per_year", unanswerable)
        self.assertNotIn("group_min_rank", unanswerable)
        self.assertNotIn("当前数据缺少这些已审核字段", response["answer"])

    def test_uploaded_admissions_semantic_recommendation_uses_verified_sql(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "recommendation")
        self.assertEqual(
            set(response["result_sections"]),
            {"reach", "match", "safety"},
        )
        self.assertEqual(
            response["debug_trace"]["execution"]["query_type"],
            "semantic_recommendation",
        )
        self.assertEqual(response["debug_trace"]["execution"]["year"], 2024)
        self.assertNotIn("sql", response["debug_trace"]["execution"])
        self.assertNotIn("sql", response["execution"])
        self.assertNotIn("sql", response["evidence_pack"]["execution_summary"])
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn('"sql":', serialized)
        self.assertNotIn("STRPOS", serialized)
        self.assertTrue(response["top_results"])
        self.assertIn(
            "school_country_or_region",
            [
                item["field_id"]
                for item in response["evidence_pack"]["unanswerable_intents"]
            ],
        )
        self.assertEqual(
            response["no_schema_field_preferences"][0]["field_id"],
            "school_country_or_region",
        )
        self.assertIn("不想去国外", response["answer"])

    def test_semantic_recommendation_with_ranking_plan_records_criterion_evidence(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": {
                        "criteria": [
                            {
                                "criterion_id": "major_rank_priority",
                                "source_text": "优先历史专业最低位次更靠前",
                                "required_field": "major_min_rank",
                                "operation": "numeric_lower_is_better",
                                "value": None,
                                "priority": 1,
                                "rationale": "专业最低位次字段可验证并支持通用排序。",
                            },
                        ]
                    },
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "recommendation")
        ranking = response["evidence_pack"]["ranking"]
        self.assertEqual(ranking["status"], "ranked")
        self.assertEqual(
            ranking["verified_ranking_plan"]["criteria"][0]["criterion_id"],
            "major_rank_priority",
        )
        self.assertTrue(ranking["criterion_evidence"])
        self.assertEqual(
            ranking["criterion_evidence"][0]["criteria"][0]["row_value"],
            response["top_results"][0]["major_min_rank"],
        )
        self.assertIn("criterion_evidence", response["answer"])

    def test_semantic_recommendation_without_ranking_plan_is_candidate_list(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                },
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(
            response["evidence_pack"]["ranking"]["status"],
            "candidate_list_only",
        )
        self.assertIn("候选列表", response["answer"])

    def test_unsafe_semantic_ranking_plan_is_rejected_and_redacted(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        unsafe_plan = {
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
            ]
        }
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": unsafe_plan,
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "error")
        self.assertEqual(
            response["query"]["soft_preferences"]["semantic_ranking_plan"],
            "[redacted_forbidden_payload]",
        )
        self.assertEqual(
            response["soft_preferences"]["semantic_ranking_plan"],
            "[redacted_forbidden_payload]",
        )
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)

    def test_unsafe_semantic_ranking_plan_uppercase_sql_is_rejected(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        unsafe_plan = {
            "criteria": [
                {
                    "criterion_id": "unsafe",
                    "source_text": "按 SQL 排序",
                    "required_field": "major_name",
                    "operation": "external_prestige_score",
                    "value": {"SQL": "SELECT * FROM admissions"},
                    "priority": 1,
                    "rationale": "不允许候选排序合同携带 SQL。",
                }
            ]
        }
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": unsafe_plan,
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "error")
        self.assertEqual(
            response["query"]["soft_preferences"]["semantic_ranking_plan"],
            "[redacted_forbidden_payload]",
        )
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)

    def test_unsafe_semantic_ranking_plan_sql_text_is_rejected(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        unsafe_plan = {
            "criteria": [
                {
                    "criterion_id": "unsafe",
                    "source_text": "SELECT * FROM admissions",
                    "required_field": "major_name",
                    "operation": "external_prestige_score",
                    "value": None,
                    "priority": 1,
                    "rationale": "不允许候选排序合同携带 SQL 命令文本。",
                }
            ]
        }
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": unsafe_plan,
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "error")
        self.assertEqual(
            response["query"]["soft_preferences"]["semantic_ranking_plan"],
            "[redacted_forbidden_payload]",
        )
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)

    def test_unsafe_semantic_ranking_plan_select_one_is_rejected(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        unsafe_plan = {
            "criteria": [
                {
                    "criterion_id": "unsafe",
                    "source_text": "SELECT 1",
                    "required_field": "major_name",
                    "operation": "external_prestige_score",
                    "value": None,
                    "priority": 1,
                    "rationale": "不允许候选排序合同携带 SQL 命令文本。",
                }
            ]
        }
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": unsafe_plan,
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "error")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT 1", serialized)

    def test_unsafe_semantic_ranking_plan_scalar_select_is_rejected(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        unsafe_plan = {
            "criteria": [
                {
                    "criterion_id": "unsafe",
                    "source_text": "SELECT count(*)",
                    "required_field": "major_name",
                    "operation": "external_prestige_score",
                    "value": None,
                    "priority": 1,
                    "rationale": "不允许候选排序合同携带 SQL 命令文本。",
                }
            ]
        }
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": unsafe_plan,
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "error")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT count(*)", serialized)

    def test_rejected_semantic_ranking_plan_does_not_leak_in_composed_text(
        self,
    ) -> None:
        unsafe_plan = {
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
            ]
        }
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )
            metadata = _dataset_metadata(service, dataset_id)

            response = run_workbench(
                WorkbenchConfig(
                    user_input="我的排位是15000，请给出推荐",
                    soft_preferences={
                        "semantic_intent": _semantic_recommendation_intent(),
                        "semantic_ranking_plan": unsafe_plan,
                    },
                    domain_name="admissions",
                    domain_path=str(metadata["domain_dir"]),
                    dataset_id=dataset_id,
                )
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "error")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertNotIn("SELECT", response["query"]["text"])
        self.assertNotIn("SELECT", response["user_input"])

    def test_top_level_forbidden_soft_preference_key_is_redacted(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "semantic_intent": _semantic_recommendation_intent(),
                    "SQL": "SELECT * FROM admissions",
                },
            )

        assert_workbench_contract(self, response)
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertNotIn("SQL", response["query"]["soft_preferences"])
        self.assertIn(
            "[redacted_forbidden_payload]",
            response["query"]["soft_preferences"],
        )

    def test_structured_prompt_payload_does_not_leak_in_semantic_flow(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": {"SQL": "SELECT * FROM admissions"},
                    "semantic_intent": _semantic_recommendation_intent(),
                },
            )

        assert_workbench_contract(self, response)
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertNotIn('"SQL"', serialized)
        self.assertEqual(
            response["query"]["soft_preferences"]["prompt"],
            "[redacted_forbidden_payload]",
        )

    def test_semantic_answer_receives_evidence_pack_only(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        captured: list[object] = []

        def answer_from_evidence_pack(evidence_pack: object) -> str:
            captured.append(evidence_pack)
            self.assertIsInstance(evidence_pack, dict)
            self.assertIn("top_k_results", evidence_pack)
            self.assertIn("execution_summary", evidence_pack)
            self.assertIn("ranking", evidence_pack)
            return "evidence-only answer"

        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench._semantic_answer",
                side_effect=answer_from_evidence_pack,
            ):
                response = service.query(
                    dataset_id,
                    user_input=query,
                    soft_preferences={
                        "prompt": query,
                        "semantic_intent": _semantic_recommendation_intent(),
                    },
                )

        assert_workbench_contract(self, response)
        self.assertEqual("evidence-only answer", response["answer"])
        self.assertTrue(captured)

    def test_external_knowledge_preference_is_not_ranked_without_reviewed_evidence(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，好就业，城市发展好，想留在广东省"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": {
                        "criteria": [
                            {
                                "criterion_id": "major_text_match",
                                "source_text": "想读人工智能，计算机",
                                "required_field": "major_name",
                                "operation": "text_match",
                                "value": ["人工智能", "计算机"],
                                "priority": 1,
                                "rationale": "专业字段可验证。",
                            },
                            {
                                "criterion_id": "employment",
                                "source_text": "好就业",
                                "required_field": "employment_outcome",
                                "operation": "numeric_higher_is_better",
                                "priority": 2,
                                "rationale": "需要就业字段。",
                            },
                        ]
                    },
                },
            )

        assert_workbench_contract(self, response)
        ranking = response["evidence_pack"]["ranking"]
        self.assertEqual(ranking["status"], "not_ranked_unverified_plan")
        self.assertEqual(ranking["criterion_evidence"], [])
        verified_criteria = ranking["verified_ranking_plan"]["criteria"]
        self.assertNotIn(
            "employment",
            [item["criterion_id"] for item in verified_criteria],
        )
        excluded_by_id = {
            item["criterion_id"]: item for item in ranking["excluded_criteria"]
        }
        self.assertEqual(excluded_by_id["employment"]["reason"], "missing_field")
        self.assertEqual(
            excluded_by_id["major_text_match"]["reason"],
            "unverified_value",
        )
        for unsupported_phrase in [
            "就业前景好",
            "好就业",
            "就业表现更好",
            "城市发展好",
            "学校氛围好",
        ]:
            self.assertNotIn(unsupported_phrase, response["answer"])

    def test_uploaded_admissions_semantic_score_only_requires_rank(self) -> None:
        query = "假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": {
                        **_semantic_recommendation_intent(),
                        "user_context": {
                            "user_score": 630,
                            "user_rank": None,
                            "source_province": "广东",
                            "subject_type": None,
                            "reselected_subjects": [],
                        },
                    },
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "needs_confirmation")
        self.assertEqual(response["query_type"], "recommendation")
        self.assertNotIn("sql", response["debug_trace"]["execution"])
        self.assertIn("score_without_rank", [w["code"] for w in response["warnings"]])


def _generated_generic_dataset(root: Path) -> tuple[DatasetService, str]:
    source = _write_generic_csv(root)
    service = DatasetService(root / "managed")
    service.upload(
        filename="housing.csv",
        content=source.read_bytes(),
        dataset_id="ds_generic",
    )
    service.generate_domain_pack("ds_generic")
    return service, "ds_generic"


def _approve_generic_dataset(service: DatasetService, dataset_id: str) -> None:
    service.approve_field(dataset_id, "listing_id")
    service.approve_op(dataset_id, "city", "in")
    service.approve_op(dataset_id, "rent_usd", "<=")
    approved = service.approve_domain(
        dataset_id,
        title_field="listing_id",
        primary_fields=["city", "rent_usd"],
        sort_field="rent_usd",
    )
    if not approved["ok"]:
        raise AssertionError(json.dumps(approved, ensure_ascii=False, indent=2))


def _queryable_uploaded_admissions(
    root: Path,
    *,
    use_excel: bool,
) -> tuple[DatasetService, str]:
    source = _write_admissions_fixture(root, use_excel=use_excel)
    dataset_id = "ds_admissions_excel" if use_excel else "ds_admissions_csv"
    service = DatasetService(root / "managed")
    service.upload(
        filename=source.name,
        content=source.read_bytes(),
        dataset_id=dataset_id,
    )
    service.generate_domain_pack(
        dataset_id,
        domain_name="admissions",
        base_domain="admissions",
    )
    approved = service.approve_domain(dataset_id)
    if not approved["ok"]:
        raise AssertionError(json.dumps(approved, ensure_ascii=False, indent=2))
    built = service.build_warehouse(dataset_id)
    if built["status"] != "queryable":
        raise AssertionError(json.dumps(built, ensure_ascii=False, indent=2))
    return service, dataset_id


def _dataset_metadata(service: DatasetService, dataset_id: str) -> dict[str, object]:
    path = Path(service.root) / dataset_id / "dataset.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _write_generic_csv(root: Path) -> Path:
    path = root / "housing.csv"
    pd.DataFrame(
        [
            {"listing_id": 1, "city": "Austin", "rent_usd": 1800, "bedrooms": 2},
            {"listing_id": 2, "city": "Dallas", "rent_usd": 1600, "bedrooms": 1},
            {"listing_id": 3, "city": "Austin", "rent_usd": 2100, "bedrooms": 3},
        ]
    ).to_csv(path, index=False)
    return path


def _write_generic_excel(root: Path) -> Path:
    path = root / "housing.xlsx"
    pd.DataFrame(
        [
            {"listing_id": 1, "city": "Austin", "rent_usd": 1800, "bedrooms": 2},
            {"listing_id": 2, "city": "Dallas", "rent_usd": 1600, "bedrooms": 1},
        ]
    ).to_excel(path, index=False)
    return path


def _write_new_admissions_with_context(path: Path) -> Path:
    rows = [dict(row) for row in NEW_ADMISSIONS_ROWS]
    context = [
        ("深圳", 7660, 9900),
        ("深圳", 6850, 10400),
        ("广州", 6850, 16000),
        ("成都", 68000, 9900),
    ]
    for row, (city, tuition, group_rank) in zip(rows, context, strict=True):
        row["城市"] = city
        row["学费"] = tuition
        row["专业组最低位次1"] = group_rank
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def _write_admissions_fixture(root: Path, *, use_excel: bool) -> Path:
    rows = _admissions_rows()
    path = root / ("uploaded_admissions.xlsx" if use_excel else "uploaded_admissions.csv")
    dataframe = pd.DataFrame(rows)
    if use_excel:
        dataframe.to_excel(path, index=False)
    else:
        dataframe.to_csv(path, index=False)
    return path


def _admissions_rows() -> list[dict[str, object]]:
    base = {
        "批次": "本科",
        "科类": "物理",
        "选科要求": "化学",
        "学费": 6850,
        "生源地": "广东",
        "院校标签": "省内",
    }
    return [
        {
            **base,
            "ID": 1,
            "年份": 2024,
            "院校代码": "10590",
            "院校名称": "深圳大学",
            "院校专业组代码": "10590221",
            "专业组名称": "物理221组",
            "专业代码": "080901",
            "专业名称": "计算机科学与技术",
            "专业全称": "计算机科学与技术",
            "所在省": "广东",
            "城市": "深圳",
            "专业组最低位次1": 9000,
            "最低位次1": 8800,
            "专业组最低分1": 628,
            "最低分1": 626,
            "最高分1": 640,
            "计划人数": 30,
            "专业组计划人数": 100,
            "院校排名": 80,
        },
        {
            **base,
            "ID": 2,
            "年份": 2024,
            "院校代码": "10590",
            "院校名称": "深圳大学",
            "院校专业组代码": "10590221",
            "专业组名称": "物理221组",
            "专业代码": "080717",
            "专业名称": "人工智能",
            "专业全称": "人工智能",
            "所在省": "广东",
            "城市": "深圳",
            "专业组最低位次1": 9000,
            "最低位次1": 9100,
            "专业组最低分1": 628,
            "最低分1": 625,
            "最高分1": 638,
            "计划人数": 20,
            "专业组计划人数": 100,
            "院校排名": 80,
        },
        {
            **base,
            "ID": 3,
            "年份": 2024,
            "院校代码": "10558",
            "院校名称": "中山大学",
            "院校专业组代码": "10558219",
            "专业组名称": "物理219组",
            "专业代码": "080901",
            "专业名称": "计算机类",
            "专业全称": "计算机类",
            "所在省": "广东",
            "城市": "广州",
            "专业组最低位次1": 5000,
            "最低位次1": 5000,
            "专业组最低分1": 650,
            "最低分1": 650,
            "最高分1": 670,
            "计划人数": 40,
            "专业组计划人数": 120,
            "院校排名": 10,
        },
        {
            **base,
            "ID": 4,
            "年份": 2024,
            "院校代码": "11845",
            "院校名称": "广东工业大学",
            "院校专业组代码": "11845101",
            "专业组名称": "物理101组",
            "专业代码": "080717",
            "专业名称": "人工智能",
            "专业全称": "人工智能",
            "所在省": "广东",
            "城市": "广州",
            "专业组最低位次1": 30000,
            "最低位次1": 30000,
            "专业组最低分1": 595,
            "最低分1": 595,
            "最高分1": 610,
            "计划人数": 60,
            "专业组计划人数": 200,
            "院校排名": 120,
        },
    ]


def _semantic_recommendation_intent() -> dict[str, object]:
    return {
        "query_type": "semantic_recommendation",
        "user_context": {
            "user_rank": 15000,
            "user_score": None,
            "source_province": "广东",
            "subject_type": None,
            "reselected_subjects": [],
        },
        "preferences": [
            {
                "source_text": "想读人工智能，计算机",
                "semantic": "major_name",
                "op": "contains_any",
                "value": ["人工智能", "计算机"],
                "confidence": 1.0,
                "reason": None,
            },
            {
                "source_text": "想留在广东省",
                "semantic": "school_province",
                "op": "in",
                "value": ["广东"],
                "confidence": 1.0,
                "reason": None,
            },
            {
                "source_text": "不想去国外",
                "semantic": "school_country_or_region",
                "op": "not_in",
                "value": ["国外", "境外", "海外"],
                "confidence": 1.0,
                "reason": None,
            },
        ],
        "requested_output": ["recommendation_sections", "minimum_rank"],
        "source_language": "zh-CN",
    }


if __name__ == "__main__":
    unittest.main()
