"""从 schemas/tools 导出统一 tool manifest。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - bootstrap 前的降级路径。
    Draft202012Validator = None  # type: ignore[assignment]

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.api.tool_registry import TOOL_CONTRACT_VERSION, get_tool_schema, list_tools


DEFAULT_OUTPUT_PATH = Path("outputs/tool_manifest/tool_manifest.json")
MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tool_contract_version", "tools"],
    "properties": {
        "tool_contract_version": {"type": "string"},
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "name",
                    "permission_scope",
                    "llm_safe",
                    "side_effects",
                    "executes_sql",
                    "writes_files",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "permission_scope": {"type": "string"},
                    "llm_safe": {"type": "boolean"},
                    "side_effects": {"type": "array"},
                    "executes_sql": {"type": "boolean"},
                    "writes_files": {"type": "boolean"},
                    "required_domain_status": {},
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "status_enum": {"type": "array"},
                    "security_notes": {"type": "array"},
                },
            },
        },
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    output_path = Path(args.output_path)
    manifest = build_manifest()
    validate_manifest(manifest)
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


def build_manifest() -> dict[str, Any]:
    """把每个 tool contract 摘要和 schema 打包进 manifest。"""

    tools = []
    for public in list_tools():
        contract = get_tool_schema(public["name"])
        tools.append(
            {
                "name": contract["name"],
                "description": contract["description"],
                "permission_scope": contract["permission_scope"],
                "llm_safe": bool(contract.get("llm_safe")),
                "side_effects": list(contract.get("side_effects") or []),
                "executes_sql": bool(contract.get("executes_sql")),
                "writes_files": bool(contract.get("writes_files")),
                "required_domain_status": contract.get("required_domain_status"),
                "status_enum": list(contract.get("status_enum") or []),
                "security_notes": list(contract.get("security_notes") or []),
                "input_schema": contract["input_schema"],
                "output_schema": contract["output_schema"],
            }
        )
    return {
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "tools": sorted(tools, key=lambda item: item["name"]),
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    """校验 manifest 形状，便于测试和部署前检查复用。"""

    if Draft202012Validator is None:
        return
    Draft202012Validator(MANIFEST_SCHEMA).validate(manifest)


if __name__ == "__main__":
    raise SystemExit(main())
