from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.adapters.data_warehouse import (
    SchemaValueIndex,
    build_structured_store,
    load_structured_dataset,
)
from src.api.workbench import WorkbenchConfig
from src.domains import DomainConfig
from src.executors.duckdb_executor import DuckDBExecutor
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry
from src.schema.value_entity_linker import ReviewedValueEntityLinker
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import assert_workbench_contract


ROOT = Path(__file__).resolve().parents[1]
ADMISSIONS_DOMAIN = DomainConfig.load("admissions")
SCHEMA_PATH = ADMISSIONS_DOMAIN.schema_path
REQUIRED_COLUMNS = ADMISSIONS_DOMAIN.required_columns
TRACKED_VALUE_INDEX_PATH = ROOT / "outputs/data/schema_value_index.json"


class WorkbenchValueEntityLinkingTest(unittest.TestCase):
    def test_shenzhen_university_prompt_filters_university_not_city(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        filters = _filter_tuples(response)
        self.assertIn(("院校名称", "eq", "深圳大学"), filters)
        self.assertNotIn(("城市", "in_contains", ["深圳"]), filters)
        self.assertTrue(response["top_results"])
        self.assertTrue(
            all(item["university_name"] == "深圳大学" for item in response["top_results"])
        )

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(linking["status"], "applied")
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["accepted_links"]],
            [("university_name", "深圳大学")],
        )
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["suppressed_links"]],
            [("city", "深圳")],
        )
        self.assertEqual(
            response["debug_trace"]["entity_linking"]["accepted_links"][0]["value"],
            "深圳大学",
        )
        warning_messages = [warning["message"] for warning in response["warnings"]]
        self.assertTrue(any("缺少科类" in message for message in warning_messages))
        self.assertTrue(any("再选科目" in message for message in warning_messages))

    def test_shenzhen_city_prompt_filters_city_not_university(self) -> None:
        prompt = "我想去深圳的大学，目前排位15000，帮我看看有什么专业可以选"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        filters = _filter_tuples(response)
        self.assertIn(("城市", "in_contains", ["深圳"]), filters)
        self.assertNotIn(("院校名称", "eq", "深圳大学"), filters)
        self.assertTrue(response["top_results"])
        self.assertTrue(
            any(item["university_name"] != "深圳大学" for item in response["top_results"])
        )

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["accepted_links"]],
            [("city", "深圳")],
        )

    def test_nearby_prompt_does_not_execute_entity_or_city_substring(self) -> None:
        prompt = "我想找深圳大学附近的学校，目前排位15000"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        filters = _filter_tuples(response)
        self.assertNotIn(("院校名称", "eq", "深圳大学"), filters)
        self.assertNotIn(("城市", "in_contains", ["深圳"]), filters)

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(linking["accepted_links"], [])
        self.assertEqual(
            linking["not_executed_links"][0]["match_type"],
            "entity_linking_boundary_required",
        )
        self.assertEqual(linking["not_executed_links"][0]["source_text"], "深圳大学附近")

    def test_nearby_boundary_preserves_other_city_value_in_same_rule(self) -> None:
        prompt = "想找深圳大学附近的学校，也可以广州的大学，目前排位15000"
        response = _run(prompt)

        assert_workbench_contract(self, response)
        filters = _filter_tuples(response)
        self.assertIn(("城市", "in_contains", ["广州"]), filters)
        self.assertNotIn(("城市", "in_contains", ["深圳"]), filters)

        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking["accepted_links"]],
            [("city", "广州")],
        )
        self.assertIn(
            ("深圳大学附近", "entity_linking_boundary_required"),
            [
                (link["source_text"], link["match_type"])
                for link in linking["not_executed_links"]
            ],
        )

    def test_non_executable_entity_context_blocks_regex_city_filter(self) -> None:
        cases = [
            ("不要深圳大学，目前排位15000", "否定/排除"),
            ("离深圳大学近一点，目前排位15000", "距离/模糊地理边界"),
            ("深圳户籍考生，目前排位15000", "身份/户籍"),
        ]
        for prompt, reason_fragment in cases:
            with self.subTest(prompt=prompt):
                response = _run(prompt)

                assert_workbench_contract(self, response)
                self.assertNotIn(
                    ("城市", "in_contains", ["深圳"]),
                    _filter_tuples(response),
                )
                linking = response["evidence_pack"]["entity_linking"]
                self.assertTrue(
                    any(
                        link.get("field_id") == "city"
                        and link.get("value") == "深圳"
                        and reason_fragment in link.get("reason", "")
                        for link in linking["not_executed_links"]
                    )
                )

    def test_builtin_artifact_links_shenzhen_university_not_city(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "sample.xlsx"
            database_path = root / "sample.duckdb"
            scratch_index_path = root / "scratch_schema_value_index.json"
            _live_artifact_dataframe().to_excel(workbook_path, index=False)
            build_structured_store(
                workbook_path=workbook_path,
                required_columns=REQUIRED_COLUMNS,
                schema_path=SCHEMA_PATH,
                database_path=database_path,
                index_path=scratch_index_path,
            )
            loaded = load_structured_dataset(database_path, REQUIRED_COLUMNS)
            registry = SchemaRegistry.from_file(SCHEMA_PATH, loaded.headers)
            value_index = SchemaValueIndex.from_file(TRACKED_VALUE_INDEX_PATH)
            linking = ReviewedValueEntityLinker(registry, value_index).link(prompt)
            verified_rules = RuleVerifier(
                registry,
                domain_config=ADMISSIONS_DOMAIN,
            ).audit_proposed_rules(linking.proposed_rules)
            executable_rules = [
                rule
                for rule in verified_rules
                if rule.get("verification", {}).get("executable")
            ]
            execution = DuckDBExecutor(
                database_path,
                domain_config=ADMISSIONS_DOMAIN,
            ).execute(executable_rules, user_rank=15000)

        self.assertEqual(linking.status, "applied")
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking.accepted_links],
            [("university_name", "深圳大学")],
        )
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in linking.suppressed_links],
            [("city", "深圳")],
        )
        self.assertIn(
            ("院校名称", "eq", "深圳大学"),
            [(rule["field"], rule["operator"], rule["value"]) for rule in executable_rules],
        )
        self.assertNotIn(
            ("城市", "in_contains", ["深圳"]),
            [(rule["field"], rule["operator"], rule["value"]) for rule in executable_rules],
        )
        self.assertTrue(execution.rows)
        self.assertTrue(
            all(row["院校名称"] == "深圳大学" for row in execution.rows[:5])
        )


