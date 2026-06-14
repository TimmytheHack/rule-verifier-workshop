from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from jsonschema import Draft202012Validator

from src.api.tool_registry import (
    FORBIDDEN_LLM_INPUT_FIELDS,
    ToolPermissionError,
    get_tool_schema,
    invoke_tool,
    list_tools,
)
from tests.workbench_contract_utils import assert_workbench_contract


ROOT = Path(__file__).resolve().parents[1]
TOOL_SCHEMA_DIR = ROOT / "schemas/tools"
CONTRACT_META_SCHEMA = {
    "type": "object",
    "required": [
        "name",
        "description",
        "input_schema",
        "output_schema",
        "permission_scope",
        "side_effects",
        "required_domain_status",
        "executes_sql",
        "writes_files",
        "security_notes",
        "status_enum",
        "examples",
    ],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "permission_scope": {
            "type": "string",
            "enum": [
                "read_only",
                "query",
                "confirm",
                "dataset_write",
                "review_admin",
                "warehouse_admin",
                "diagnostics",
            ],
        },
        "side_effects": {"type": "array"},
        "required_domain_status": {},
        "executes_sql": {"type": "boolean"},
        "writes_files": {"type": "boolean"},
        "security_notes": {"type": "array", "minItems": 1},
        "status_enum": {"type": "array", "minItems": 1},
        "examples": {"type": "array", "minItems": 1},
    },
}


