from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.adapters.data_warehouse import (
    SchemaValueIndex,
    build_structured_store,
    load_structured_dataset,
)
from src.domains import DomainConfig
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[1]
ADMISSIONS_DOMAIN = DomainConfig.load("admissions")
SCHEMA_PATH = ADMISSIONS_DOMAIN.schema_path
REQUIRED_COLUMNS = ADMISSIONS_DOMAIN.required_columns


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
                        "选科要求": "不限",
                        "专业名称": "计算机科学与技术",
                        "城市": "广州",
                        "专业组最低位次1": 32000,
                        "学费": "6850元/年",
                    },
                    {
                        "生源地": "广东",
                        "科类": "物理",
                        "选科要求": "不限",
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
            value_index = SchemaValueIndex.from_file(index_path)
            registry = SchemaRegistry.from_file(SCHEMA_PATH, loaded.headers)
            grounding = AttributeGrounder(
                registry,
                value_index=value_index,
                domain_config=ADMISSIONS_DOMAIN,
            ).ground(
                {
                    "user_context": {},
                    "preferences": {
                        "major_exact_terms": ["计算机"],
                        "preferred_cities": ["广州", "深圳"],
                    },
                }
            )
            major_audit = value_index.audit_value("major_name", "计算机")
            city_audit = value_index.audit_value("city", ["广州", "深圳"])
            missing_city_audit = value_index.audit_value("city", "珠海")

        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.column_count, 7)
        summary = result.to_dict()
        self.assertEqual(summary["source_path"], str(workbook_path))
        self.assertEqual(summary["fingerprint"], result.source_fingerprint)
        self.assertEqual(summary["row_count"], 2)
        self.assertEqual(summary["column_count"], 7)
        self.assertIn("major_name", summary["field_profiles"])
        self.assertIsInstance(summary["created_at"], str)
        self.assertEqual(len(loaded.dataframe), 2)
        self.assertIn("major_name", index_payload["fields"])
        self.assertTrue(index_payload["fields"]["major_name"]["active"])
        self.assertTrue(index_payload["fields"]["major_name"]["lookup_complete"])
        self.assertIn("计算机科学与技术", index_payload["fields"]["major_name"]["lookup_values"])
        self.assertEqual(major_audit["status"], "matched")
        self.assertEqual(major_audit["checks"][0]["status"], "contains_match")
        self.assertEqual(city_audit["status"], "matched")
        self.assertEqual(missing_city_audit["status"], "not_found")
        self.assertEqual(
            grounding["summary"]["value_index_status_counts"],
            {"matched": 2},
        )
        self.assertEqual(
            index_payload["fields"]["tuition_yuan_per_year"]["numeric"],
            {"min": 6850, "max": 8000},
        )


if __name__ == "__main__":
    unittest.main()
