from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.generate_domain_pack import (
    _safe_llm_profile,
    approve_domain_pack,
    generate_domain_pack,
)
from src.domains import DomainConfig
from src.executors.duckdb_executor import DuckDBExecutor
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[1]
HOUSING_FIXTURE = ROOT / "domains/housing/fixtures/housing.csv"
PRODUCTS_FIXTURE = ROOT / "domains/products/fixtures/products.csv"


class GenerateDomainPackTest(unittest.TestCase):
    def test_csv_input_generates_required_draft_files_and_warehouse(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="housing_draft",
                output_root=directory,
            )
            domain_dir = result.domain_dir

            for filename in [
                "domain.yaml",
                "schema_mapping.yaml",
                "rule_taxonomy.seed.yaml",
                "extraction_aliases.seed.json",
                "top_result_mapping.yaml",
                "sort_policy.seed.yaml",
                "answer_templates.seed.md",
                "golden_cases.seed.yaml",
                "housing_draft.duckdb",
                "schema_profile.json",
                "schema_value_index.json",
                "ingestion_summary.json",
            ]:
                self.assertTrue((domain_dir / filename).exists(), filename)

            domain = DomainConfig.from_path(domain_dir)
            profile = json.loads((domain_dir / "schema_profile.json").read_text(encoding="utf-8"))
            summary = json.loads((domain_dir / "ingestion_summary.json").read_text(encoding="utf-8"))
            schema = json.loads((domain_dir / "schema_registry.json").read_text(encoding="utf-8"))
            taxonomy = json.loads((domain_dir / "rule_taxonomy.json").read_text(encoding="utf-8"))

        self.assertEqual(domain.domain_id, "housing_draft")
        self.assertEqual(profile["status"], "draft")
        self.assertEqual(schema["status"], "draft")
        self.assertTrue(
            all(field["status"] == "needs_review" for field in schema["fields"].values())
        )
        self.assertTrue(
            all(field["allowed_ops"] == [] for field in schema["fields"].values())
        )
        self.assertEqual(taxonomy["deterministic_rules"], [])
        self.assertEqual(profile["row_count"], 20)
        self.assertEqual(summary["row_count"], 20)
        self.assertEqual(summary["table_name"], "housing_draft")

    def test_excel_input_generates_profile_and_runtime_domain_config(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "products.xlsx"
            pd.DataFrame(
                [
                    {
                        "product_id": 1,
                        "category": "book",
                        "price_usd": 12.5,
                        "description": "Introductory textbook with exercises.",
                    },
                    {
                        "product_id": 2,
                        "category": "book",
                        "price_usd": 18.0,
                        "description": "Advanced textbook with long-form notes.",
                    },
                    {
                        "product_id": 3,
                        "category": "tool",
                        "price_usd": 35.0,
                        "description": "Reusable classroom tool kit.",
                    },
                ]
            ).to_excel(workbook, index=False)

            result = generate_domain_pack(
                source_path=workbook,
                domain_name="excel_products",
                output_root=root,
            )
            domain = DomainConfig.from_path(result.domain_dir)
            profile = json.loads(result.schema_profile_path.read_text(encoding="utf-8"))
            database_exists = result.database_path.exists()

        self.assertEqual(domain.table_name, "excel_products")
        self.assertEqual(profile["column_count"], 4)
        self.assertTrue(database_exists)

    def test_infers_numeric_categorical_and_text_fields(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "fixture.csv"
            pd.DataFrame(
                {
                    "price_usd": [10, 20, 30, 40, 50, 60],
                    "category": ["a", "a", "b", "b", "c", "c"],
                    "description": [
                        "Long description for item one with enough words to read as text.",
                        "Long description for item two with enough words to read as text.",
                        "Long description for item three with enough words to read as text.",
                        "Long description for item four with enough words to read as text.",
                        "Long description for item five with enough words to read as text.",
                        "Long description for item six with enough words to read as text.",
                    ],
                }
            ).to_csv(csv_path, index=False)

            result = generate_domain_pack(csv_path, "typed_fixture", output_root=root)
            profile = json.loads(result.schema_profile_path.read_text(encoding="utf-8"))
            by_field = {column["field_id"]: column for column in profile["columns"]}

        self.assertEqual(by_field["price_usd"]["inferred_type"], "number")
        self.assertEqual(by_field["price_usd"]["numeric"], {"min": 10, "max": 60})
        self.assertEqual(by_field["category"]["inferred_type"], "enum")
        self.assertEqual(by_field["description"]["inferred_type"], "long_text")

    def test_pii_and_high_cardinality_fields_are_not_auto_filters(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=PRODUCTS_FIXTURE,
                domain_name="products_draft",
                output_root=directory,
            )
            schema = json.loads(result.schema_path.read_text(encoding="utf-8"))
            fields = schema["fields"]

        self.assertEqual(fields["email_contact"]["filter_policy"], "blocked_by_default")
        self.assertEqual(fields["email_contact"]["allowed_ops"], [])
        self.assertEqual(fields["email_contact"]["candidate_allowed_ops"], [])
        self.assertEqual(fields["product_name"]["filter_policy"], "blocked_by_default")
        self.assertEqual(fields["product_name"]["allowed_ops"], [])
        self.assertEqual(fields["product_name"]["candidate_allowed_ops"], [])

    def test_llm_profile_uses_only_sanitized_schema_samples(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=PRODUCTS_FIXTURE,
                domain_name="products_llm_safe",
                output_root=directory,
            )
            profile = json.loads(result.schema_profile_path.read_text(encoding="utf-8"))

        safe_profile = _safe_llm_profile(profile)
        serialized = json.dumps(safe_profile, ensure_ascii=False)
        by_field = {column["field_id"]: column for column in safe_profile["columns"]}

        self.assertNotIn("seller1@example.com", serialized)
        self.assertEqual(by_field["email_contact"]["sample_values"], [])
        self.assertLessEqual(len(by_field["product_name"]["sample_values"]), 3)

    def test_draft_config_does_not_execute_until_reviewed(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="housing_draft",
                output_root=directory,
            )
            domain = DomainConfig.from_path(result.domain_dir)
            dataframe = pd.read_csv(HOUSING_FIXTURE)
            registry = SchemaRegistry.from_domain(domain, list(dataframe.columns))
            verifier = RuleVerifier(registry, domain_config=domain)

            draft_rule = verifier.attach_verification(
                {
                    "rule_id": "r_city",
                    "category": "deterministic",
                    "field_id": "city",
                    "field": "city",
                    "operator": "eq",
                    "value": "Austin",
                }
            )

            approved_domain = approve_domain_pack(
                result.domain_dir,
                approved_field_ids=["listing_id", "city", "bedrooms", "rent_usd"],
                output_field_ids=["listing_id", "city", "bedrooms", "rent_usd"],
                sort_field_id="rent_usd",
            )
            approved_registry = SchemaRegistry.from_domain(
                approved_domain,
                list(dataframe.columns),
            )
            approved_verifier = RuleVerifier(
                approved_registry,
                domain_config=approved_domain,
            )
            executable_rules = [
                approved_verifier.attach_verification(rule)
                for rule in [
                    {
                        "rule_id": "r_city",
                        "category": "deterministic",
                        "field_id": "city",
                        "field": "city",
                        "operator": "eq",
                        "value": "Austin",
                    },
                    {
                        "rule_id": "r_bedrooms",
                        "category": "deterministic",
                        "field_id": "bedrooms",
                        "field": "bedrooms",
                        "operator": ">=",
                        "value": 2,
                    },
                    {
                        "rule_id": "r_rent",
                        "category": "deterministic",
                        "field_id": "rent_usd",
                        "field": "rent_usd",
                        "operator": "<=",
                        "value": 1900,
                    },
                ]
            ]
            execution = DuckDBExecutor(
                approved_domain.warehouse_database_path,
                table_name=approved_domain.table_name,
                domain_config=approved_domain,
            ).execute(executable_rules, top_k=5)

        self.assertFalse(draft_rule["verification"]["executable"])
        self.assertEqual(
            draft_rule["verification"]["terminal_status"],
            "rejected_invalid_operator",
        )
        self.assertTrue(all(rule["verification"]["executable"] for rule in executable_rules))
        self.assertEqual([row["listing_id"] for row in execution.rows], [14, 9, 2])

    def test_toy_housing_and_products_can_smoke_query_after_approval(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            housing = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="toy_housing",
                output_root=root,
            )
            housing_domain = approve_domain_pack(
                housing.domain_dir,
                approved_field_ids=["listing_id", "city", "rent_usd"],
                output_field_ids=["listing_id", "city", "rent_usd"],
                sort_field_id="rent_usd",
            )
            housing_rows = _execute_smoke_query(
                domain=housing_domain,
                source_columns=list(pd.read_csv(HOUSING_FIXTURE).columns),
                rules=[
                    {
                        "rule_id": "h_city",
                        "category": "deterministic",
                        "field_id": "city",
                        "field": "city",
                        "operator": "eq",
                        "value": "Dallas",
                    },
                    {
                        "rule_id": "h_rent",
                        "category": "deterministic",
                        "field_id": "rent_usd",
                        "field": "rent_usd",
                        "operator": "<=",
                        "value": 1600,
                    },
                ],
            )

            products = generate_domain_pack(
                source_path=PRODUCTS_FIXTURE,
                domain_name="toy_products",
                output_root=root,
            )
            products_domain = approve_domain_pack(
                products.domain_dir,
                approved_field_ids=[
                    "product_id",
                    "product_name",
                    "category",
                    "price_usd",
                    "rating",
                ],
                output_field_ids=[
                    "product_id",
                    "product_name",
                    "category",
                    "price_usd",
                    "rating",
                ],
                sort_field_id="price_usd",
            )
            product_rows = _execute_smoke_query(
                domain=products_domain,
                source_columns=list(pd.read_csv(PRODUCTS_FIXTURE).columns),
                rules=[
                    {
                        "rule_id": "p_category",
                        "category": "deterministic",
                        "field_id": "category",
                        "field": "category",
                        "operator": "eq",
                        "value": "audio",
                    },
                    {
                        "rule_id": "p_price",
                        "category": "deterministic",
                        "field_id": "price_usd",
                        "field": "price_usd",
                        "operator": "<=",
                        "value": 100,
                    },
                ],
            )

        self.assertEqual([row["listing_id"] for row in housing_rows], [11.0, 4.0])
        self.assertEqual(product_rows[0]["product_name"], "Speaker Mini")
        self.assertEqual(product_rows[0]["price_usd"], 49)


def _execute_smoke_query(
    domain: DomainConfig,
    source_columns: list[str],
    rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    registry = SchemaRegistry.from_domain(domain, source_columns)
    verifier = RuleVerifier(registry, domain_config=domain)
    executable_rules = [verifier.attach_verification(rule) for rule in rules]
    if not all(rule["verification"]["executable"] for rule in executable_rules):
        raise AssertionError(executable_rules)
    return DuckDBExecutor(
        domain.warehouse_database_path,
        table_name=domain.table_name,
        domain_config=domain,
    ).execute(executable_rules, top_k=5).rows


if __name__ == "__main__":
    unittest.main()
