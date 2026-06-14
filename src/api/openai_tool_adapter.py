"""OpenAI-compatible tool export for the LLM-safe tool layer."""

from __future__ import annotations

import json
import re
from typing import Any

from src.api.tool_registry import (
    LLM_SAFE_TOOL_NAMES,
    TOOL_CONTRACT_VERSION,
    ToolPermissionError,
    ToolRegistryError,
    get_tool_schema,
    invoke_tool,
    list_tools,
)


OPENAI_NAME_SEPARATOR = "__"
UNSAFE_MESSAGE_PATTERN = re.compile(
    r"(secret|api[_-]?key|token|password|passwd|traceback|stack|\.env)",
    re.IGNORECASE,
)
UNSAFE_PATH_PATTERN = re.compile(r"(/Users/[^\s\"']+|/tmp/[^\s\"']+|/var/[^\s\"']+)")


class OpenAIToolAdapter:
    """把内部 tool contract 转成 OpenAI function tools。"""

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
        self.llm_safe_only = llm_safe_only

    def export_tools(self) -> list[dict[str, Any]]:
        """返回可直接传给 OpenAI-compatible tool calling 的 tools。"""

        tools = []
        for tool_name in sorted(self.allowed_tool_names):
            contract = get_tool_schema(tool_name)
            tools.append(contract_to_openai_tool(contract))
        return tools

    def manifest(self) -> dict[str, Any]:
        """返回带版本的 OpenAI tools manifest。"""

        return {
            "tool_contract_version": TOOL_CONTRACT_VERSION,
            "adapter": "openai",
            "llm_safe_only": self.llm_safe_only,
            "tools": self.export_tools(),
        }

    def invoke(
        self,
        function_name: str,
        arguments: str | dict[str, Any],
        actor_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行一个 OpenAI function tool call 并返回 tool 原始输出。"""

        tool_name = openai_name_to_tool_name(function_name)
        if tool_name not in self.allowed_tool_names:
            return adapter_error(
                "tool_not_allowed",
                f"Tool is not available to this adapter: {tool_name}",
            )
        try:
            payload = parse_arguments(arguments)
            return invoke_tool(tool_name, payload, actor_context or {})
        except Exception as exc:  # noqa: BLE001 - adapter 边界统一结构化错误。
            return adapter_error(error_code(exc), str(exc))


def export_openai_tools(
    *,
    llm_safe_only: bool = True,
    allowed_tool_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """便捷函数：导出 OpenAI-compatible tools。"""

    return OpenAIToolAdapter(
        allowed_tool_names=allowed_tool_names,
        llm_safe_only=llm_safe_only,
    ).export_tools()


def contract_to_openai_tool(contract: dict[str, Any]) -> dict[str, Any]:
    """把单个内部 contract 转为 OpenAI tool object。"""

    return {
        "type": "function",
        "function": {
            "name": tool_name_to_openai_name(str(contract["name"])),
            "description": str(contract["description"]),
            "parameters": contract["input_schema"],
        },
    }


def tool_name_to_openai_name(tool_name: str) -> str:
    """OpenAI function name 不使用点号，内部点号用双下划线映射。"""

    return tool_name.replace(".", OPENAI_NAME_SEPARATOR)


def openai_name_to_tool_name(function_name: str) -> str:
    return function_name.replace(OPENAI_NAME_SEPARATOR, ".")


def parse_arguments(arguments: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return dict(arguments)
    try:
        payload = json.loads(arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ToolRegistryError("Invalid JSON tool arguments") from exc
    if not isinstance(payload, dict):
        raise ToolRegistryError("Tool arguments must decode to an object")
    return payload


def adapter_error(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": sanitize_message(message),
        },
    }


def error_code(exc: Exception) -> str:
    if isinstance(exc, ToolPermissionError):
        return "permission_denied"
    if isinstance(exc, ToolRegistryError):
        return "invalid_tool_request"
    return "tool_error"


def sanitize_message(message: str) -> str:
    if UNSAFE_MESSAGE_PATTERN.search(message):
        return "[redacted]"
    return UNSAFE_PATH_PATTERN.sub("[redacted_path]", message)
