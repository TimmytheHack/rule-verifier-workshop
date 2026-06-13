from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.adapters.data_warehouse import (
    build_structured_store,
    load_structured_dataset,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/schema_registry.json"
REQUIRED_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]


class DataWarehouseTest(unittest.TestCase):
    def test_builds_duckdb_store_and_schema_value_index(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "sample.xlsx"
            database_path = root / "sample.duckdb"
            index_path = root / "schema_value_index.json"
            dataframe = pd.DataFrame(
                [
                    {
                        "生源地": "广东",
                        "科类": "物理",
                        "专业名称": "计算机科学与技术",
                        "城市": "广州",
                        "专业组最低位次1": 32000,
                        "学费": "6850元/年",
                    },
                    {
                        "生源地": "广东",
                        "科类": "物理",
                        "专业名称": "软件工程",
                        "城市": "深圳",
                        "专业组最低位次1": 35000,
                        "学费": "8000元/年",
                    },
                ]
            )
            dataframe.to_excel(workbook_path, index=False)

            result = build_structured_store(
                workbook_path=workbook_path,
                required_columns=REQUIRED_COLUMNS,
                schema_path=SCHEMA_PATH,
                database_path=database_path,
                index_path=index_path,
            )
            loaded = load_structured_dataset(database_path, REQUIRED_COLUMNS)
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))

        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.column_count, 6)
        self.assertEqual(len(loaded.dataframe), 2)
        self.assertIn("major_name", index_payload["fields"])
        self.assertTrue(index_payload["fields"]["major_name"]["active"])
        self.assertEqual(
            index_payload["fields"]["tuition_yuan_per_year"]["numeric"],
            {"min": 6850, "max": 8000},
        )


if __name__ == "__main__":
    unittest.main()
