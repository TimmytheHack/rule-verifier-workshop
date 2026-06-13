from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pandas as pd

from src.domains import DomainConfig
from src.executors.duckdb_executor import DuckDBExecutor
from src.reporting.evidence_pack import EvidencePack
from src.reporting.template_report_builder import TemplateReportBuilder
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry
from src.tracing.trace_generator import TraceGenerator


class DomainConfigTest(unittest.TestCase):
    def test_housing_fixture_runs_through_shared_pipeline(self) -> None:
        domain = DomainConfig.load("housing")
        cases = json.loads(domain.golden_cases_path.read_text(encoding="utf-8"))[
            "cases"
        ]
        case = cases[0]
        dataframe = pd.read_csv(domain.fixture_path)

        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "housing.duckdb"
            with duckdb.connect(str(database_path)) as connection:
                connection.register("source_dataframe", dataframe)
                connection.execute(
                    'CREATE OR REPLACE TABLE "housing" AS SELECT * FROM source_dataframe'
                )

            registry = SchemaRegistry.from_domain(domain, list(dataframe.columns))
            grounding = AttributeGrounder(
                registry,
                domain_config=domain,
            ).ground(case["slots"])
            verifier = RuleVerifier(registry, domain_config=domain)
            classified = RuleClassifier(
                domain.rule_taxonomy_path,
                verifier,
                domain_config=domain,
            ).classify(case["slots"])
            final_rules = RulePromoter(
                domain.rule_taxonomy_path,
                simulated_confirmation_enabled=True,
                domain_config=domain,
            ).final_executable_rules(classified)
            execution = DuckDBExecutor(
                database_path,
                table_name=domain.table_name,
                domain_config=domain,
            ).execute(final_rules, top_k=5)

        traced = TraceGenerator().add_traces(
            execution.rows,
            executable_rules=final_rules,
            not_executed_preferences=classified.get("non_executable_preferences", []),
        )
        evidence = EvidencePack.from_verified_pipeline(
            user_request="Austin, at least 2 bedrooms, under 1900.",
            executed_rules=final_rules,
            classified_rules=classified,
            traced_results=traced,
            attribute_grounding=grounding,
            execution_summary=execution.audit.to_dict(),
            domain_config=domain,
        )
        answer = TemplateReportBuilder(domain_config=domain).build(evidence)

        self.assertEqual([rule["rule_id"] for rule in final_rules], case["hard_rule_ids"])
        self.assertEqual(len(execution.rows), case["result_count"])
        self.assertEqual(execution.rows[0]["listing_id"], case["top"]["listing_id"])
        self.assertEqual(execution.rows[0]["rent_usd"], case["top"]["rent_usd"])
        self.assertEqual(
            grounding["summary"]["status_counts"],
            {"schema_grounded": 4},
        )
        self.assertIn("月租", answer)
        self.assertIn("共筛选到 3 条", answer)


if __name__ == "__main__":
    unittest.main()
