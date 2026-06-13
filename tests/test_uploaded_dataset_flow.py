from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import yaml

from src.api.dataset_service import DatasetService, DatasetServiceError
from tests.workbench_contract_utils import assert_workbench_contract


GROUP_DETAIL_QUERY = (
    "列出 2025 年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数"
)
RECOMMENDATION_QUERY = (
    "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省"
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
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=RECOMMENDATION_QUERY,
                soft_preferences={"prompt": RECOMMENDATION_QUERY},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "recommendation")
        self.assertTrue(response["items"])
        self.assertEqual(set(response["result_sections"]), {"reach", "match", "safety"})
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


if __name__ == "__main__":
    unittest.main()
