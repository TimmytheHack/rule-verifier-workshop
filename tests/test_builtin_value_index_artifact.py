from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILTIN_VALUE_INDEX_PATH = ROOT / "outputs/data/schema_value_index.json"
INGESTION_SUMMARY_PATH = ROOT / "outputs/data/ingestion_summary.json"
EXPECTED_WORKBOOK_PATH = "广东省2025年志愿填报大数据（24-25）0523.xlsx"
EXPECTED_DATABASE_PATH = "outputs/data/guangdong_admissions.duckdb"
EXPECTED_VALUE_INDEX_PATH = "outputs/data/schema_value_index.json"
REQUIRED_ACTIVE_FIELDS = ("university_name", "city", "major_name", "group_code")
REQUIRED_LOOKUP_VALUES = {
    "university_name": "深圳大学",
    "city": "深圳",
    "major_name": None,
}


class BuiltinValueIndexArtifactTest(unittest.TestCase):
    def test_builtin_value_index_contains_required_active_lookup_fields(self) -> None:
        payload = json.loads(BUILTIN_VALUE_INDEX_PATH.read_text(encoding="utf-8"))
        fields = payload.get("fields")
        self.assertIsInstance(fields, dict)

        for field_id in REQUIRED_ACTIVE_FIELDS:
            with self.subTest(field_id=field_id):
                field = fields.get(field_id)
                self.assertIsInstance(field, dict)
                self.assertTrue(field.get("active"))

        for field_id, required_value in REQUIRED_LOOKUP_VALUES.items():
            with self.subTest(field_id=field_id):
                field = fields.get(field_id)
                self.assertIsInstance(field, dict)
                lookup_values = field.get("lookup_values")
                self.assertTrue(lookup_values)
                if required_value is not None:
                    self.assertIn(required_value, lookup_values)

        group_code = fields.get("group_code")
        self.assertIsInstance(group_code, dict)
        self.assertFalse(group_code.get("lookup_complete"))

    def test_builtin_data_artifacts_use_stable_paths(self) -> None:
        value_index = json.loads(BUILTIN_VALUE_INDEX_PATH.read_text(encoding="utf-8"))
        ingestion_summary = json.loads(
            INGESTION_SUMMARY_PATH.read_text(encoding="utf-8")
        )
        value_index_source = value_index.get("source")
        value_index_warehouse = value_index.get("warehouse")
        self.assertIsInstance(value_index_source, dict)
        self.assertIsInstance(value_index_warehouse, dict)
        self.assertIsInstance(ingestion_summary, dict)

        checked_paths = [
            (
                "schema_value_index.source.source_path",
                value_index_source.get("source_path"),
                EXPECTED_WORKBOOK_PATH,
            ),
            (
                "schema_value_index.source.workbook_path",
                value_index_source.get("workbook_path"),
                EXPECTED_WORKBOOK_PATH,
            ),
            (
                "schema_value_index.warehouse.database_path",
                value_index_warehouse.get("database_path"),
                EXPECTED_DATABASE_PATH,
            ),
            (
                "ingestion_summary.source_path",
                ingestion_summary.get("source_path"),
                EXPECTED_WORKBOOK_PATH,
            ),
            (
                "ingestion_summary.database_path",
                ingestion_summary.get("database_path"),
                EXPECTED_DATABASE_PATH,
            ),
            (
                "ingestion_summary.index_path",
                ingestion_summary.get("index_path"),
                EXPECTED_VALUE_INDEX_PATH,
            ),
        ]

        for key, path, expected in checked_paths:
            with self.subTest(key=key):
                self.assertIsInstance(path, str)
                self.assertEqual(path, expected)
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn(".worktrees", path)

        artifact_text = (
            BUILTIN_VALUE_INDEX_PATH.read_text(encoding="utf-8")
            + INGESTION_SUMMARY_PATH.read_text(encoding="utf-8")
        )
        self.assertNotIn("/Users/", artifact_text)
        self.assertNotIn(".worktrees", artifact_text)


if __name__ == "__main__":
    unittest.main()
