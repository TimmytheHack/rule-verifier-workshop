"""Evaluate fuzzy inputs across extractor/baseline methods.

This benchmark compares task success on preference extraction and safety
guardrails. It does not execute dataset queries, because many fuzzy inputs omit
required executable fields by design.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

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
from src.extractors.deepseek_extractor import (
    DEFAULT_MODEL,
    DeepSeekExtractor,
    env_value,
    has_deepseek_api_key,
)
from src.extractors.regex_extractor import RegexExtractor
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


INPUT_PATH = Path("eval_inputs.jsonl")
OUTPUT_DIR = Path("outputs/eval")
OUTPUT_PATH = OUTPUT_DIR / "fuzzy_eval_results.json"
CACHE_PATH = OUTPUT_DIR / "deepseek_fuzzy_cache.json"
SCHEMA_PATH = Path("schemas/schema_registry.json")
AVAILABLE_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]
METHOD_ALIASES = {
    "all": {"regex", "deepseek", "llm_only", "schema_aware"},
    "baselines": {"llm_only", "schema_aware"},
    "deepseek": {"deepseek"},
    "regex": {"regex"},
    "llm_only": {"llm_only"},
    "schema_aware": {"schema_aware"},
}


def load_cases(path: Path = INPUT_PATH) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class JsonCache:
    """Small JSON cache so long API-backed evals can resume after interruption."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        if enabled and path.exists():
            self.payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.payload = {"records": {}}

    def get_or_compute(
        self,
        key: str,
        compute: Callable[[], dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        records = self.payload["records"]
        if self.enabled and key in records:
            return records[key], True
        value = compute()
        if self.enabled:
            records[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return value, False


def parse_methods(raw: str) -> set[str]:
    methods: set[str] = set()
    for item in raw.split(","):
        key = item.strip()
        if not key:
            continue
        if key not in METHOD_ALIASES:
            allowed = ", ".join(sorted(METHOD_ALIASES))
            raise ValueError(f"未知评估方法“{key}”。允许的取值：{allowed}")
        methods.update(METHOD_ALIASES[key])
    return methods or METHOD_ALIASES["all"]


def select_cases(
    cases: list[dict[str, Any]],
    case_ids: set[str] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
    if limit is not None:
        cases = cases[:limit]
    return cases


def cache_key(method: str, case: dict[str, Any]) -> str:
    model = env_value("DEEPSEEK_MODEL") or DEFAULT_MODEL
    return json.dumps(
        {
            "version": 2,
            "method": method,
            "model": model,
            "case_id": case["id"],
            "input": case["input"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def evaluate(
    methods: set[str] | None = None,
    limit: int | None = None,
    case_ids: set[str] | None = None,
    cache_path: Path = CACHE_PATH,
    use_cache: bool = True,
    progress: bool = True,
) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = select_cases(load_cases(), case_ids=case_ids, limit=limit)
    selected_methods = methods or METHOD_ALIASES["all"]
    has_key = has_deepseek_api_key()
    cache = JsonCache(cache_path, enabled=use_cache)

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

    for index, case in enumerate(cases, start=1):
        if progress:
            print(f"[{index}/{len(cases)}] {case['id']}: {case['input']}", flush=True)
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

        if has_key and "deepseek" in selected_methods:
            deepseek_slots, cache_hit = cache.get_or_compute(
                cache_key("deepseek_extractor_symbolic_verifier", case),
                lambda: DeepSeekExtractor().extract(case["input"]),
            )
            deepseek_grounding = attribute_grounder.ground(deepseek_slots)
            usage = deepseek_slots.get("deepseek_usage", {})
            if not cache_hit:
                append_usage("fuzzy_deepseek_extractor_symbolic_verifier", usage)
            deepseek_score = with_efficiency(
                score_extractor_case(deepseek_slots, case, deepseek_grounding),
                total_tokens=usage.get("total_tokens", 0),
            )
            deepseek_score["cache_hit"] = cache_hit
            deepseek_score["extracted_slots"] = deepseek_slots
            deepseek_score["attribute_grounding"] = deepseek_grounding
            row["methods"]["deepseek_extractor_symbolic_verifier"] = deepseek_score
            aggregate["deepseek_extractor_symbolic_verifier"]["score"] += deepseek_score["task_success_score"]
            aggregate["deepseek_extractor_symbolic_verifier"]["max"] += deepseek_score["max_score"]
            aggregate["deepseek_extractor_symbolic_verifier"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["deepseek_extractor_symbolic_verifier"]["cases"] += 1
            if progress:
                status = "cache" if cache_hit else "api"
                print(f"  deepseek_extractor_symbolic_verifier: {status}", flush=True)
        else:
            reason = "未选择该方法" if "deepseek" not in selected_methods else "未配置 DeepSeek 密钥（环境变量 DEEPSEEK_API_KEY）"
            row["methods"]["deepseek_extractor_symbolic_verifier"] = {"status": "skipped", "reason": reason}
            aggregate["deepseek_extractor_symbolic_verifier"]["skipped"] += 1

        if has_key and "llm_only" in selected_methods:
            baseline_payload, cache_hit = cache.get_or_compute(
                cache_key("llm_only_baseline", case),
                lambda: LLMOnlyBaseline().propose(case["input"]),
            )
            usage = baseline_payload.get("deepseek_usage", {})
            if not cache_hit:
                append_usage("fuzzy_llm_only_baseline", usage)
            baseline_score = with_efficiency(
                score_llm_only_case(baseline_payload, case),
                total_tokens=usage.get("total_tokens", 0),
            )
            baseline_score["cache_hit"] = cache_hit
            baseline_score["unsafe_flags"] = unsafe_baseline_flags(baseline_payload)
            baseline_score["raw_output"] = baseline_payload
            row["methods"]["llm_only_baseline"] = baseline_score
            if any(baseline_score["unsafe_flags"].values()):
                aggregate["llm_only_baseline"]["over_promotion_events"] += 1
            aggregate["llm_only_baseline"]["score"] += baseline_score["task_success_score"]
            aggregate["llm_only_baseline"]["max"] += baseline_score["max_score"]
            aggregate["llm_only_baseline"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["llm_only_baseline"]["cases"] += 1
            if progress:
                status = "cache" if cache_hit else "api"
                print(f"  llm_only_baseline: {status}", flush=True)
        else:
            reason = "未选择该方法" if "llm_only" not in selected_methods else "未配置 DeepSeek 密钥（环境变量 DEEPSEEK_API_KEY）"
            row["methods"]["llm_only_baseline"] = {"status": "skipped", "reason": reason}
            aggregate["llm_only_baseline"]["skipped"] += 1

        if has_key and "schema_aware" in selected_methods:
            schema_aware_payload, cache_hit = cache.get_or_compute(
                cache_key("schema_aware_llm_only_baseline", case),
                lambda: SchemaAwareLLMOnlyBaseline(schema_fields).propose(case["input"]),
            )
            usage = schema_aware_payload.get("deepseek_usage", {})
            if not cache_hit:
                append_usage("fuzzy_schema_aware_llm_only_baseline", usage)
            schema_aware_score = with_efficiency(
                score_llm_only_case(schema_aware_payload, case),
                total_tokens=usage.get("total_tokens", 0),
            )
            schema_aware_score["cache_hit"] = cache_hit
            schema_aware_score["unsafe_flags"] = unsafe_baseline_flags(schema_aware_payload)
            schema_aware_score["raw_output"] = schema_aware_payload
            row["methods"]["schema_aware_llm_only_baseline"] = schema_aware_score
            if any(schema_aware_score["unsafe_flags"].values()):
                aggregate["schema_aware_llm_only_baseline"]["over_promotion_events"] += 1
            aggregate["schema_aware_llm_only_baseline"]["score"] += schema_aware_score["task_success_score"]
            aggregate["schema_aware_llm_only_baseline"]["max"] += schema_aware_score["max_score"]
            aggregate["schema_aware_llm_only_baseline"]["tokens"] += usage.get("total_tokens", 0)
            aggregate["schema_aware_llm_only_baseline"]["cases"] += 1
            if progress:
                status = "cache" if cache_hit else "api"
                print(f"  schema_aware_llm_only_baseline: {status}", flush=True)
        else:
            reason = "未选择该方法" if "schema_aware" not in selected_methods else "未配置 DeepSeek 密钥（环境变量 DEEPSEEK_API_KEY）"
            row["methods"]["schema_aware_llm_only_baseline"] = {"status": "skipped", "reason": reason}
            aggregate["schema_aware_llm_only_baseline"]["skipped"] += 1

        results.append(row)

    finalize_aggregate(aggregate)

    return {
        "evaluation_goal": "比较更模糊输入下不同方法的任务成功率和 token 预算。",
        "main_safety_metric": "确定性规则过度提升率",
        "methods": [
            "rule_regex_extractor_symbolic_verifier",
            "deepseek_extractor_symbolic_verifier",
            "llm_only_baseline",
            "schema_aware_llm_only_baseline",
        ],
        "aggregate": aggregate,
        "cases": results,
        "selected_methods": sorted(selected_methods),
        "cache_path": str(cache_path) if use_cache else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate fuzzy preference inputs.")
    parser.add_argument(
        "--methods",
        default="all",
        help=(
            "Comma-separated methods: all, regex, deepseek, llm_only, "
            "schema_aware, baselines. Use regex,deepseek for a faster extractor run."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Shortcut for --methods regex,deepseek.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N selected cases.")
    parser.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="Evaluate one case id. Can be supplied multiple times.",
    )
    parser.add_argument("--cache-path", type=Path, default=CACHE_PATH)
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--no-cache", action="store_true", help="Disable API response cache.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case progress output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    methods = parse_methods("regex,deepseek" if args.quick else args.methods)
    result = evaluate(
        methods=methods,
        limit=args.limit,
        case_ids=set(args.case_id) if args.case_id else None,
        cache_path=args.cache_path,
        use_cache=not args.no_cache,
        progress=not args.quiet,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output_path}")
    for method, summary in result["aggregate"].items():
        print(method, "score", summary["score"], "/", summary["max"], "tokens", summary["tokens"])


if __name__ == "__main__":
    main()
