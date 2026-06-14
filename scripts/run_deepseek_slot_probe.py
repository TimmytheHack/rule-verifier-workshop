"""运行一次 DeepSeek slot adapter 探针，不输出密钥或完整 prompt。"""

from __future__ import annotations

import argparse
import json
from typing import Any

from src.api.workbench import WorkbenchConfig, run_workbench
from src.extractors.llm_slot_adapter import (
    deepseek_slot_adapter_enabled,
    llm_runtime_enabled,
)


DEFAULT_QUERY = "广东物理类，排位12345，想学环境工程，广州。"


def run_probe(query: str, extractor: str) -> dict[str, Any]:
    response = run_workbench(
        WorkbenchConfig(
            user_input=query,
            soft_preferences={"prompt": query},
            extractor=extractor,
            generator="template_evidence",
        )
    )
    slots = response.get("extracted_slots") or {}
    fallback = slots.get("fallback_extraction") or {}
    execution = response.get("execution") or {}
    return {
        "llm_runtime_enabled": llm_runtime_enabled(),
        "deepseek_slot_adapter_enabled": deepseek_slot_adapter_enabled(),
        "status": response.get("status"),
        "query_type": response.get("query_type"),
        "result_count": response.get("result_count"),
        "fallback_extraction": fallback,
        "llm_slot_adapter": slots.get("llm_slot_adapter"),
        "token_usage": (response.get("token_usage") or {}).get("extractor"),
        "extracted_slots_summary": {
            "user_context": slots.get("user_context"),
            "preferences": slots.get("preferences"),
            "proposed_rules": slots.get("proposed_rules"),
            "unmapped_preferences": slots.get("unmapped_preferences"),
        },
        "execution_summary": {
            "executor": execution.get("executor"),
            "filtered_row_count": execution.get("filtered_row_count"),
            "hard_rule_ids": execution.get("hard_rule_ids"),
        },
        "warnings": response.get("warnings") or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe DeepSeek slot adapter without exposing secrets."
    )
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument(
        "--extractor",
        choices=["hybrid", "deepseek"],
        default="hybrid",
    )
    args = parser.parse_args()

    if not llm_runtime_enabled():
        print(
            "ENABLE_LLM is not true. Set ENABLE_LLM=true in .env before running "
            "this probe."
        )
        raise SystemExit(2)
    if not deepseek_slot_adapter_enabled():
        print(
            "DeepSeek slot adapter is disabled. Check DEEPSEEK_API_KEY in .env."
        )
        raise SystemExit(2)

    print(json.dumps(run_probe(args.query, args.extractor), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
