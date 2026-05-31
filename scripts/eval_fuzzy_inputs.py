"""Evaluate fuzzy inputs across extractor/baseline methods.

This benchmark compares task success on preference extraction and safety
guardrails. It does not execute dataset queries, because many fuzzy inputs omit
required executable fields by design.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.eval_modes import append_usage
from src.baselines.llm_only_baseline import LLMOnlyBaseline, SchemaAwareLLMOnlyBaseline
from src.evaluation.scoring import (
    finalize_aggregate,
    score_extractor_case,
    score_llm_only_case,
    unsafe_baseline_flags,
    with_efficiency,
)
from src.extractors.deepseek_extractor import DeepSeekExtractor
from src.extractors.regex_extractor import RegexExtractor
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


INPUT_PATH = Path("eval_inputs.jsonl")
OUTPUT_DIR = Path("outputs/eval")
OUTPUT_PATH = OUTPUT_DIR / "fuzzy_eval_results.json"
SCHEMA_PATH = Path("schemas/schema_registry.json")
AVAILABLE_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]


def load_cases(path: Path = INPUT_PATH) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    has_key = bool(os.getenv("DEEPSEEK_API_KEY"))

    results: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, Any]] = {
        "rule_regex_extractor_symbolic_verifier": {
            "score": 0,
            "max": 0,
            "tokens": 0,
            "cases": 0,
            "over_promotion_events": 0,
        },
        "deepseek_extractor_symbolic_verifier": {
            "score": 0,
            "max": 0,
            "tokens": 0,
            "cases": 0,
            "skipped": 0,
            "over_promotion_events": 0,
        },
        "llm_only_baseline": {
            "score": 0,
            "max": 0,
            "tokens": 0,
            "cases": 0,
            "skipped": 0,
            "over_promotion_events": 0,
        },
        "schema_aware_llm_only_baseline": {
            "score": 0,
            "max": 0,
            "tokens": 0,
            "cases": 0,
            "skipped": 0,
            "over_promotion_events": 0,
        },
    }
    schema_fields = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS).configured_fields
    schema_registry = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS)
    attribute_grounder = AttributeGrounder(schema_registry)

    for case in cases:
        row: dict[str, Any] = {"id": case["id"], "input": case["input"], "methods": {}}

        regex_slots = RegexExtractor().extract(case["input"])
        regex_grounding = attribute_grounder.ground(regex_slots)
        regex_score = with_efficiency(score_extractor_case(regex_slots, case, regex_grounding), total_tokens=0)
        regex_score["extracted_slots"] = regex_slots
        regex_score["attribute_grounding"] = regex_grounding
        row["methods"]["rule_regex_extractor_symbolic_verifier"] = regex_score
        aggregate["rule_regex_extractor_symbolic_verifier"]["score"] += regex_score["task_success_score"]
        aggregate["rule_regex_extractor_symbolic_verifier"]["max"] += regex_score["max_score"]
        aggregate["rule_regex_extractor_symbolic_verifier"]["cases"] += 1

        if has_key:
            deepseek_slots = DeepSeekExtractor().extract(case["input"])
            deepseek_grounding = attribute_grounder.ground(deepseek_slots)
            usage = deepseek_slots.get("deepseek_usage", {})
            append_usage("fuzzy_deepseek_extractor_symbolic_verifier", usage)
            deepseek_score = with_efficiency(
                score_extractor_case(deepseek_slots, case, deepseek_grounding),
                total_tokens=usage.get("total_tokens", 0),
            )
            deepseek_score["extracted_slots"] = deepseek_slots
            deepseek_score["attribute_grounding"] = deepseek_grounding
            row["methods"]["deepseek_extractor_symbolic_verifier"] = deepseek_score
            aggregate["deepseek_extractor_symbolic_verifier"]["score"] += deepseek_score["task_success_score"]
            aggregate["deepseek_extractor_symbolic_verifier"]["max"] += deepseek_score["max_score"]
            aggregate["deepseek_extractor_symbolic_verifier"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["deepseek_extractor_symbolic_verifier"]["cases"] += 1

            baseline_payload = LLMOnlyBaseline().propose(case["input"])
            usage = baseline_payload.get("deepseek_usage", {})
            append_usage("fuzzy_llm_only_baseline", usage)
            baseline_score = with_efficiency(
                score_llm_only_case(baseline_payload, case),
                total_tokens=usage.get("total_tokens", 0),
            )
            baseline_score["unsafe_flags"] = unsafe_baseline_flags(baseline_payload)
            baseline_score["raw_output"] = baseline_payload
            row["methods"]["llm_only_baseline"] = baseline_score
            if any(baseline_score["unsafe_flags"].values()):
                aggregate["llm_only_baseline"]["over_promotion_events"] += 1
            aggregate["llm_only_baseline"]["score"] += baseline_score["task_success_score"]
            aggregate["llm_only_baseline"]["max"] += baseline_score["max_score"]
            aggregate["llm_only_baseline"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["llm_only_baseline"]["cases"] += 1

            schema_aware_payload = SchemaAwareLLMOnlyBaseline(schema_fields).propose(case["input"])
            usage = schema_aware_payload.get("deepseek_usage", {})
            append_usage("fuzzy_schema_aware_llm_only_baseline", usage)
            schema_aware_score = with_efficiency(
                score_llm_only_case(schema_aware_payload, case),
                total_tokens=usage.get("total_tokens", 0),
            )
            schema_aware_score["unsafe_flags"] = unsafe_baseline_flags(schema_aware_payload)
            schema_aware_score["raw_output"] = schema_aware_payload
            row["methods"]["schema_aware_llm_only_baseline"] = schema_aware_score
            if any(schema_aware_score["unsafe_flags"].values()):
                aggregate["schema_aware_llm_only_baseline"]["over_promotion_events"] += 1
            aggregate["schema_aware_llm_only_baseline"]["score"] += schema_aware_score["task_success_score"]
            aggregate["schema_aware_llm_only_baseline"]["max"] += schema_aware_score["max_score"]
            aggregate["schema_aware_llm_only_baseline"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["schema_aware_llm_only_baseline"]["cases"] += 1
        else:
            skipped = {"status": "skipped", "reason": "DEEPSEEK_API_KEY is not set."}
            row["methods"]["deepseek_extractor_symbolic_verifier"] = skipped
            row["methods"]["llm_only_baseline"] = skipped
            row["methods"]["schema_aware_llm_only_baseline"] = skipped
            aggregate["deepseek_extractor_symbolic_verifier"]["skipped"] += 1
            aggregate["llm_only_baseline"]["skipped"] += 1
            aggregate["schema_aware_llm_only_baseline"]["skipped"] += 1

        results.append(row)

    finalize_aggregate(aggregate)

    return {
        "evaluation_goal": "Compare task success under token budget on fuzzier inputs.",
        "main_safety_metric": "deterministic over-promotion rate",
        "methods": [
            "rule_regex_extractor_symbolic_verifier",
            "deepseek_extractor_symbolic_verifier",
            "llm_only_baseline",
            "schema_aware_llm_only_baseline",
        ],
        "aggregate": aggregate,
        "cases": results,
    }


def main() -> None:
    result = evaluate()
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    for method, summary in result["aggregate"].items():
        print(method, "score", summary["score"], "/", summary["max"], "tokens", summary["tokens"])


if __name__ == "__main__":
    main()
