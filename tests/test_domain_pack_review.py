from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.generate_domain_pack import generate_domain_pack
from scripts.review_domain_pack import (
    approve_domain,
    approve_field,
    approve_op,
    block_field,
    summarize_domain_pack,
    validate_domain_pack,
    write_review_report,
)
from src.api.workbench import WorkbenchConfig, run_workbench
from src.domains import DomainConfig
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[1]
HOUSING_FIXTURE = ROOT / "domains/housing/fixtures/housing.csv"
PRODUCTS_FIXTURE = ROOT / "domains/products/fixtures/products.csv"


class DomainPackReviewTest(unittest.TestCase):
    def test_draft_domain_summarize_and_validate(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )

            summary = summarize_domain_pack(result.domain_dir)
            validation = validate_domain_pack(result.domain_dir)

        self.assertEqual(summary["domain"], "review_housing")
        self.assertEqual(summary["domain_pack_status"], "draft")
        self.assertEqual(summary["field_count"], 7)
        self.assertTrue(validation["ok"])

    def test_approve_field_then_block_field_controls_executability(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )

            approved = approve_field(result.domain_dir, "city", write=True)
            approved_rule = _verify_rule(
                result.domain_dir,
                {"field_id": "city", "field": "city", "operator": "in", "value": ["Austin"]},
            )
            blocked = block_field(result.domain_dir, "city", write=True)
            blocked_rule = _verify_rule(
                result.domain_dir,
                {"field_id": "city", "field": "city", "operator": "in", "value": ["Austin"]},
            )

        self.assertTrue(approved.ok)
        self.assertTrue(approved_rule["verification"]["executable"])
        self.assertTrue(blocked.ok)
        self.assertFalse(blocked_rule["verification"]["executable"])

    def test_mutations_are_dry_run_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )
            before = (result.schema_path).read_text(encoding="utf-8")

            dry_run = approve_field(result.domain_dir, "city")
            after = (result.schema_path).read_text(encoding="utf-8")

        self.assertTrue(dry_run.ok)
        self.assertFalse(dry_run.written)
        self.assertEqual(before, after)

    def test_approve_op_only_opens_specified_operator(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )

            approved = approve_op(result.domain_dir, "city", "in", write=True)
            schema = json.loads(
                (result.domain_dir / "schema_registry.json").read_text(
                    encoding="utf-8"
                )
            )
            in_rule = _verify_rule(
                result.domain_dir,
                {"field_id": "city", "field": "city", "operator": "in", "value": ["Austin"]},
            )
            eq_rule = _verify_rule(
                result.domain_dir,
                {"field_id": "city", "field": "city", "operator": "eq", "value": "Austin"},
            )

        self.assertTrue(approved.ok)
        self.assertEqual(schema["fields"]["city"]["allowed_ops"], ["in"])
        self.assertTrue(in_rule["verification"]["executable"])
        self.assertFalse(eq_rule["verification"]["executable"])

    def test_pii_and_high_cardinality_fields_cannot_auto_approve(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=PRODUCTS_FIXTURE,
                domain_name="review_products",
                output_root=directory,
            )

            email = approve_field(result.domain_dir, "email_contact", write=True)
            product_name = approve_field(result.domain_dir, "product_name", write=True)
            contains = approve_op(
                result.domain_dir,
                "description",
                "contains",
                write=True,
            )

        self.assertFalse(email.ok)
        self.assertFalse(product_name.ok)
        self.assertFalse(contains.ok)

    def test_draft_domain_with_reviewed_field_is_still_blocked(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )
            approve_field(result.domain_dir, "city", write=True)

            response = run_workbench(
                WorkbenchConfig(
                    domain_name="review_housing",
                    domain_path=str(result.domain_dir),
                    user_input="Austin",
                    hard_filters={"city": ["Austin"]},
                    soft_preferences={"prompt": "Austin"},
                    extractor="regex",
                )
            )

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["domain_pack_status"], "draft")
        self.assertEqual(response["debug_trace"]["execution"]["sql"], "")

    def test_approve_domain_requires_title_and_primary_mapping(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )
            approve_field(result.domain_dir, "listing_id", write=True)
            approve_field(result.domain_dir, "city", write=True)
            approve_field(result.domain_dir, "rent_usd", write=True)

            missing_title = approve_domain(
                result.domain_dir,
                primary_fields=["city"],
                sort_field="rent_usd",
                write=True,
            )
            missing_primary = approve_domain(
                result.domain_dir,
                title_field="listing_id",
                sort_field="rent_usd",
                write=True,
            )

        self.assertFalse(missing_title.ok)
        self.assertIn("title", "\n".join(missing_title.payload["failures"]))
        self.assertFalse(missing_primary.ok)
        self.assertIn("primary", "\n".join(missing_primary.payload["failures"]))

    def test_approve_domain_enables_workbench_smoke_query(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )
            approve_field(result.domain_dir, "listing_id", write=True)
            approve_op(result.domain_dir, "city", "in", write=True)
            approve_op(result.domain_dir, "rent_usd", "<=", write=True)
            approved = approve_domain(
                result.domain_dir,
                title_field="listing_id",
                primary_fields=["city", "rent_usd"],
                sort_field="rent_usd",
                write=True,
            )

            response = run_workbench(
                WorkbenchConfig(
                    domain_name="review_housing",
                    domain_path=str(result.domain_dir),
                    user_input="Austin under 1900",
                    hard_filters={"city": ["Austin"], "rent_usd": 1900},
                    soft_preferences={"prompt": "Austin under 1900"},
                    extractor="regex",
                )
            )

        self.assertTrue(approved.ok)
        self.assertEqual(response["status"], "ok")
        self.assertGreater(response["result_count"], 0)
        self.assertTrue(response["items"])
        self.assertEqual(response["domain_pack_status"], "approved")

    def test_review_report_json_and_markdown_are_generated(self) -> None:
        with TemporaryDirectory() as directory:
            result = generate_domain_pack(
                source_path=HOUSING_FIXTURE,
                domain_name="review_housing",
                output_root=directory,
            )
            output_dir = Path(directory) / "review_outputs"

            report = write_review_report(
                result.domain_dir,
                output_dir=output_dir,
                write=True,
            )
            json_path = Path(report.payload["json_path"])
            markdown_path = Path(report.payload["markdown_path"])
            json_exists = json_path.exists()
            markdown_exists = markdown_path.exists()
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertTrue(report.ok)
        self.assertTrue(json_exists)
        self.assertTrue(markdown_exists)
        self.assertEqual(payload["summary"]["domain"], "review_housing")
        self.assertIn("字段摘要", markdown)


def _verify_rule(
    domain_dir: Path,
    rule: dict[str, object],
) -> dict[str, object]:
    domain = DomainConfig.from_path(domain_dir)
    columns = list(pd.read_csv(HOUSING_FIXTURE).columns)
    registry = SchemaRegistry.from_domain(domain, columns)
    verifier = RuleVerifier(registry, domain_config=domain)
    return verifier.attach_verification(
        {
            "rule_id": "test_rule",
            "category": "deterministic",
            "requires_human_confirmation": False,
            **rule,
        }
    )


if __name__ == "__main__":
    unittest.main()
