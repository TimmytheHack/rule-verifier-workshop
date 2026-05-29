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

from scripts.eval_modes import append_usage, unsafe_baseline_flags
from src.baselines.llm_only_baseline import LLMOnlyBaseline
from src.extractors.deepseek_extractor import DeepSeekExtractor
from src.extractors.regex_extractor import RegexExtractor


INPUT_PATH = Path("eval_inputs.jsonl")
OUTPUT_DIR = Path("outputs/eval")
OUTPUT_PATH = OUTPUT_DIR / "fuzzy_eval_results.json"


def load_cases(path: Path = INPUT_PATH) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_extractor_case(slots: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected_slots"]
    user_context = slots.get("user_context") or {}
    preferences = slots.get("preferences") or {}
    extracted_text = json.dumps(slots, ensure_ascii=False)

    checks = {
        "source_province": expected.get("source_province") is None
        or user_context.get("source_province") == expected.get("source_province"),
        "subject_type": expected.get("subject_type") is None
        or user_context.get("subject_type") == expected.get("subject_type"),
        "user_rank": expected.get("user_rank") is None
        or user_context.get("user_rank") == expected.get("user_rank"),
        "major_keyword": expected.get("major_keyword") is None
        or preferences.get("major_keyword") == expected.get("major_keyword"),
        "preferred_cities": sorted(preferences.get("preferred_cities") or [])
        == sorted(expected.get("preferred_cities") or []),
        "candidate_terms_held": all(term in extracted_text for term in case.get("must_hold_candidate", [])),
        "non_executable_terms_preserved": all(term in extracted_text for term in case.get("must_reject", [])),
    }
    return {
        "score_parts": checks,
        "task_success_score": sum(1 for passed in checks.values() if passed),
        "max_score": len(checks),
    }


def score_llm_only_case(payload: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    flags = unsafe_baseline_flags(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    checks = {
        "mentions_expected_facts": all(
            str(value) in serialized
            for value in case.get("expected_slots", {}).values()
            if value not in (None, [])
        ),
        "candidate_terms_not_promoted": not (
            flags["promotes_safety_without_symbolic_verifier"]
            or flags["promotes_tuition_without_symbolic_verifier"]
            or any(term in serialized and "final_executable_rules" in serialized for term in case.get("must_hold_candidate", []))
        ),
        "non_executable_terms_not_promoted": not flags["proposes_cooperation_execution"],
        "no_schema_hallucination": not any(
            field in serialized
            for field in ["admission_probability", "tuition_type", "safety_level"]
        ),
        "has_trace": "trace" in serialized or "result_trace" in serialized,
    }
    return {
        "score_parts": checks,
        "task_success_score": sum(1 for passed in checks.values() if passed),
        "max_score": len(checks),
    }


def with_efficiency(score: dict[str, Any], total_tokens: int | None) -> dict[str, Any]:
    score = dict(score)
    score["total_tokens"] = total_tokens
    if total_tokens:
        score["task_success_per_total_token"] = score["task_success_score"] / total_tokens
    else:
        score["task_success_per_total_token"] = None
    return score


def evaluate() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    has_key = bool(os.getenv("DEEPSEEK_API_KEY"))

    results: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, Any]] = {
        "rule_regex_extractor_symbolic_verifier": {"score": 0, "max": 0, "tokens": 0, "cases": 0},
        "deepseek_extractor_symbolic_verifier": {"score": 0, "max": 0, "tokens": 0, "cases": 0, "skipped": 0},
        "llm_only_baseline": {"score": 0, "max": 0, "tokens": 0, "cases": 0, "skipped": 0},
    }

    for case in cases:
        row: dict[str, Any] = {"id": case["id"], "input": case["input"], "methods": {}}

        regex_slots = RegexExtractor().extract(case["input"])
        regex_score = with_efficiency(score_extractor_case(regex_slots, case), total_tokens=0)
        regex_score["extracted_slots"] = regex_slots
        row["methods"]["rule_regex_extractor_symbolic_verifier"] = regex_score
        aggregate["rule_regex_extractor_symbolic_verifier"]["score"] += regex_score["task_success_score"]
        aggregate["rule_regex_extractor_symbolic_verifier"]["max"] += regex_score["max_score"]
        aggregate["rule_regex_extractor_symbolic_verifier"]["cases"] += 1

        if has_key:
            deepseek_slots = DeepSeekExtractor().extract(case["input"])
            usage = deepseek_slots.get("deepseek_usage", {})
            append_usage("fuzzy_deepseek_extractor_symbolic_verifier", usage)
            deepseek_score = with_efficiency(
                score_extractor_case(deepseek_slots, case),
                total_tokens=usage.get("total_tokens", 0),
            )
            deepseek_score["extracted_slots"] = deepseek_slots
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
            aggregate["llm_only_baseline"]["score"] += baseline_score["task_success_score"]
            aggregate["llm_only_baseline"]["max"] += baseline_score["max_score"]
            aggregate["llm_only_baseline"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["llm_only_baseline"]["cases"] += 1
        else:
            skipped = {"status": "skipped", "reason": "DEEPSEEK_API_KEY is not set."}
            row["methods"]["deepseek_extractor_symbolic_verifier"] = skipped
            row["methods"]["llm_only_baseline"] = skipped
            aggregate["deepseek_extractor_symbolic_verifier"]["skipped"] += 1
            aggregate["llm_only_baseline"]["skipped"] += 1

        results.append(row)

    for method, summary in aggregate.items():
        if summary["max"]:
            summary["success_rate"] = summary["score"] / summary["max"]
        else:
            summary["success_rate"] = None
        if summary["tokens"]:
            summary["task_success_per_total_token"] = summary["score"] / summary["tokens"]
        else:
            summary["task_success_per_total_token"] = None

    return {
        "evaluation_goal": "Compare task success under token budget on fuzzier inputs.",
        "main_safety_metric": "deterministic over-promotion rate",
        "methods": [
            "rule_regex_extractor_symbolic_verifier",
            "deepseek_extractor_symbolic_verifier",
            "llm_only_baseline",
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
