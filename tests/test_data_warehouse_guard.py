from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from scripts.run_mvp_demo import REQUIRED_COLUMNS
from src.adapters.data_warehouse import (
    audit_data_warehouse_fingerprints,
    build_structured_store,
)
from src.api.workbench import WorkbenchConfig, run_workbench
from src.domains import DomainConfig


ROOT = Path(__file__).resolve().parents[1]
ADMISSIONS_DOMAIN = DomainConfig.load("admissions")
SCHEMA_PATH = ADMISSIONS_DOMAIN.schema_path


def _sample_dataframe(city: str = "广州") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "生源地": "广东",
                "科类": "物理",
                "选科要求": "化学",
                "专业名称": "计算机科学与技术",
                "城市": city,
                "专业组最低位次1": 32000,
                "学费": "6850元/年",
                "院校名称": "样本大学",
                "院校专业组代码": "123401",
                "专业代码": "080901",
                "专业全称": "计算机科学与技术",
                "最低位次1": 33000,
            }
        ]
    )


def _build_store(root: Path) -> tuple[Path, Path, Path]:
    workbook_path = root / "sample.xlsx"
    database_path = root / "sample.duckdb"
    index_path = root / "schema_value_index.json"
    _sample_dataframe().to_excel(workbook_path, index=False)
    build_structured_store(
        workbook_path=workbook_path,
        required_columns=REQUIRED_COLUMNS,
        schema_path=SCHEMA_PATH,
        database_path=database_path,
        index_path=index_path,
    )
    return workbook_path, database_path, index_path


def _warning_codes(payload: dict[str, object]) -> set[str]:
    data_warehouse = payload["data_warehouse"]
    assert isinstance(data_warehouse, dict)
    warnings = data_warehouse["warnings"]
    assert isinstance(warnings, list)
    return {str(warning["code"]) for warning in warnings}


def _run_with_paths(
    workbook_path: Path,
    database_path: Path,
    index_path: Path,
) -> dict[str, object]:
    with patch("src.api.workbench.WORKBOOK_NAME", workbook_path):
        with patch("src.api.workbench.WAREHOUSE_DATABASE_PATH", database_path):
            with patch("src.api.workbench.WAREHOUSE_VALUE_INDEX_PATH", index_path):
                return run_workbench(
                    WorkbenchConfig(
                        user_input="广东物理，排位32000，想学计算机，广州。",
                        extractor="regex",
                    )
                )


class DataWarehouseGuardTest(unittest.TestCase):
    def test_matched_fingerprint_allows_workbench_execution(self) -> None:
        with TemporaryDirectory() as directory:
            workbook_path, database_path, index_path = _build_store(Path(directory))
            audit = audit_data_warehouse_fingerprints(
                workbook_path=workbook_path,
                database_path=database_path,
                index_path=index_path,
            )
            result = _run_with_paths(workbook_path, database_path, index_path)

        self.assertEqual(audit["status"], "ok")
        self.assertTrue(audit["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data_warehouse"]["status"], "ok")
        self.assertEqual(result["execution"]["executor"], "duckdb")
        self.assertGreaterEqual(result["result_count"], 1)

    def test_missing_warehouse_returns_structured_warning(self) -> None:
        with TemporaryDirectory() as directory:
            workbook_path, database_path, index_path = _build_store(Path(directory))
            database_path.unlink()
            result = _run_with_paths(workbook_path, database_path, index_path)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["warning_type"], "data_warehouse_fingerprint_guard")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["execution"]["executor"], None)
        self.assertIn("missing_warehouse", _warning_codes(result))
        self.assertIn("数据仓库 fingerprint guard 未通过", result["natural_language_report"]["full_text"])

    def test_stale_warehouse_returns_structured_warning(self) -> None:
        with TemporaryDirectory() as directory:
            workbook_path, database_path, index_path = _build_store(Path(directory))
            _sample_dataframe(city="深圳").to_excel(workbook_path, index=False)
            result = _run_with_paths(workbook_path, database_path, index_path)

        codes = _warning_codes(result)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("warehouse_fingerprint_mismatch", codes)
        self.assertIn("value_index_fingerprint_mismatch", codes)
        self.assertEqual(result["top_results"], [])

    def test_missing_value_index_returns_structured_warning(self) -> None:
        with TemporaryDirectory() as directory:
            workbook_path, database_path, index_path = _build_store(Path(directory))
            index_path.unlink()
            result = _run_with_paths(workbook_path, database_path, index_path)

        self.assertEqual(result["status"], "blocked")
        self.assertIn("missing_value_index", _warning_codes(result))
        self.assertEqual(result["execution"]["sql"], "")


if __name__ == "__main__":
    unittest.main()
