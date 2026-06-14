from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.api.openai_tool_adapter import (
    OpenAIToolAdapter,
    openai_name_to_tool_name,
    tool_name_to_openai_name,
)
from src.api.tool_registry import list_tools
from tests.test_tool_contract import _actor, _queryable_generic_dataset
from tests.workbench_contract_utils import assert_workbench_contract


ROOT = Path(__file__).resolve().parents[1]
OPENAI_FUNCTION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class OpenAIToolAdapterTest(unittest.TestCase):
    def test_default_export_contains_only_llm_safe_tools(self) -> None:
        adapter = OpenAIToolAdapter()
        tools = adapter.export_tools()
        names = {tool["function"]["name"] for tool in tools}

        self.assertEqual(
            names,
            {
                "dataset__profile",
                "dataset__review_summary",
                "workbench__query",
                "workbench__confirm",
                "evidence__get",
            },
        )
        self.assertFalse(any("approve" in name for name in names))
        self.assertNotIn("dataset__build_warehouse", names)
        for tool in tools:
            function = tool["function"]
            self.assertEqual(tool["type"], "function")
            self.assertRegex(function["name"], OPENAI_FUNCTION_RE)
            self.assertNotIn(".", function["name"])
            self.assertIn("parameters", function)

    def test_name_mapping_round_trips(self) -> None:
        for tool_name in [
            "dataset.profile",
            "dataset.review_summary",
            "workbench.query",
            "workbench.confirm",
            "evidence.get",
        ]:
            openai_name = tool_name_to_openai_name(tool_name)
            self.assertEqual(openai_name_to_tool_name(openai_name), tool_name)

    def test_invoke_workbench_query_with_json_arguments(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = _queryable_generic_dataset(root)
            adapter = OpenAIToolAdapter()
            response = adapter.invoke(
                "workbench__query",
                json.dumps(
                    {
                        "dataset_id": dataset_id,
                        "natural_language": "Austin under 1900",
                        "deterministic_fields": {
                            "city": ["Austin"],
                            "rent_usd": 1900,
                        },
                    }
                ),
                _actor(root, ["query"]),
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["items"])

    def test_admin_tool_is_not_callable_by_default_adapter(self) -> None:
        adapter = OpenAIToolAdapter()
        response = adapter.invoke(
            "dataset__approve_op",
            {"dataset_id": "ds_any", "field_id": "city", "op": "in"},
            {"actor_id": "agent", "permission_scopes": ["query"]},
        )

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "tool_not_allowed")

    def test_non_default_manifest_can_mark_admin_export(self) -> None:
        adapter = OpenAIToolAdapter(
            allowed_tool_names={tool["name"] for tool in list_tools()},
            llm_safe_only=False,
        )
        manifest = adapter.manifest()
        names = {tool["function"]["name"] for tool in manifest["tools"]}

        self.assertFalse(manifest["llm_safe_only"])
        self.assertIn("dataset__approve_op", names)

    def test_export_openai_tools_script_defaults_to_llm_safe(self) -> None:
        with TemporaryDirectory() as directory:
            output_path = Path(directory) / "openai_tools.json"
            completed = subprocess.run(
                [
                    ".venv/bin/python",
                    "scripts/export_openai_tools.py",
                    "--output-path",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["adapter"], "openai")
        self.assertTrue(payload["llm_safe_only"])
        names = {tool["function"]["name"] for tool in payload["tools"]}
        self.assertEqual(
            names,
            {
                "dataset__profile",
                "dataset__review_summary",
                "workbench__query",
                "workbench__confirm",
                "evidence__get",
            },
        )


if __name__ == "__main__":
    unittest.main()
