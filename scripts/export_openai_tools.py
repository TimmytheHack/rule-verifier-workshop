"""导出 OpenAI-compatible tools JSON。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.api.openai_tool_adapter import OpenAIToolAdapter
from src.api.tool_registry import list_tools


DEFAULT_OUTPUT_PATH = Path("outputs/tool_manifest/openai_tools.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument(
        "--include-admin",
        action="store_true",
        help="显式导出所有 tools；默认只导出 LLM-safe tools。",
    )
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)

    if args.include_admin:
        allowed = {tool["name"] for tool in list_tools()}
        adapter = OpenAIToolAdapter(
            allowed_tool_names=allowed,
            llm_safe_only=False,
        )
    else:
        adapter = OpenAIToolAdapter()
    manifest = adapter.manifest()
    if args.include_admin:
        manifest["llm_safe_only"] = False
        manifest["admin_export_requires_operator_review"] = True
        _attach_admin_warnings(manifest)

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.json_only:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {output_path}")
    return 0


def _attach_admin_warnings(manifest: dict[str, object]) -> None:
    tools = manifest.get("tools") or []
    for tool in tools:
        function = dict(tool.get("function") or {})
        name = str(function.get("name") or "")
        if name.startswith("dataset__approve") or name in {
            "dataset__build_warehouse",
            "quality__run",
            "pilot__run",
        }:
            function["description"] = (
                f"{function.get('description', '')} "
                "ADMIN ONLY: do not expose to LLM-safe agents."
            ).strip()
            tool["function"] = function


if __name__ == "__main__":
    raise SystemExit(main())
