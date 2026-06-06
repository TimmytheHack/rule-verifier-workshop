"""Compare answer generation modes for the MVP verified pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.excel_adapter import ExcelAdapter, ExcelDataSet
from src.evaluation.scoring import score_answer_against_evidence
from src.executors.pandas_executor import PandasExecutor
from src.extractors.deepseek_extractor import has_deepseek_api_key
from src.extractors.regex_extractor import RegexExtractor
from src.reporting.deepseek_answer_generator import (
    DeepSeekAnswerGenerator,
    LLMOnlyAnswerBaseline,
)
from src.reporting.evidence_pack import EvidencePack
from src.reporting.template_report_builder import TemplateReportBuilder
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry
from src.tracing.trace_generator import TraceGenerator


WORKBOOK_NAME = "广东省2025年志愿填报大数据（24-25）0523.xlsx"
OUTPUT_DIR = Path("outputs/answer_demo")
SCHEMA_PATH = Path("schemas/schema_registry.json")
TAXONOMY_PATH = Path("rules/rule_taxonomy.json")

DEMO_INPUT = (
    "我是广东物理类，排位32000，想学计算机，最好在广州深圳，"
    "学校稳一点，不想去太贵的中外合作。"
)
REQUIRED_COLUMNS = [
    "生源地",
    "科类",
    "专业名称",
    "城市",
    "专业组最低位次1",
    "学费",
]


def build_demo_evidence(top_k: int = 5) -> tuple[EvidencePack, SchemaRegistry]:
    dataset = ExcelAdapter(WORKBOOK_NAME, REQUIRED_COLUMNS).load()
    registry = SchemaRegistry.from_file(SCHEMA_PATH, dataset.headers)
    rules_payload = _run_verified_pipeline(dataset, registry)
    evidence = EvidencePack.from_verified_pipeline(
        user_request=DEMO_INPUT,
        executed_rules=rules_payload["final_executable_rules"],
        classified_rules=rules_payload["classified_rules"],
        traced_results=rules_payload["results"],
        top_k=top_k,
    )
    return evidence, registry


def compare_answers(
    evidence: EvidencePack,
    schema_registry: SchemaRegistry,
    include_deepseek: bool = True,
) -> dict[str, Any]:
    evidence_dict = evidence.to_dict()
    comparison = {
        "llm_only_schema_sample": _skipped_answer("DeepSeek not requested."),
        "pipeline_template": _template_answer(evidence_dict),
        "pipeline_deepseek_evidence": _skipped_answer("DeepSeek not requested."),
    }

    if include_deepseek and has_deepseek_api_key():
        comparison["llm_only_schema_sample"] = _deepseek_llm_only_answer(
            evidence=evidence,
            schema_registry=schema_registry,
        )
        comparison["pipeline_deepseek_evidence"] = _deepseek_evidence_answer(evidence)
    elif include_deepseek:
        skipped = _skipped_answer("DEEPSEEK_API_KEY is not set.")
        comparison["llm_only_schema_sample"] = dict(skipped)
        comparison["pipeline_deepseek_evidence"] = dict(skipped)

    return comparison


def run_answer_demo(
    output_dir: Path = OUTPUT_DIR,
    top_k: int = 5,
    include_deepseek: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence, registry = build_demo_evidence(top_k=top_k)
    evidence_dict = evidence.to_dict()
    comparison = compare_answers(
        evidence=evidence,
        schema_registry=registry,
        include_deepseek=include_deepseek,
    )
    output = {
        "input": DEMO_INPUT,
        "answer_goal": "Generate answers from verified evidence, not raw Excel.",
        "comparison": comparison,
        "answer_level_evaluation": {
            mode: payload.get("answer_evaluation")
            for mode, payload in comparison.items()
        },
    }

    (output_dir / "evidence_pack.json").write_text(
        json.dumps(evidence_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "template_answer.md").write_text(
        comparison["pipeline_template"]["answer"],
        encoding="utf-8",
    )
    (output_dir / "answer_comparison.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_optional_answer(
        output_dir,
        "llm_only_answer.md",
        comparison["llm_only_schema_sample"],
    )
    _write_optional_answer(
        output_dir,
        "deepseek_evidence_answer.md",
        comparison["pipeline_deepseek_evidence"],
    )
    return output


def _run_verified_pipeline(
    dataset: ExcelDataSet,
    registry: SchemaRegistry,
) -> dict[str, Any]:
    slots = RegexExtractor().extract(DEMO_INPUT)
    verifier = RuleVerifier(registry)
    classified_rules = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
    final_rules = RulePromoter(
        TAXONOMY_PATH,
        simulated_confirmation_enabled=True,
    ).final_executable_rules(classified_rules)
    raw_results = PandasExecutor().execute(dataset.dataframe, final_rules)
    results = TraceGenerator().add_traces(raw_results)
    return {
        "classified_rules": classified_rules,
        "final_executable_rules": final_rules,
        "results": results,
    }


def _template_answer(evidence_dict: dict[str, Any]) -> dict[str, Any]:
    answer = TemplateReportBuilder().build(evidence_dict)
    return {
        "status": "ok",
        "answer_source": "pipeline_template_from_evidence_pack",
        "answer": answer,
        "answer_evaluation": score_answer_against_evidence(answer, evidence_dict),
        "token_usage": None,
    }


def _deepseek_evidence_answer(evidence: EvidencePack) -> dict[str, Any]:
    evidence_dict = evidence.to_dict()
    try:
        payload = DeepSeekAnswerGenerator().generate(evidence)
    except RuntimeError as exc:
        return _skipped_answer(str(exc))
    answer = payload["answer"]
    return {
        "status": "ok",
        "answer_source": "pipeline_deepseek_from_evidence_pack",
        "answer": answer,
        "answer_evaluation": score_answer_against_evidence(answer, evidence_dict),
        "token_usage": payload.get("deepseek_usage"),
    }


def _deepseek_llm_only_answer(
    evidence: EvidencePack,
    schema_registry: SchemaRegistry,
) -> dict[str, Any]:
    evidence_dict = evidence.to_dict()
    try:
        payload = LLMOnlyAnswerBaseline().generate(
            user_request=evidence.user_request,
            schema_fields=schema_registry.configured_fields,
            sample_results=evidence.top_k_results,
        )
    except RuntimeError as exc:
        return _skipped_answer(str(exc))
    answer = payload["answer"]
    return {
        "status": "ok",
        "answer_source": "llm_only_schema_sample_user_input",
        "answer": answer,
        "answer_evaluation": score_answer_against_evidence(answer, evidence_dict),
        "token_usage": payload.get("deepseek_usage"),
    }


def _skipped_answer(reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
        "answer": "",
        "answer_evaluation": None,
        "token_usage": None,
    }


def _write_optional_answer(output_dir: Path, filename: str, payload: dict[str, Any]) -> None:
    if payload.get("status") != "ok" or not payload.get("answer"):
        return
    (output_dir / filename).write_text(payload["answer"], encoding="utf-8")


def main() -> None:
    result = run_answer_demo()
    print(f"Wrote {OUTPUT_DIR / 'evidence_pack.json'}")
    print(f"Wrote {OUTPUT_DIR / 'template_answer.md'}")
    print(f"Wrote {OUTPUT_DIR / 'answer_comparison.json'}")
    for mode, payload in result["comparison"].items():
        print(f"{mode}: {payload['status']}")


if __name__ == "__main__":
    main()
