from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.generate_domain_pack import load_source_dataset
from scripts.run_mvp_demo import REQUIRED_COLUMNS, SCHEMA_PATH, WORKBOOK_NAME
from src.adapters.data_warehouse import (
    build_structured_store,
    build_structured_store_from_dataset,
)
from src.api.workbench import WorkbenchConfig, run_workbench
from src.domains import DomainConfig


_WAREHOUSE_DIRECTORY = TemporaryDirectory()
_WAREHOUSE_PATHS: tuple[Path, Path, Path] | None = None
_DOMAIN_WAREHOUSE_PATHS: dict[str, tuple[Path, Path]] = {}


def run_workbench_with_test_warehouse(config: WorkbenchConfig) -> dict[str, object]:
    if config.domain_name != "admissions" or config.domain_path:
        return run_workbench_with_domain_warehouse(config)
    workbook_path, database_path, index_path = _test_warehouse_paths()
    with patch("src.api.workbench.WORKBOOK_NAME", workbook_path):
        with patch("src.api.workbench.WAREHOUSE_DATABASE_PATH", database_path):
            with patch("src.api.workbench.WAREHOUSE_VALUE_INDEX_PATH", index_path):
                return run_workbench(config)


def run_workbench_with_domain_warehouse(
    config: WorkbenchConfig,
) -> dict[str, object]:
    domain = (
        DomainConfig.from_path(config.domain_path, config.domain_name)
        if config.domain_path
        else DomainConfig.load(config.domain_name)
    )
    if domain.pack_status != "approved":
        return run_workbench(config)
    database_path, index_path = _domain_warehouse_paths(domain)

    def database_for_domain(domain_config: DomainConfig) -> Path:
        if domain_config.domain_id == domain.domain_id:
            return database_path
        return domain_config.warehouse_database_path

    def index_for_domain(domain_config: DomainConfig) -> Path:
        if domain_config.domain_id == domain.domain_id:
            return index_path
        return domain_config.value_index_path

    with patch("src.api.workbench._warehouse_database_path", database_for_domain):
        with patch("src.api.workbench._warehouse_value_index_path", index_for_domain):
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


def _domain_warehouse_paths(domain: DomainConfig) -> tuple[Path, Path]:
    cached = _DOMAIN_WAREHOUSE_PATHS.get(domain.domain_id)
    if cached:
        return cached
    root = Path(_WAREHOUSE_DIRECTORY.name)
    database_path = root / f"{domain.domain_id}.duckdb"
    index_path = root / f"{domain.domain_id}_schema_value_index.json"
    dataset = load_source_dataset(domain.workbook_path)
    build_structured_store_from_dataset(
        dataset=dataset,
        schema_path=domain.schema_path,
        database_path=database_path,
        index_path=index_path,
        table_name=domain.table_name,
        source_path=domain.workbook_path,
    )
    _DOMAIN_WAREHOUSE_PATHS[domain.domain_id] = (database_path, index_path)
    return database_path, index_path
