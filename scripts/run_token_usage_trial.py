"""汇总 token 消耗测试证据。

默认只读取既有 evaluation artifacts 和 token usage log，不调用 LLM，也不覆盖
正式 tracked evidence。需要 live LLM 测试时，按输出里的 command matrix 手动运行。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


EVAL_DIR = Path("outputs/eval")
DEFAULT_OUTPUT_PATH = EVAL_DIR / "token_usage_trial_latest.json"
TOKEN_LOG_PATH = EVAL_DIR / "deepseek_token_usage.jsonl"


def summarize_token_log(records: list[dict[str, Any]]) -> dict[str, Any]:
    """按 mode 汇总 LLM usage records。"""

    if not records:
        return {
            "status": "empty",
            "total_calls": 0,
            "total_tokens": 0,
            "by_mode": {},
        }

    by_mode: dict[str, dict[str, Any]] = {}
    for record in records:
        mode = str(record.get("mode") or "unknown")
        entry = by_mode.setdefault(
            mode,
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "min_total_tokens": None,
                "max_total_tokens": None,
            },
        )
        prompt_tokens = _int_value(record.get("prompt_tokens"))
        completion_tokens = _int_value(record.get("completion_tokens"))
        total_tokens = _int_value(record.get("total_tokens"))
        entry["calls"] += 1
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
        entry["total_tokens"] += total_tokens
        entry["min_total_tokens"] = (
            total_tokens
            if entry["min_total_tokens"] is None
            else min(entry["min_total_tokens"], total_tokens)
        )
        entry["max_total_tokens"] = (
            total_tokens
            if entry["max_total_tokens"] is None
            else max(entry["max_total_tokens"], total_tokens)
        )

    for entry in by_mode.values():
        calls = int(entry["calls"])
        entry["average_total_tokens"] = (
            entry["total_tokens"] / calls if calls else 0
        )

    return {
        "status": "ok",
        "total_calls": sum(entry["calls"] for entry in by_mode.values()),
        "total_tokens": sum(entry["total_tokens"] for entry in by_mode.values()),
        "by_mode": dict(sorted(by_mode.items())),
    }


def build_artifact_summary(root: Path = ROOT_DIR) -> dict[str, Any]:
    """从既有输出文件抽取 token 测试需要的关键字段。"""

    eval_dir = root / EVAL_DIR
    return {
        "pipeline_token_budget": _pipeline_token_budget_summary(
            eval_dir / "pipeline_token_budget.json",
            root=root,
        ),
        "eval_modes": _eval_modes_summary(eval_dir / "eval_modes.json", root=root),
        "fuzzy_eval_results": _fuzzy_summary(
            eval_dir / "fuzzy_eval_results.json",
            root=root,
        ),
        "fuzzy_deepseek_extractor_results": _fuzzy_summary(
            eval_dir / "fuzzy_deepseek_extractor_results.json",
            root=root,
        ),
        "token_usage_log": _token_log_summary(
            eval_dir / "deepseek_token_usage.jsonl",
            root=root,
        ),
    }


def build_trial_report(root: Path = ROOT_DIR) -> dict[str, Any]:
    """生成一次 token trial 的可读汇总。"""

    return {
        "schema_version": "token_usage_trial.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "artifact_summary",
        "notes": [
            "默认报告只汇总既有 artifact，不调用 LLM。",
            "live LLM 测试会消耗 provider token，应显式设置 ENABLE_LLM=true 后手动运行。",
            "不要提交 quick 或 trial 输出，除非要把它提升为正式 evidence。",
        ],
        "artifact_summary": build_artifact_summary(root),
        "command_matrix": _command_matrix(),
    }


def write_trial_report(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    report = build_trial_report(root)
    target = output_path if output_path.is_absolute() else root / output_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _pipeline_token_budget_summary(path: Path, *, root: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload is None:
        return _missing(path, root=root)
    full_excel = payload.get("naive_direct_llm_full_excel") or {}
    required = payload.get("naive_direct_llm_required_columns") or {}
    return {
        "status": "ok",
        "path": _display_path(path, root),
        "naive_full_excel_input_tokens": full_excel.get("estimated_input_tokens"),
        "naive_required_columns_input_tokens": required.get(
            "estimated_input_tokens"
        ),
        "full_excel_fits_128k": full_excel.get("fits_128000_token_budget"),
        "required_columns_fits_128k": required.get("fits_128000_token_budget"),
    }


def _eval_modes_summary(path: Path, *, root: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload is None:
        return _missing(path, root=root)
    modes = payload.get("modes") or {}
    return {
        "status": "ok",
        "path": _display_path(path, root),
        "modes": {
            mode: {
                "status": summary.get("status"),
                "result_count": summary.get("result_count"),
                "total_tokens": summary.get("total_tokens"),
                "task_success": summary.get("task_success"),
                "trace_complete": summary.get("trace_complete"),
            }
            for mode, summary in modes.items()
            if isinstance(summary, dict)
        },
    }


def _fuzzy_summary(path: Path, *, root: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload is None:
        return _missing(path, root=root)
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        return {
            "status": "missing_aggregate",
            "path": _display_path(path, root),
        }
    return {
        "status": "ok",
        "path": _display_path(path, root),
        "selected_methods": payload.get("selected_methods"),
        "aggregate": {
            method: {
                "score": summary.get("score"),
                "max": summary.get("max"),
                "tokens": summary.get("tokens"),
                "cases": summary.get("cases"),
                "skipped": summary.get("skipped"),
                "success_rate": summary.get("success_rate"),
                "deterministic_over_promotion_rate": summary.get(
                    "deterministic_over_promotion_rate"
                ),
            }
            for method, summary in aggregate.items()
            if isinstance(summary, dict)
        },
    }


def _token_log_summary(path: Path, *, root: Path) -> dict[str, Any]:
    if not path.exists():
        return _missing(path, root=root)
    records = _read_usage_jsonl(path)
    summary = summarize_token_log(records)
    summary["path"] = _display_path(path, root)
    return summary


def _read_usage_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _missing(path: Path, *, root: Path) -> dict[str, Any]:
    return {
        "status": "missing",
        "path": _display_path(path, root),
    }


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _command_matrix() -> list[dict[str, Any]]:
    return [
        {
            "name": "汇总当前 token 证据",
            "live_llm": False,
            "command": ".venv/bin/python scripts/run_token_usage_trial.py",
            "output": str(DEFAULT_OUTPUT_PATH),
        },
        {
            "name": "重算直接塞 Excel 的 token 预算估算",
            "live_llm": False,
            "command": ".venv/bin/python scripts/eval_pipeline_token_budget.py",
            "output": "outputs/eval/pipeline_token_budget.json",
        },
        {
            "name": "单条 MVP live token 对比",
            "live_llm": True,
            "command": "ENABLE_LLM=true .venv/bin/python scripts/eval_modes.py",
            "output": "outputs/eval/eval_modes.json",
        },
        {
            "name": "40 条模糊输入 DeepSeek extractor token",
            "live_llm": True,
            "command": (
                "ENABLE_LLM=true .venv/bin/python scripts/eval_fuzzy_inputs.py "
                "--quick --output-path outputs/eval/fuzzy_quick_deepseek_token_live.json"
            ),
            "output": "outputs/eval/fuzzy_quick_deepseek_token_live.json",
        },
        {
            "name": "40 条模糊输入完整 baseline token",
            "live_llm": True,
            "command": (
                "ENABLE_LLM=true .venv/bin/python scripts/eval_fuzzy_inputs.py "
                "--methods all --output-path outputs/eval/fuzzy_quick_all_token_live.json"
            ),
            "output": "outputs/eval/fuzzy_quick_all_token_live.json",
        },
        {
            "name": "Workbench slot adapter live smoke",
            "live_llm": True,
            "command": "ENABLE_LLM=true .venv/bin/python scripts/run_deepseek_slot_probe.py",
            "output": "stdout",
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="汇总 token 消耗测试证据，不默认调用 LLM。"
    )
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="同时把 summary JSON 输出到 stdout。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = write_trial_report(output_path=args.output_path, root=args.root)
    target = args.output_path if args.output_path.is_absolute() else args.root / args.output_path
    print(f"Wrote {target}")
    if args.stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
