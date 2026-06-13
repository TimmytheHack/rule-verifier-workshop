from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.run_mvp_demo import REQUIRED_COLUMNS, SCHEMA_PATH, WORKBOOK_NAME
from src.adapters.data_warehouse import build_structured_store
from src.api.workbench import WorkbenchConfig, run_workbench


_WAREHOUSE_DIRECTORY = TemporaryDirectory()
_WAREHOUSE_PATHS: tuple[Path, Path, Path] | None = None


def run_workbench_with_test_warehouse(config: WorkbenchConfig) -> dict[str, object]:
    workbook_path, database_path, index_path = _test_warehouse_paths()
    with patch("src.api.workbench.WORKBOOK_NAME", workbook_path):
        with patch("src.api.workbench.WAREHOUSE_DATABASE_PATH", database_path):
            with patch("src.api.workbench.WAREHOUSE_VALUE_INDEX_PATH", index_path):
                return run_workbench(config)


def _test_warehouse_paths() -> tuple[Path, Path, Path]:
    global _WAREHOUSE_PATHS
    if _WAREHOUSE_PATHS is None:
        root = Path(_WAREHOUSE_DIRECTORY.name)
        database_path = root / "guangdong_admissions.duckdb"
        index_path = root / "schema_value_index.json"
        build_structured_store(
            workbook_path=WORKBOOK_NAME,
            required_columns=REQUIRED_COLUMNS,
            schema_path=SCHEMA_PATH,
            database_path=database_path,
            index_path=index_path,
        )
        _WAREHOUSE_PATHS = (Path(WORKBOOK_NAME), database_path, index_path)
    return _WAREHOUSE_PATHS