class ToolContractTest(unittest.TestCase):
    def test_all_tool_contracts_are_valid_jsonschema(self) -> None:
        meta = Draft202012Validator(CONTRACT_META_SCHEMA)
        expected = {
            "dataset.upload",
            "dataset.profile",
            "dataset.generate_domain_pack",
            "dataset.review_summary",
            "dataset.approve_field",
            "dataset.approve_op",
            "dataset.block_field",
            "dataset.approve_domain",
            "dataset.build_warehouse",
            "workbench.query",
            "workbench.confirm",
            "evidence.get",
            "quality.run",
            "pilot.run",
        }
        found = set()

        for path in TOOL_SCHEMA_DIR.glob("*.json"):
            contract = json.loads(path.read_text(encoding="utf-8"))
            found.add(contract["name"])
            meta.validate(contract)
            Draft202012Validator.check_schema(contract["input_schema"])
            Draft202012Validator.check_schema(contract["output_schema"])

        self.assertEqual(found, expected)

    def test_llm_safe_tools_exclude_admin_tools(self) -> None:
        names = {tool["name"] for tool in list_tools(llm_safe_only=True)}

        self.assertEqual(
            names,
            {
                "dataset.profile",
                "dataset.review_summary",
                "workbench.query",
                "workbench.confirm",
                "evidence.get",
            },
        )
        self.assertFalse(any(name.startswith("dataset.approve") for name in names))
        self.assertNotIn("dataset.build_warehouse", names)
        self.assertNotIn("quality.run", names)
        self.assertNotIn("pilot.run", names)

    def test_llm_safe_input_schemas_do_not_accept_bypass_fields(self) -> None:
        for tool in list_tools(llm_safe_only=True):
            contract = get_tool_schema(tool["name"])
            serialized = json.dumps(contract["input_schema"], ensure_ascii=False)
            for forbidden in FORBIDDEN_LLM_INPUT_FIELDS:
                self.assertNotIn(forbidden, serialized)

    def test_workbench_query_draft_domain_returns_blocked(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _generated_generic_dataset(root)

            response = invoke_tool(
                "workbench.query",
                {
                    "dataset_id": dataset_id,
                    "natural_language": "Austin under 1900",
                    "deterministic_fields": {
                        "city": ["Austin"],
                        "rent_usd": 1900,
                    },
                },
                _actor(root, ["query"]),
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["domain_pack_status"], "needs_review")
        self.assertEqual(response["debug_trace"]["execution"]["sql"], "")

    def test_workbench_query_approved_warehouse_returns_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _queryable_generic_dataset(root)

            response = invoke_tool(
                "workbench.query",
                {
                    "dataset_id": dataset_id,
                    "natural_language": "Austin under 1900",
                    "deterministic_fields": {
                        "city": ["Austin"],
                        "rent_usd": 1900,
                    },
                    "top_k": 5,
                },
                _actor(root, ["query"]),
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertGreaterEqual(response["result_count"], 1)
        self.assertTrue(response["items"])

    def test_workbench_confirm_forged_candidate_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _queryable_generic_dataset(root)
            previous = invoke_tool(
                "workbench.query",
                {
                    "dataset_id": dataset_id,
                    "natural_language": "Austin under 1900",
                    "deterministic_fields": {
                        "city": ["Austin"],
                        "rent_usd": 1900,
                    },
                },
                _actor(root, ["query"]),
            )

            response = invoke_tool(
                "workbench.confirm",
                {
                    "previous_response": previous,
                    "confirmed_candidate_ids": ["forged_candidate_id"],
                },
                _actor(root, ["confirm"]),
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "blocked")
        self.assertTrue(response["rejected_confirmations"])

    def test_review_admin_permissions_are_required(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _generated_generic_dataset(root)

            with self.assertRaises(ToolPermissionError):
                invoke_tool(
                    "dataset.approve_field",
                    {"dataset_id": dataset_id, "field_id": "city"},
                    _actor(root, ["query"]),
                )
            with self.assertRaises(ToolPermissionError):
                invoke_tool(
                    "dataset.approve_op",
                    {"dataset_id": dataset_id, "field_id": "city", "op": "in"},
                    _actor(root, ["query"]),
                )

    def test_approve_tools_write_audit_records(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _generated_generic_dataset(root)
            actor = _actor(root, ["review_admin"])

            field_result = invoke_tool(
                "dataset.approve_field",
                {"dataset_id": dataset_id, "field_id": "city"},
                actor,
            )
            op_result = invoke_tool(
                "dataset.approve_op",
                {"dataset_id": dataset_id, "field_id": "city", "op": "in"},
                actor,
            )
            audit_lines = [
                json.loads(line)
                for line in (root / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(field_result["ok"])
        self.assertTrue(op_result["ok"])
        self.assertIn("dataset.approve_field", [line["tool_name"] for line in audit_lines])
        self.assertIn("dataset.approve_op", [line["tool_name"] for line in audit_lines])
        self.assertTrue(all(line["status"] == "ok" for line in audit_lines[-2:]))

    def test_evidence_get_redacts_unsafe_material(self) -> None:
        response = invoke_tool(
            "evidence.get",
            {
                "workbench_response": {
                    "evidence_pack": {
                        "result_count": 1,
                        "stack_trace": "Traceback: /Users/tz/.env SECRET=abc",
                        "source_path": "/Users/tz/Desktop/Projects/SZU/.env",
                        "nested": {
                            "api_key": "sk-secret",
                            "safe": "可展示",
                        },
                    }
                }
            },
            {
                "actor_id": "reader",
                "permission_scopes": ["read_only"],
                "audit_path": str(Path("outputs/tool_audit/test_audit.jsonl")),
            },
        )

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertIn("可展示", serialized)
        self.assertNotIn("Traceback", serialized)
        self.assertNotIn("/Users/tz", serialized)
        self.assertNotIn("sk-secret", serialized)
        self.assertNotIn("api_key", serialized)

    def test_tool_outputs_match_response_contracts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _generated_generic_dataset(root)
            profile = invoke_tool(
                "dataset.profile",
                {"dataset_id": dataset_id},
                _actor(root, ["read_only"]),
            )
            review = invoke_tool(
                "dataset.review_summary",
                {"dataset_id": dataset_id},
                _actor(root, ["read_only"]),
            )
            response = invoke_tool(
                "workbench.query",
                {
                    "dataset_id": dataset_id,
                    "natural_language": "Austin under 1900",
                    "deterministic_fields": {"city": ["Austin"]},
                },
                _actor(root, ["query"]),
            )

        self.assertIn("fields", profile)
        self.assertIn("reviewable_fields", review)
        assert_workbench_contract(self, response)


def _actor(root: Path, permissions: list[str]) -> dict[str, object]:
    return {
        "actor_id": "unit_tester",
        "permission_scopes": permissions,
        "dataset_root": str(root / "managed"),
        "audit_path": str(root / "audit.jsonl"),
    }


def _generated_generic_dataset(root: Path) -> str:
    source = root / "housing.csv"
    pd.DataFrame(
        [
            {"listing_id": 1, "city": "Austin", "rent_usd": 1800, "bedrooms": 2},
            {"listing_id": 2, "city": "Dallas", "rent_usd": 1600, "bedrooms": 1},
            {"listing_id": 3, "city": "Austin", "rent_usd": 2100, "bedrooms": 3},
        ]
    ).to_csv(source, index=False)
    dataset_id = "ds_tool_contract"
    actor = _actor(root, ["dataset_write"])
    invoke_tool(
        "dataset.upload",
        {
            "filename": source.name,
            "source_path": str(source),
            "dataset_id": dataset_id,
        },
        actor,
    )
    invoke_tool(
        "dataset.generate_domain_pack",
        {"dataset_id": dataset_id, "domain_name": "tool_housing"},
        actor,
    )
    return dataset_id


def _queryable_generic_dataset(root: Path) -> str:
    dataset_id = _generated_generic_dataset(root)
    review_actor = _actor(root, ["review_admin"])
    for field_id in ["listing_id", "city", "rent_usd"]:
        invoke_tool(
            "dataset.approve_field",
            {"dataset_id": dataset_id, "field_id": field_id},
            review_actor,
        )
    invoke_tool(
        "dataset.approve_op",
        {"dataset_id": dataset_id, "field_id": "city", "op": "in"},
        review_actor,
    )
    invoke_tool(
        "dataset.approve_op",
        {"dataset_id": dataset_id, "field_id": "rent_usd", "op": "<="},
        review_actor,
    )
    approved = invoke_tool(
        "dataset.approve_domain",
        {
            "dataset_id": dataset_id,
            "title_field": "listing_id",
            "primary_fields": ["city", "rent_usd"],
            "sort_field": "rent_usd",
        },
        review_actor,
    )
    if not approved["ok"]:
        raise AssertionError(json.dumps(approved, ensure_ascii=False, indent=2))
    built = invoke_tool(
        "dataset.build_warehouse",
        {"dataset_id": dataset_id},
        _actor(root, ["warehouse_admin"]),
    )
    if built["status"] != "queryable":
        raise AssertionError(json.dumps(built, ensure_ascii=False, indent=2))
    return dataset_id


if __name__ == "__main__":
    unittest.main()
