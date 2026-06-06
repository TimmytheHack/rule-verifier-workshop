"""Compare task success under token budget for the first MVP input.

Modes:
1. regex_extractor_symbolic_verifier
2. deepseek_extractor_symbolic_verifier
3. llm_only_baseline
4. schema_aware_llm_only_baseline

DeepSeek modes are optional. If DEEPSEEK_API_KEY is not set, they are skipped.
Evaluation is not token usage alone: each mode reports task_success_score,
total_tokens, and task_success_score / total_tokens where applicable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.excel_adapter import ExcelAdapter, ExcelDataSet
from src.baselines.llm_only_baseline import LLMOnlyBaseline, SchemaAwareLLMOnlyBaseline
from src.executors.pandas_executor import PandasExecutor
from src.extractors.deepseek_extractor import DeepSeekExtractor, has_deepseek_api_key
from src.extractors.regex_extractor import RegexExtractor
from src.evaluation.scoring import (
    score_llm_only_baseline,
    score_symbolic_task_success,
    unsafe_baseline_flags,
    with_efficiency,
)
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


WORKBOOK_NAME = "广东省2025年志愿填报大数据（24-25）0523.xlsx"
SCHEMA_PATH = Path("schemas/schema_registry.json")
TAXONOMY_PATH = Path("rules/rule_taxonomy.json")
OUTPUT_DIR = Path("outputs/eval")
TOKEN_LOG_PATH = OUTPUT_DIR / "deepseek_token_usage.jsonl"

DEMO_INPUT = "我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"
REQUIRED_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]


def symbolic_pipeline(slots: dict[str, Any], dataset: ExcelDataSet) -> dict[str, Any]:
    registry = SchemaRegistry.from_file(SCHEMA_PATH, dataset.headers)
    attribute_grounding = AttributeGrounder(registry).ground(slots)
    verifier = RuleVerifier(registry)
    classified = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
    final_rules = RulePromoter(
        TAXONOMY_PATH,
        simulated_confirmation_enabled=True,
    ).final_executable_rules(classified)
    rows = PandasExecutor().execute(dataset.dataframe, final_rules)
    final_rule_ids = [rule["rule_id"] for rule in final_rules]
    trace_complete = len(rows) > 0 and all(
        rule_id in final_rule_ids
        for rule_id in [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
            "e_safety_margin",
            "e_tuition_cap",
        ]
    )
    success = score_symbolic_task_success(
        final_rule_ids=final_rule_ids,
        candidate_rules_executable_count=sum(
            1 for rule in classified["candidate_rules"] if rule["verification"]["executable"]
        ),
        cooperation_field_exists=registry.has_field("cooperation_type"),
        cooperation_executed=any(rule.get("field") == "cooperation_type" for rule in final_rules),
        trace_complete=trace_complete,
    )
    return {
        "status": "ok",
        "result_count": len(rows),
        "final_executable_rule_ids": final_rule_ids,
        "candidate_rules_executable_count": sum(
            1 for rule in classified["candidate_rules"] if rule["verification"]["executable"]
        ),
        "cooperation_field_exists": registry.has_field("cooperation_type"),
        "cooperation_executed": any(rule.get("field") == "cooperation_type" for rule in final_rules),
        "trace_complete": trace_complete,
        "task_success": success,
        "attribute_grounding": attribute_grounding,
        "llm_needed_parts": classified["llm_needed_parts"],
    }


def append_usage(mode: str, usage: dict[str, int]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "mode": mode,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    with TOKEN_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

def run_eval() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = ExcelAdapter(WORKBOOK_NAME, REQUIRED_COLUMNS).load()

    modes: dict[str, Any] = {}
    regex_slots = RegexExtractor().extract(DEMO_INPUT)
    modes["regex_extractor_symbolic_verifier"] = with_efficiency(
        symbolic_pipeline(regex_slots, dataset),
        total_tokens=0,
    )
    modes["regex_extractor_symbolic_verifier"]["extracted_slots"] = regex_slots

    has_deepseek_key = has_deepseek_api_key()
    if has_deepseek_key:
        deepseek_slots = DeepSeekExtractor().extract(DEMO_INPUT)
        append_usage("deepseek_extractor_symbolic_verifier", deepseek_slots.get("deepseek_usage", {}))
        modes["deepseek_extractor_symbolic_verifier"] = with_efficiency(
            symbolic_pipeline(deepseek_slots, dataset),
            total_tokens=deepseek_slots.get("deepseek_usage", {}).get("total_tokens", 0),
        )
        modes["deepseek_extractor_symbolic_verifier"]["token_usage"] = deepseek_slots.get("deepseek_usage", {})
        modes["deepseek_extractor_symbolic_verifier"]["extracted_slots"] = deepseek_slots

        baseline_payload = LLMOnlyBaseline().propose(DEMO_INPUT)
        append_usage("llm_only_baseline", baseline_payload.get("deepseek_usage", {}))
        modes["llm_only_baseline"] = {
            "status": "ok",
            "token_usage": baseline_payload.get("deepseek_usage", {}),
            "total_tokens": baseline_payload.get("deepseek_usage", {}).get("total_tokens", 0),
            "task_success": score_llm_only_baseline(baseline_payload),
            "task_success_per_total_token": None,
            "unsafe_flags": unsafe_baseline_flags(baseline_payload),
            "raw_output": baseline_payload,
        }
        total_tokens = modes["llm_only_baseline"]["total_tokens"]
        if total_tokens:
            modes["llm_only_baseline"]["task_success_per_total_token"] = (
                modes["llm_only_baseline"]["task_success"]["task_success_score"] / total_tokens
            )

        schema_fields = SchemaRegistry.from_file(SCHEMA_PATH, dataset.headers).configured_fields
        schema_aware_payload = SchemaAwareLLMOnlyBaseline(schema_fields).propose(DEMO_INPUT)
        append_usage("schema_aware_llm_only_baseline", schema_aware_payload.get("deepseek_usage", {}))
        modes["schema_aware_llm_only_baseline"] = {
            "status": "ok",
            "token_usage": schema_aware_payload.get("deepseek_usage", {}),
            "total_tokens": schema_aware_payload.get("deepseek_usage", {}).get("total_tokens", 0),
            "task_success": score_llm_only_baseline(schema_aware_payload),
            "task_success_per_total_token": None,
            "unsafe_flags": unsafe_baseline_flags(schema_aware_payload),
            "raw_output": schema_aware_payload,
        }
        total_tokens = modes["schema_aware_llm_only_baseline"]["total_tokens"]
        if total_tokens:
            modes["schema_aware_llm_only_baseline"]["task_success_per_total_token"] = (
                modes["schema_aware_llm_only_baseline"]["task_success"]["task_success_score"] / total_tokens
            )
    else:
        skipped = {
            "status": "skipped",
            "reason": "DEEPSEEK_API_KEY is not set.",
            "token_usage": None,
            "total_tokens": None,
            "task_success": None,
            "task_success_per_total_token": None,
        }
        modes["deepseek_extractor_symbolic_verifier"] = dict(skipped)
        modes["llm_only_baseline"] = dict(skipped)
        modes["schema_aware_llm_only_baseline"] = dict(skipped)

    return {
        "input": DEMO_INPUT,
        "modes": modes,
        "evaluation_goal": "Compare task success under token budget, not token usage alone.",
        "task_success_definition": [
            "correct deterministic rule extraction",
            "correct candidate rule holding",
            "correct non-executable rejection",
            "no schema hallucination",
            "complete trace",
        ],
        "efficiency_metric": "task_success_score / total_tokens",
        "main_safety_metric": "deterministic over-promotion rate",
        "principle": "Neural proposes; symbolic verifies and executes.",
    }


def main() -> None:
    result = run_eval()
    output_path = OUTPUT_DIR / "eval_modes.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    for mode, summary in result["modes"].items():
        print(f"{mode}: {summary['status']}")


if __name__ == "__main__":
    main()
