"""Minimal MCP-style adapter for the LLM-safe tool registry."""

from __future__ import annotations

import json
from typing import Any

from src.api.openai_tool_adapter import adapter_error, error_code, sanitize_message
from src.api.tool_registry import (
    LLM_SAFE_TOOL_NAMES,
    TOOL_CONTRACT_VERSION,
    get_tool_schema,
    invoke_tool,
    list_tools,
)


class MCPToolAdapter:
    """把内部 tool registry 暴露为 MCP-style list/call adapter。"""

    def __init__(
        self,
        *,
        allowed_tool_names: set[str] | None = None,
        llm_safe_only: bool = True,
    ) -> None:
        if allowed_tool_names is None:
            public_tools = list_tools(llm_safe_only=llm_safe_only)
            allowed_tool_names = {tool["name"] for tool in public_tools}
        if llm_safe_only:
            allowed_tool_names = set(allowed_tool_names) & set(LLM_SAFE_TOOL_NAMES)
        self.allowed_tool_names = set(allowed_tool_names)

    def list_tools(self) -> dict[str, Any]:
        """返回 MCP tools/list 风格 payload。"""

        return {
            "tool_contract_version": TOOL_CONTRACT_VERSION,
            "tools": [
                self._contract_to_mcp_tool(get_tool_schema(tool_name))
                for tool_name in sorted(self.allowed_tool_names)
            ],
        }

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        actor_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回 MCP tools/call 风格 payload。"""

        if name not in self.allowed_tool_names:
            return mcp_error(
                adapter_error(
                    "tool_not_allowed",
                    f"Tool is not available to this adapter: {name}",
                )
            )
        try:
            output = invoke_tool(name, dict(arguments), actor_context or {})
            return mcp_success(output)
        except Exception as exc:  # noqa: BLE001 - adapter 边界统一结构化错误。
            return mcp_error(adapter_error(error_code(exc), str(exc)))

    @staticmethod
    def _contract_to_mcp_tool(contract: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": contract["name"],
            "description": contract["description"],
            "inputSchema": contract["input_schema"],
        }


def mcp_success(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "isError": False,
        "content": [
            {
                "type": "text",
                "text": json.dumps(output, ensure_ascii=False),
            }
        ],
        "structuredContent": output,
    }


def mcp_error(error: dict[str, Any]) -> dict[str, Any]:
    safe_error = {
        "status": "error",
        "error": {
            "code": str((error.get("error") or {}).get("code") or "tool_error"),
            "message": sanitize_message(
                str((error.get("error") or {}).get("message") or "tool error")
            ),
        },
    }
    return {
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": json.dumps(safe_error, ensure_ascii=False),
            }
        ],
        "structuredContent": safe_error,
    }