def _run(prompt: str) -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=prompt,
            soft_preferences={"prompt": prompt},
            extractor="regex",
            planner_mode="legacy",
        )
    )


def _live_artifact_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "生源地": "广东",
                "科类": "物理",
                "选科要求": "不限",
                "院校名称": "深圳大学",
                "院校专业组代码": "10590101",
                "专业代码": "080901",
                "专业名称": "计算机科学与技术",
                "专业全称": "计算机科学与技术",
                "城市": "深圳",
                "专业组最低位次1": 16000,
                "最低位次1": 15500,
                "学费": "6850元/年",
                "计划人数": 20,
            },
            {
                "生源地": "广东",
                "科类": "物理",
                "选科要求": "不限",
                "院校名称": "广州大学",
                "院校专业组代码": "11078101",
                "专业代码": "080902",
                "专业名称": "软件工程",
                "专业全称": "软件工程",
                "城市": "广州",
                "专业组最低位次1": 22000,
                "最低位次1": 21800,
                "学费": "6850元/年",
                "计划人数": 30,
            },
        ]
    )


def _filter_tuples(response: dict[str, object]) -> list[tuple[object, object, object]]:
    return [
        (item["field"], item["operator"], item["value"])
        for item in response["executed_filters"]
    ]


if __name__ == "__main__":
    unittest.main()
