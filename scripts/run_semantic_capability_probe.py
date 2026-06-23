"""运行 uploaded admissions 语义能力查询探针。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DEFAULT_QUERY = (
    "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
)


def main(argv: list[str] | None = None) -> int:
    args = _arg_parser().parse_args(argv)
    try:
        exit_code, payload = run_probe(
            workbook_path=Path(args.workbook_path),
            dataset_id=args.dataset_id,
            query=args.query,
            root=Path(args.root),
            live_llm=args.live_llm,
            live_semantic_candidates=args.live_semantic_candidates,
            planner_mode=args.planner_mode,
        )
    except (FileNotFoundError, ValueError) as exc:
        exit_code = 1
        payload = _error_payload(exc)
    print(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2))
    return exit_code


def run_probe(
    *,
    workbook_path: Path,
    dataset_id: str,
    query: str,
    root: Path,
    live_llm: bool = False,
    live_semantic_candidates: bool = False,
    planner_mode: str = "auto",
) -> tuple[int, dict[str, Any]]:
    """复用 DatasetService 跑通上传、审查、建仓和语义查询。"""

    from src.api.dataset_service import DatasetService

    service = DatasetService(root)
    upload = service.upload(
        filename=workbook_path.name,
        content=workbook_path.read_bytes(),
        dataset_id=dataset_id,
    )
    service.generate_domain_pack(
        dataset_id,
        domain_name="admissions",
        base_domain="admissions",
    )
    approve = service.approve_domain(dataset_id)
    if not approve.get("ok"):
        return 2, {
            "status": "approval_failed",
            "upload": upload,
            "approve": approve,
        }

    build = service.build_warehouse(dataset_id)
    profile = service.profile(dataset_id)
    semantic_mapping_candidates = dict(
        profile.get("semantic_mapping_candidates") or {}
    )
    if live_semantic_candidates:
        from scripts.generate_domain_pack import load_source_dataset
        from src.domains import DomainConfig
        from src.semantic.capability_graph import DatasetCapabilityGraph
        from src.semantic.llm_semantic_candidates import (
            DeepSeekSemanticCandidateGenerator,
        )

        metadata = service._load_metadata(dataset_id)
        domain = DomainConfig.from_path(Path(metadata["domain_dir"]), "admissions")
        dataset = load_source_dataset(
            workbook_path,
            sheet_name=metadata.get("sheet_name"),
        )
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        semantic_mapping_candidates["llm"] = {
            "status": "completed",
            **asdict(
                DeepSeekSemanticCandidateGenerator().generate(
                    graph=graph,
                    domain_config=domain,
                )
            ),
        }
    response = service.query(
        dataset_id,
        user_input=query,
        soft_preferences={
            "prompt": query,
            "live_semantic_rerank": live_llm,
        },
        extractor="hybrid" if live_llm else "regex",
        planner_mode=planner_mode,
    )
    evidence = response.get("evidence_pack") or {}
    return 0, {
        "upload": upload,
        "build": build,
        "semantic_mapping_candidates": semantic_mapping_candidates,
        "status": response.get("status"),
        "query_type": response.get("query_type"),
        "planner": evidence.get("planner", {}),
        "semantic_intent": evidence.get("semantic_intent"),
        "token_usage": response.get("token_usage", {}),
        "answer": response.get("answer"),
        "top_results": response.get("top_results", []),
        "evidence_pack": {
            "planner": evidence.get("planner", {}),
            "semantic_intent": evidence.get("semantic_intent"),
            "answerable_intents": evidence.get("answerable_intents", []),
            "unanswerable_intents": evidence.get("unanswerable_intents", []),
            "not_executed_preferences": evidence.get(
                "not_executed_preferences",
                [],
            ),
            "selection_evidence": evidence.get("selection_evidence", []),
            "execution_summary": evidence.get("execution_summary", {}),
        },
    }


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="上传招生表并运行语义能力 QueryAST 探针。",
    )
    parser.add_argument("workbook_path", help="招生 Excel/CSV 路径。")
    parser.add_argument("--dataset-id", default="ds_semantic_probe")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--root", default="outputs/uploaded_datasets")
    parser.add_argument(
        "--planner-mode",
        choices=["auto", "legacy", "llm_semantic"],
        default="auto",
        help=(
            "Workbench semantic planner 模式。auto 对 uploaded dataset "
            "优先尝试 LLM SemanticIntent；legacy 跳过 LLM planner。"
        ),
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help=(
            "启用 Workbench 的可选 DeepSeek rerank 路径；"
            "SemanticIntent planner 由 --planner-mode 控制。"
        ),
    )
    parser.add_argument(
        "--live-semantic-candidates",
        action="store_true",
        help="显式调用 DeepSeek 生成 candidate-only 字段语义候选。",
    )
    return parser


def _error_payload(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "error_type": type(exc).__name__,
        "message": str(exc),
    }
    code = getattr(exc, "code", None)
    if code:
        payload["code"] = code
        payload["status_code"] = getattr(exc, "status_code", 400)
        payload["details"] = getattr(exc, "details", None) or {}
    return payload


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_ready(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
