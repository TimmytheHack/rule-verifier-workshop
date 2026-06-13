"""Display adapter for the frontend workbench.

This module runs the existing verified pipeline and reshapes its artifacts for
the UI. It does not add verifier, promoter, executor, or recommendation logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from scripts.run_mvp_demo import (
    REQUIRED_COLUMNS,
    SCHEMA_PATH,
    TAXONOMY_PATH,
    WORKBOOK_NAME,
)
from src.adapters.data_warehouse import (
    SchemaValueIndex,
    audit_data_warehouse_fingerprints,
    load_structured_dataset,
)
from src.adapters.excel_adapter import ExcelDataSet
from src.executors.duckdb_executor import (
    DuckDBExecutor,
    ExecutionResult,
    hard_filter_rules,
)
from src.extractors.deepseek_extractor import (
    DeepSeekClient,
    DeepSeekExtractor,
    has_deepseek_api_key,
)
from src.extractors.extractor_pipeline import ExtractorFallbackPipeline
from src.extractors.regex_extractor import RegexExtractor
from src.reporting.deepseek_answer_generator import (
    DeepSeekAnswerGenerator,
)
from src.reporting.evidence_pack import EvidencePack
from src.reporting.template_report_builder import TemplateReportBuilder
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry
from src.tracing.trace_generator import TraceGenerator


DEFAULT_USER_INPUT = (
    "我是广东物理类，排位32000，想学计算机，最好在广州深圳，"
    "学校稳一点，不想去太贵的中外合作。"
)

EXTRACTOR_OPTIONS = {
    "hybrid": "规则优先，LLM 补槽",
    "regex": "规则解析软偏好",
    "deepseek": "LLM 辅助解析软偏好",
}

GENERATOR_OPTIONS = {
    "template_evidence": "模板证据回答",
    "deepseek_evidence": "LLM 证据回答",
}

MODEL_OPTIONS = {
    "deepseek-v4-flash": "LLM 快速模型",
    "deepseek-v4-pro": "LLM 高质量模型",
}
INTERACTIVE_DEEPSEEK_TIMEOUT_SECONDS = 25
INTERACTIVE_DEEPSEEK_MAX_RETRIES = 1
EVIDENCE_TOP_K = 5

NOT_EXECUTED_COOPERATION_TEXT = "中外合作未执行：缺少合作办学类型字段"
NOT_EXECUTED_COOPERATION_REASON = (
    "当前数据字段定义没有合作办学类型字段，不能验证或执行"
    "“排除中外合作”。"
)
WAREHOUSE_DATABASE_PATH = Path("outputs/data/guangdong_admissions.duckdb")
WAREHOUSE_VALUE_INDEX_PATH = Path("outputs/data/schema_value_index.json")
PEARL_RIVER_DELTA_CITIES = [
    "广州",
    "深圳",
    "佛山",
    "东莞",
    "珠海",
    "惠州",
    "中山",
    "江门",
    "肇庆",
]
COMPUTER_RELATED_CONFIRMATION_TERMS = [
    "计算机",
    "软件工程",
    "人工智能",
    "数据科学",
    "网络空间安全",
]


@dataclass(frozen=True)
class WorkbenchConfig:
    """Validated frontend workbench run options."""

    user_input: str = DEFAULT_USER_INPUT
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    extractor: str = "hybrid"
    generator: str = "template_evidence"
    model: str = "deepseek-v4-flash"
    confirmed_candidates: list[str] = field(default_factory=list)


def available_options() -> dict[str, Any]:
    """Return the user-facing option whitelist for API mode."""

    return {
        "extractors": _options(EXTRACTOR_OPTIONS),
        "generators": _options(GENERATOR_OPTIONS),
        "models": _options(MODEL_OPTIONS),
    }


def run_workbench(config: WorkbenchConfig) -> dict[str, Any]:
    """Run the verified pipeline and return UI-ready artifacts."""

    _validate_config(config)
    warehouse_audit = _data_warehouse_audit()
    if not warehouse_audit["ok"]:
        return _data_warehouse_warning_payload(config, warehouse_audit)

    dataset = _load_dataset()
    schema_registry = _load_schema_registry(tuple(dataset.headers))
    value_index = _load_value_index()
    slots, extractor_usage = _extract_slots(config, schema_registry=schema_registry)
    verifier = RuleVerifier(schema_registry)
    attribute_grounding = AttributeGrounder(
        schema_registry,
        value_index=value_index,
    ).ground(slots)
    confirmation_candidates = _build_confirmation_candidates(
        user_request=_compose_user_request(config),
        attribute_grounding=attribute_grounding,
    )
    confirmation_state = _resolve_confirmed_candidates(
        confirmed_candidates=config.confirmed_candidates,
        confirmation_candidates=confirmation_candidates,
        verifier=verifier,
    )
    proposed_rules = verifier.audit_proposed_rules(slots.get("proposed_rules", []))
    classified_rules = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
    classified_rules = _append_unmapped_preferences(classified_rules, slots)
    classified_rules = _append_grounding_non_executable_preferences(
        classified_rules,
        attribute_grounding,
    )
    classified_rules["attribute_grounding"] = attribute_grounding
    classified_rules["proposed_rules"] = proposed_rules
    classified_rules["confirmation_state"] = confirmation_state
    classified_rules = _apply_soft_confirmations(classified_rules, config, slots)
    final_rules = RulePromoter(
        TAXONOMY_PATH,
        simulated_confirmation_enabled=True,
    ).final_executable_rules(classified_rules)
    final_rules.extend(confirmation_state["confirmed_rules"])
    final_rules = _apply_value_index_hard_filter_guard(
        final_rules,
        attribute_grounding,
    )
    hard_rules, _ = hard_filter_rules(final_rules)
    execution = _execute_verified_hard_rules(
        executable_rules=final_rules,
        user_rank=slots.get("user_context", {}).get("user_rank"),
        top_k=EVIDENCE_TOP_K,
    )
    confirmation_state = _finalize_confirmation_execution(
        confirmation_state,
        execution.audit.to_dict(),
    )
    classified_rules["confirmation_state"] = confirmation_state
    traced_results = TraceGenerator().add_traces(
        execution.rows,
        executable_rules=hard_rules,
        not_executed_preferences=classified_rules.get("non_executable_preferences", []),
    )
    extracted_preferences = _extracted_preferences(slots)
    evidence = EvidencePack.from_verified_pipeline(
        user_request=_compose_user_request(config),
        executed_rules=hard_rules,
        classified_rules=classified_rules,
        traced_results=traced_results,
        top_k=EVIDENCE_TOP_K,
        extracted_preferences=extracted_preferences,
        attribute_grounding=attribute_grounding,
        proposed_rules=proposed_rules,
        execution_summary=execution.audit.to_dict(),
        confirmation_state=confirmation_state,
    )
    report, generator_usage = _generate_report(
        config=config,
        evidence=evidence,
        schema_registry=schema_registry,
    )

    return {
        "mode": "api",
        "status": "ok",
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "hard_filters": _display_hard_filters(config.hard_filters),
        "soft_preferences": _display_soft_preferences(config.soft_preferences),
        "selected_options": {
            "extractor": EXTRACTOR_OPTIONS[config.extractor],
            "generator": GENERATOR_OPTIONS[config.generator],
            "model": MODEL_OPTIONS[config.model],
        },
        "extracted_preferences": extracted_preferences,
        "extracted_slots": slots,
        "attribute_grounding": _display_attribute_grounding(attribute_grounding),
        "confirmation_candidates": confirmation_candidates,
        "confirmation_state": _display_confirmation_state(confirmation_state),
        "proposed_rules": _display_proposed_rules(proposed_rules),
        "deterministic_rules": [_display_rule(rule) for rule in classified_rules["deterministic_rules"]],
        "candidate_rules": _candidate_rules(classified_rules),
        "not_executed_preferences": _not_executed_preferences(classified_rules),
        "simulated_confirmations": _simulated_confirmations(classified_rules),
        "executable_rules": [_executable_rule(rule) for rule in hard_rules],
        "execution": _display_execution_summary(execution.audit.to_dict()),
        "result_count": len(traced_results),
        "top_results": [
            _top_result(rank, row)
            for rank, row in enumerate(traced_results[:EVIDENCE_TOP_K], start=1)
        ],
        "trace": {},
        "evidence_pack": evidence.to_dict(),
        "natural_language_report": _with_context_warnings(report, slots),
        "token_usage": {
            "extractor": extractor_usage,
            "generator": generator_usage,
            "total": _sum_usage([extractor_usage, generator_usage]),
        },
}


def _data_warehouse_audit() -> dict[str, Any]:
    return audit_data_warehouse_fingerprints(
        workbook_path=WORKBOOK_NAME,
        database_path=WAREHOUSE_DATABASE_PATH,
        index_path=WAREHOUSE_VALUE_INDEX_PATH,
    )


def _data_warehouse_warning_payload(
    config: WorkbenchConfig,
    warehouse_audit: dict[str, Any],
) -> dict[str, Any]:
    messages = [
        str(warning.get("message"))
        for warning in warehouse_audit.get("warnings", [])
    ]
    full_text = "\n".join(
        ["数据仓库 fingerprint guard 未通过，未执行筛选。"]
        + [f"- {message}" for message in messages]
    )
    return {
        "mode": "api",
        "status": "blocked",
        "warning_type": "data_warehouse_fingerprint_guard",
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "structured_warnings": warehouse_audit.get("warnings", []),
        "warnings": warehouse_audit.get("warnings", []),
        "hard_filters": _display_hard_filters(config.hard_filters),
        "soft_preferences": _display_soft_preferences(config.soft_preferences),
        "selected_options": {
            "extractor": EXTRACTOR_OPTIONS[config.extractor],
            "generator": GENERATOR_OPTIONS[config.generator],
            "model": MODEL_OPTIONS[config.model],
        },
        "extracted_preferences": [],
        "extracted_slots": {},
        "attribute_grounding": {"summary": {}, "attributes": []},
        "proposed_rules": [],
        "deterministic_rules": [],
        "candidate_rules": [],
        "not_executed_preferences": [],
        "simulated_confirmations": {},
        "executable_rules": [],
        "execution": {
            "executor": None,
            "sql": "",
            "params": [],
            "input_row_count": 0,
            "filtered_row_count": 0,
            "sort_key": [],
            "top_k": EVIDENCE_TOP_K,
            "hard_rule_ids": [],
            "skipped_soft_rule_ids": [],
        },
        "result_count": 0,
        "top_results": [],
        "trace": {},
        "evidence_pack": {},
        "natural_language_report": {
            "title": "数据仓库需要重建",
            "summary": "DuckDB、schema/value index 与源 Excel 未通过一致性校验。",
            "full_text": full_text,
            "result_count_text": "当前未执行筛选，结果数为 0。",
            "executed_rules": [],
            "attribute_explanations": [],
            "top_results": [],
            "warnings": messages,
            "disclaimer": "请先重建数据仓库，再运行规则验证。",
        },
        "token_usage": {
            "extractor": None,
            "generator": None,
            "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    }


def _load_dataset() -> ExcelDataSet:
    if not WAREHOUSE_DATABASE_PATH.exists():
        raise RuntimeError("DuckDB 数据仓库不存在，Workbench 不执行静默 Excel 回退。")
    stat = WAREHOUSE_DATABASE_PATH.stat()
    return _load_warehouse_dataset_cached(
        str(WAREHOUSE_DATABASE_PATH),
        stat.st_mtime_ns,
        stat.st_size,
    )


@lru_cache(maxsize=1)
def _load_warehouse_dataset_cached(
    database_path: str,
    modified_ns: int,
    file_size: int,
) -> ExcelDataSet:
    _ = (modified_ns, file_size)
    return load_structured_dataset(database_path, REQUIRED_COLUMNS)


def _execute_verified_hard_rules(
    executable_rules: list[dict[str, Any]],
    user_rank: int | None,
    top_k: int,
) -> ExecutionResult:
    if not WAREHOUSE_DATABASE_PATH.exists():
        raise RuntimeError("DuckDB 数据仓库不存在，Workbench 不执行静默 Pandas 回退。")
    return DuckDBExecutor(WAREHOUSE_DATABASE_PATH).execute(
        executable_rules,
        user_rank=user_rank,
        top_k=top_k,
    )


def _load_schema_registry(headers: tuple[str, ...]) -> SchemaRegistry:
    schema_path = Path(SCHEMA_PATH)
    stat = schema_path.stat()
    return _load_schema_registry_cached(
        str(schema_path),
        stat.st_mtime_ns,
        stat.st_size,
        headers,
    )


@lru_cache(maxsize=4)
def _load_schema_registry_cached(
    schema_path: str,
    modified_ns: int,
    file_size: int,
    headers: tuple[str, ...],
) -> SchemaRegistry:
    _ = (modified_ns, file_size)
    return SchemaRegistry.from_file(Path(schema_path), list(headers))


def _load_value_index() -> SchemaValueIndex | None:
    if not WAREHOUSE_VALUE_INDEX_PATH.exists():
        return None
    stat = WAREHOUSE_VALUE_INDEX_PATH.stat()
    return _load_value_index_cached(
        str(WAREHOUSE_VALUE_INDEX_PATH),
        stat.st_mtime_ns,
        stat.st_size,
    )


@lru_cache(maxsize=1)
def _load_value_index_cached(
    index_path: str,
    modified_ns: int,
    file_size: int,
) -> SchemaValueIndex:
    _ = (modified_ns, file_size)
    return SchemaValueIndex.from_file(index_path)


def _validate_config(config: WorkbenchConfig) -> None:
    if config.extractor not in EXTRACTOR_OPTIONS:
        raise ValueError(f"不支持的规则提取方式：{config.extractor}")
    if config.generator not in GENERATOR_OPTIONS:
        raise ValueError(f"不支持的证据回答方式：{config.generator}")
    if config.model not in MODEL_OPTIONS:
        raise ValueError(f"不支持的 LLM 模型：{config.model}")


def _extract_slots(
    config: WorkbenchConfig,
    schema_registry: SchemaRegistry | None = None,
) -> tuple[dict[str, Any], dict[str, int] | None]:
    soft_prompt = _soft_prompt(config)
    if config.extractor == "regex":
        return _slots_from_inputs(
            RegexExtractor().extract(soft_prompt),
            config=config,
        ), None
    if config.extractor == "hybrid":
        client = (
            _interactive_deepseek_client(config.model)
            if has_deepseek_api_key()
            else None
        )
        slots = _slots_from_inputs(
            ExtractorFallbackPipeline(
                fallback_extractor=(
                    DeepSeekExtractor(client=client) if client is not None else None
                ),
                fallback_enabled=client is not None,
            ).extract(
                soft_prompt,
                schema_context=(
                    schema_registry.field_summary_for_llm()
                    if schema_registry is not None
                    else []
                ),
                hard_context=_display_hard_filters(config.hard_filters),
                boundary_context=_boundary_context(config.soft_preferences),
            ),
            config=config,
        )
        return slots, slots.get("deepseek_usage")

    client = _interactive_deepseek_client(config.model)
    slots = _slots_from_inputs(
        DeepSeekExtractor(client=client).extract(
            soft_prompt,
            schema_context=(
                schema_registry.field_summary_for_llm()
                if schema_registry is not None
                else []
            ),
            hard_context=_display_hard_filters(config.hard_filters),
            boundary_context=_boundary_context(config.soft_preferences),
        ),
        config=config,
    )
    return slots, slots.get("deepseek_usage")


def _generate_report(
    config: WorkbenchConfig,
    evidence: EvidencePack,
    schema_registry: SchemaRegistry,
) -> tuple[dict[str, Any], dict[str, int] | None]:
    evidence_dict = evidence.to_dict()

    if config.generator == "template_evidence":
        answer = TemplateReportBuilder().build(evidence)
        return _report_from_answer(answer, evidence_dict), None

    client = _interactive_deepseek_client(config.model)
    payload = DeepSeekAnswerGenerator(client=client).generate(evidence)
    return (
        _report_from_answer(payload["answer"], evidence_dict),
        payload.get("deepseek_usage"),
    )


def _interactive_deepseek_client(model: str) -> DeepSeekClient:
    return DeepSeekClient(
        model=model,
        timeout_seconds=INTERACTIVE_DEEPSEEK_TIMEOUT_SECONDS,
        max_retries=INTERACTIVE_DEEPSEEK_MAX_RETRIES,
    )


def _soft_prompt(config: WorkbenchConfig) -> str:
    if "prompt" in config.soft_preferences:
        return str(config.soft_preferences.get("prompt") or "").strip()
    return config.user_input


def _slots_from_inputs(
    extracted_slots: dict[str, Any],
    config: WorkbenchConfig,
) -> dict[str, Any]:
    """Merge explicit form fields with extracted soft preferences.

    Explicit hard filters are user-provided structured facts. They still go
    through the normal classifier and verifier before execution.
    """

    slots = dict(extracted_slots)
    slots["input"] = _compose_user_request(config)
    context = dict(slots.get("user_context") or {})
    preferences = dict(slots.get("preferences") or {})
    hard = config.hard_filters
    soft = config.soft_preferences

    context["source_province"] = _clean_text(
        hard.get("source_province"),
    ) or context.get("source_province")
    context["subject_type"] = _clean_text(
        hard.get("subject_type"),
    ) or context.get("subject_type")
    reselected_subjects = _clean_list(hard.get("reselected_subjects"))
    if reselected_subjects:
        context["reselected_subjects"] = reselected_subjects
    context["user_rank"] = _optional_int(hard.get("user_rank")) or context.get("user_rank")

    major_keyword = _clean_text(hard.get("major_keyword"))
    if major_keyword:
        preferences["major_keyword"] = major_keyword
        preferences["major_exact_terms"] = [major_keyword]

    cities = _clean_list(hard.get("preferred_cities"))
    if cities:
        preferences["preferred_cities"] = cities

    hard_tuition_cap = _optional_int(hard.get("tuition_cap_yuan"))
    if hard_tuition_cap:
        preferences["tuition_cap_yuan"] = hard_tuition_cap
        preferences["tuition_preference_raw"] = None

    safety_percent = _optional_int(soft.get("safety_margin_percent"))
    if safety_percent in {5, 10, 15}:
        preferences["risk_preference_raw"] = (
            preferences.get("risk_preference_raw")
            or f"已选择{safety_percent}%位次窗口"
        )

    soft_tuition_cap = _optional_int(soft.get("tuition_cap_yuan"))
    if soft_tuition_cap and not hard_tuition_cap:
        preferences["tuition_preference_raw"] = (
            preferences.get("tuition_preference_raw")
            or f"已选择{soft_tuition_cap}元费用上限"
        )

    slots["user_context"] = context
    slots["preferences"] = preferences
    return slots


def _apply_soft_confirmations(
    classified_rules: dict[str, Any],
    config: WorkbenchConfig,
    slots: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(classified_rules)
    candidate_rule_ids = {
        rule["rule_id"] for rule in updated.get("candidate_rules", [])
    }
    soft = config.soft_preferences
    existing_simulated = updated.get("simulated_confirmations", {})
    simulated: dict[str, Any] = {}
    if "recommendation_rank_floor" in existing_simulated:
        simulated["recommendation_rank_floor"] = existing_simulated[
            "recommendation_rank_floor"
        ]

    safety_percent = _optional_int(soft.get("safety_margin_percent"))
    user_rank = _optional_int(slots.get("user_context", {}).get("user_rank"))
    if safety_percent in {5, 10, 15} and "c_safety_margin" in candidate_rule_ids and user_rank:
        lower_bound = max(1, int(user_rank * (1 - safety_percent / 100)))
        upper_bound = int(user_rank * (1 + safety_percent / 100))
        simulated["safety_margin"] = {
            "selected_option": f"{safety_percent}%",
            "label": f"{safety_percent}% 位次窗口",
            "field": "专业组最低位次1",
            "operator": "between",
            "value": [lower_bound, upper_bound],
            "source_expression": (
                f"{user_rank} * {1 - safety_percent / 100:.2f} 到 "
                f"{user_rank} * {1 + safety_percent / 100:.2f}"
            ),
        }

    tuition_cap = _optional_int(soft.get("tuition_cap_yuan"))
    if tuition_cap in {10000, 20000, 40000} and "c_tuition_cap" in candidate_rule_ids:
        simulated["tuition_threshold"] = {
            "selected_option": str(tuition_cap),
            "label": f"不高于 {tuition_cap} 元/年",
            "field": "学费",
            "operator": "<=",
            "value": tuition_cap,
        }

    if "c_major_expansion" in candidate_rule_ids:
        if bool(soft.get("major_expansion")):
            simulated["major_expansion"] = {
                "selected_option": "expand",
                "label": "扩展到相关专业",
                "expanded_terms": ["软件工程", "人工智能", "网络空间安全"],
                "reason": "当前 MVP 只展示确认，不新增专业扩展执行规则。",
            }
        else:
            simulated["major_expansion"] = {
                "selected_option": "none",
                "label": "不扩展",
                "expanded_terms": [],
            }

    if updated.get("non_executable_preferences"):
        simulated["cooperation_type"] = {
            "selected_option": None,
            "status": "not_executable",
            "reason": "缺少合作办学类型字段。",
        }

    updated["simulated_confirmations"] = simulated
    return updated


def _build_confirmation_candidates(
    user_request: str,
    attribute_grounding: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    seen: set[tuple[str, str, str]] = set()
    for record in attribute_grounding.get("attributes", []):
        match_type = _confirmation_match_type(record)
        if match_type not in {"partial_match", "no_schema_field"}:
            continue
        source_text = _display_record_source_text(record)
        field = record.get("source_column")
        field_id = record.get("field_id")
        mapping = _reviewed_candidate_mapping(record)
        if match_type == "partial_match" and not mapping:
            continue
        executable = bool(match_type == "partial_match" and mapping)
        if executable:
            operator = mapping["operator"]
            value = mapping["value"]
            label = mapping["label"]
            reason = mapping["reason"]
        else:
            operator = None
            value = None
            label = "不可执行"
            reason = _no_candidate_execution_reason(record, match_type)
        key = (str(field_id), source_text, _stable_value(value))
        if key in seen:
            continue
        seen.add(key)
        candidate = {
            "candidate_id": _confirmation_candidate_id(
                user_request=user_request,
                source_text=source_text,
                field_id=field_id,
                field=field,
                operator=operator,
                value=value,
            ),
            "source_text": source_text,
            "slot_path": record.get("slot_path"),
            "field_id": field_id,
            "field": field or "无可执行字段",
            "match_type": match_type,
            "operator": operator,
            "value": value,
            "label": label,
            "executable": executable,
            "reason": reason,
            "matched_values": _value_index_matched_values(
                record.get("value_index_audit") or {}
            ),
        }
        candidates.append(candidate)
    return candidates


def _resolve_confirmed_candidates(
    confirmed_candidates: list[str],
    confirmation_candidates: list[dict[str, Any]],
    verifier: RuleVerifier,
) -> dict[str, Any]:
    requested_ids = _clean_confirmed_candidate_ids(confirmed_candidates)
    candidates_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in confirmation_candidates
    }
    confirmed_rules = []
    confirmation_source = []
    rejected_candidates = []
    accepted_ids: set[str] = set()

    for candidate_id in requested_ids:
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            rejected_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "reason": "candidate_id 不属于当前 query，或不是系统上一轮生成的候选。",
                }
            )
            continue
        if not candidate.get("executable"):
            rejected_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_text": candidate.get("source_text"),
                    "reason": candidate.get("reason") or "该候选不能执行。",
                }
            )
            continue
        rule = _candidate_to_rule(candidate)
        verified = verifier.attach_verification(
            {
                "rule_id": rule["rule_id"],
                "field_id": candidate.get("field_id"),
                "field": rule["field"],
                "operator": rule["operator"],
                "value": rule["value"],
            }
        )
        if not verified.get("verification", {}).get("executable"):
            rejected_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_text": candidate.get("source_text"),
                    "reason": "候选规则未通过 RuleVerifier，不能执行。",
                }
            )
            continue
        accepted_ids.add(candidate_id)
        confirmed_rules.append(rule)
        confirmation_source.append(
            {
                "candidate_id": candidate_id,
                "source_text": candidate.get("source_text"),
                "field": candidate.get("field"),
                "operator": candidate.get("operator"),
                "value": candidate.get("value"),
                "source": "confirmed_candidates",
                "status": "accepted",
            }
        )

    unconfirmed = [
        candidate
        for candidate in confirmation_candidates
        if candidate.get("executable")
        and candidate.get("candidate_id") not in accepted_ids
    ]
    no_schema = [
        candidate
        for candidate in confirmation_candidates
        if candidate.get("match_type") == "no_schema_field"
    ]
    return {
        "requested_candidate_ids": requested_ids,
        "accepted_candidate_ids": sorted(accepted_ids),
        "rejected_candidates": rejected_candidates,
        "confirmed_rules": confirmed_rules,
        "confirmation_source": confirmation_source,
        "executed_after_confirmation": [],
        "unconfirmed_candidates": unconfirmed,
        "no_schema_field_preferences": no_schema,
    }


def _finalize_confirmation_execution(
    confirmation_state: dict[str, Any],
    execution_summary: dict[str, Any],
) -> dict[str, Any]:
    executed_rule_ids = set(execution_summary.get("hard_rule_ids") or [])
    updated = dict(confirmation_state)
    updated["executed_after_confirmation"] = [
        rule["rule_id"]
        for rule in confirmation_state.get("confirmed_rules", [])
        if rule.get("rule_id") in executed_rule_ids
    ]
    return updated


def _clean_confirmed_candidate_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        raw_values = value.get("candidate_ids") or value.get("confirmed_candidates") or []
    elif isinstance(value, str):
        raw_values = [value]
    else:
        try:
            raw_values = list(value)
        except TypeError:
            raw_values = [value]
    cleaned = []
    for item in raw_values:
        candidate_id = None
        if isinstance(item, dict):
            candidate_id = item.get("candidate_id")
        else:
            candidate_id = item
        text = _clean_text(candidate_id)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _candidate_to_rule(candidate: dict[str, Any]) -> dict[str, Any]:
    suffix = str(candidate["candidate_id"]).replace("cand_", "")
    return {
        "rule_id": f"e_confirmed_{suffix}",
        "derived_from": candidate["candidate_id"],
        "field": candidate["field"],
        "operator": candidate["operator"],
        "value": candidate["value"],
        "confirmation": "用户通过 candidate_id 确认",
        "confirmation_source": {
            "type": "confirmed_candidates",
            "candidate_id": candidate["candidate_id"],
            "source_text": candidate["source_text"],
        },
    }


def _confirmation_match_type(record: dict[str, Any]) -> str | None:
    status = record.get("status")
    audit_status = (record.get("value_index_audit") or {}).get("status")
    if status == "context_only":
        return None
    if (
        status in {"missing_schema", "ignored_not_schema_mapped", "unmapped_attribute"}
        or not record.get("field_exists_in_excel_schema")
        or audit_status == "field_inactive"
    ):
        return "no_schema_field"
    if status == "confirmable" or record.get("requires_human_confirmation"):
        return "partial_match"
    if audit_status in {
        "partial_match",
        "not_found",
        "not_found_in_partial_index",
        "partial_numeric_profile",
        "outside_numeric_profile",
    }:
        return "partial_match"
    return None


def _reviewed_candidate_mapping(record: dict[str, Any]) -> dict[str, Any] | None:
    field_id = record.get("field_id")
    source_text = _display_record_source_text(record)
    if field_id == "city" and source_text == "珠三角":
        return {
            "operator": "in_contains",
            "value": PEARL_RIVER_DELTA_CITIES,
            "label": "按珠三角城市集合筛选",
            "reason": "珠三角是区域集合，必须通过 candidate_id 确认后才执行城市过滤。",
        }
    if field_id == "major_name" and source_text == "计科":
        return {
            "operator": "contains_any",
            "value": ["计算机"],
            "label": "按计算机专业关键词筛选",
            "reason": "计科是缩写，必须通过 candidate_id 确认后才执行专业过滤。",
        }
    if field_id == "major_name" and source_text in {"计算机相关", "相关专业"}:
        return {
            "operator": "contains_any",
            "value": COMPUTER_RELATED_CONFIRMATION_TERMS,
            "label": "按计算机相关专业集合筛选",
            "reason": "相关专业是语义扩展，必须通过 candidate_id 确认后才执行专业过滤。",
        }
    return None


def _no_candidate_execution_reason(
    record: dict[str, Any],
    match_type: str,
) -> str:
    if match_type == "no_schema_field":
        return _grounding_reason(record.get("reason")) or "缺少可执行字段。"
    return "缺少已审查的候选值映射，不能执行。"


def _confirmation_candidate_id(
    user_request: str,
    source_text: str,
    field_id: Any,
    field: Any,
    operator: Any,
    value: Any,
) -> str:
    payload = {
        "user_request": user_request,
        "source_text": source_text,
        "field_id": field_id,
        "field": field,
        "operator": operator,
        "value": value,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"cand_{digest}"


def _display_record_source_text(record: dict[str, Any]) -> str:
    source_text = record.get("source_text")
    if isinstance(source_text, list):
        return "、".join(str(item) for item in source_text)
    if source_text not in (None, ""):
        return str(source_text)
    value = record.get("value")
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _display_confirmation_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "requested_candidate_ids": state.get("requested_candidate_ids", []),
        "accepted_candidate_ids": state.get("accepted_candidate_ids", []),
        "rejected_candidates": state.get("rejected_candidates", []),
        "confirmed_rules": [
            _display_rule(rule)
            for rule in state.get("confirmed_rules", [])
        ],
        "confirmation_source": state.get("confirmation_source", []),
        "executed_after_confirmation": state.get("executed_after_confirmation", []),
        "unconfirmed_candidates": state.get("unconfirmed_candidates", []),
        "no_schema_field_preferences": state.get("no_schema_field_preferences", []),
    }


def _append_unmapped_preferences(
    classified_rules: dict[str, Any],
    slots: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(classified_rules)
    existing = {
        item.get("source_text")
        for item in updated.get("non_executable_preferences", [])
    }
    preferences = list(updated.get("non_executable_preferences", []))
    for item in slots.get("unmapped_preferences") or []:
        source_text = _clean_text(item.get("source_text"))
        if not source_text or source_text in existing:
            continue
        preferences.append(
            {
                "source_text": source_text,
                "status": "not_executed",
                "reason": _sanitize_user_text(
                    item.get("reason") or "缺少可验证数据字段。"
                ),
                "field_id": item.get("field_id"),
            }
        )
        existing.add(source_text)
    updated["non_executable_preferences"] = preferences
    return updated


def _append_grounding_non_executable_preferences(
    classified_rules: dict[str, Any],
    attribute_grounding: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(classified_rules)
    existing = {
        item.get("source_text")
        for item in updated.get("non_executable_preferences", [])
    }
    existing_field_ids = {
        item.get("field_id")
        for item in updated.get("non_executable_preferences", [])
    }
    has_cooperation_warning = any(
        "中外合作" in str(item.get("source_text"))
        or item.get("field_id") == "cooperation_type"
        for item in updated.get("non_executable_preferences", [])
    )
    preferences = list(updated.get("non_executable_preferences", []))
    for record in attribute_grounding.get("attributes", []):
        if record.get("status") not in {"missing_schema", "unmapped_attribute"}:
            continue
        if record.get("field_id") == "cooperation_type" and has_cooperation_warning:
            continue
        value = record.get("value")
        source_text = (
            "、".join(str(item) for item in value)
            if isinstance(value, list)
            else str(value)
        )
        source_text = _clean_text(source_text)
        if not source_text or source_text in existing:
            continue
        if record.get("field_id") in existing_field_ids and record.get("field_id"):
            continue
        preferences.append(
            {
                "source_text": source_text,
                "status": "not_executed",
                "reason": _grounding_reason(record.get("reason")),
                "field_id": record.get("field_id"),
            }
        )
        existing.add(source_text)
        existing_field_ids.add(record.get("field_id"))
    updated["non_executable_preferences"] = preferences
    return updated


def _apply_value_index_hard_filter_guard(
    final_rules: list[dict[str, Any]],
    attribute_grounding: dict[str, Any],
) -> list[dict[str, Any]]:
    blocked = _value_index_blocked_rule_keys(attribute_grounding)
    guarded = []
    for rule in final_rules:
        updated = dict(rule)
        if _rule_value_key(rule) in blocked:
            updated["hard_filter_allowed"] = False
            updated["hard_filter_block_reason"] = blocked[_rule_value_key(rule)]
        guarded.append(updated)
    return guarded


def _value_index_blocked_rule_keys(
    attribute_grounding: dict[str, Any],
) -> dict[tuple[str, str], str]:
    blocked = {}
    for record in attribute_grounding.get("attributes", []):
        field = record.get("source_column")
        if not field:
            continue
        if not _grounded_attribute_is_blocked_from_hard_filter(record):
            continue
        blocked[(str(field), _stable_value(record.get("value")))] = (
            "value_index_audit 未达到 exact_match，不能进入 hard filter。"
        )
    return blocked


def _grounded_attribute_is_blocked_from_hard_filter(record: dict[str, Any]) -> bool:
    status = record.get("status")
    audit_status = (record.get("value_index_audit") or {}).get("status")
    if status in {"missing_schema", "ignored_not_schema_mapped", "unmapped_attribute"}:
        return True
    if record.get("requires_human_confirmation") or status == "confirmable":
        return True
    return audit_status in {
        "partial_match",
        "not_found",
        "not_found_in_partial_index",
        "partial_numeric_profile",
        "outside_numeric_profile",
        "field_inactive",
    }


def _rule_value_key(rule: dict[str, Any]) -> tuple[str, str]:
    return str(rule.get("field")), _stable_value(rule.get("value"))


def _merge_verified_proposed_rules(
    final_rules: list[dict[str, Any]],
    proposed_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(final_rules)
    seen = {_rule_identity(rule) for rule in merged}
    for proposed in proposed_rules:
        verification = proposed.get("verification", {})
        if not verification.get("executable"):
            proposed["execution_merge_status"] = "not_mergeable"
            continue
        executable_rule = {
            "rule_id": f"e_{proposed['rule_id']}",
            "derived_from": proposed["rule_id"],
            "field": proposed.get("field"),
            "operator": proposed.get("operator"),
            "value": verification.get("normalized_value", proposed.get("value")),
            "verification_origin": "verified_proposed_rule",
        }
        identity = _rule_identity(executable_rule)
        if identity in seen:
            proposed["execution_merge_status"] = "not_merged"
            proposed["execution_merge_reason"] = "执行层已存在同等规则，LLM 提议仅保留审查记录。"
            continue
        merge_block_reason = _proposed_rule_merge_block_reason(
            proposed=proposed,
            existing_rules=merged,
        )
        if merge_block_reason:
            proposed["execution_merge_status"] = "not_merged"
            proposed["execution_merge_reason"] = merge_block_reason
            continue
        merged.append(executable_rule)
        seen.add(identity)
        proposed["execution_merge_status"] = "merged"
        proposed["execution_merge_reason"] = "字段、操作符和值已通过验证，并已进入执行层。"
    return merged


def _proposed_rule_merge_block_reason(
    proposed: dict[str, Any],
    existing_rules: list[dict[str, Any]],
) -> str | None:
    """Decide whether a verified LLM proposal may enter execution.

    RuleVerifier answers whether a rule shape is schema-valid. This merge guard
    answers a narrower runtime question: whether the LLM proposal should add a
    new executable filter on top of deterministic and confirmed rules.
    """

    category = str(proposed.get("category") or "")
    if category != "deterministic":
        return "该提议不是确定性规则，不能直接进入执行层。"

    semantic_type = str(proposed.get("semantic_type") or proposed.get("value_source") or "")
    if semantic_type != "explicit_user_fact":
        return "该提议不是明确用户事实，不能越过候选确认流程进入执行层。"

    field = proposed.get("field")
    if field == "专业组最低位次1":
        return "排位安全边界只能由用户排位和已确认边界生成，LLM 提议仅保留审查记录。"

    existing_fields = {rule.get("field") for rule in existing_rules}
    if field in existing_fields:
        return "执行层已有同字段规则，LLM 提议不能再追加同字段筛选条件。"

    return None


def _rule_identity(rule: dict[str, Any]) -> str:
    return "|".join(
        [
            str(rule.get("field")),
            str(rule.get("operator")),
            _stable_value(rule.get("value")),
        ]
    )


def _stable_value(value: Any) -> str:
    if isinstance(value, list):
        return "list:" + "|".join(str(item) for item in value)
    return str(value)


def _compose_user_request(config: WorkbenchConfig) -> str:
    hard = config.hard_filters
    soft = config.soft_preferences
    parts = []
    source_province = _clean_text(hard.get("source_province"))
    subject_type = _clean_text(hard.get("subject_type"))
    reselected_subjects = _clean_list(hard.get("reselected_subjects"))
    user_rank = _optional_int(hard.get("user_rank"))
    major_keyword = _clean_text(hard.get("major_keyword"))
    cities = _clean_list(hard.get("preferred_cities"))
    tuition_cap = _optional_int(hard.get("tuition_cap_yuan"))
    if source_province:
        parts.append(source_province)
    if subject_type:
        parts.append(f"{subject_type}类")
    if reselected_subjects:
        parts.append(f"再选科目：{'、'.join(reselected_subjects)}")
    if user_rank:
        parts.append(f"排位{user_rank}")
    if major_keyword:
        parts.append(f"专业关键词：{major_keyword}")
    if cities:
        parts.append(f"城市：{'、'.join(cities)}")
    if tuition_cap:
        parts.append(f"硬性学费上限：{tuition_cap}元/年")

    boundary_parts = []
    safety_percent = _optional_int(soft.get("safety_margin_percent"))
    soft_tuition_cap = _optional_int(soft.get("tuition_cap_yuan"))
    if safety_percent:
        boundary_parts.append(f"位次窗口 {safety_percent}%")
    if soft_tuition_cap and not tuition_cap:
        boundary_parts.append(f"费用上限 {soft_tuition_cap} 元/年")
    prompt = _clean_sentence(soft.get("prompt"))
    soft_parts = []
    if boundary_parts:
        soft_parts.append(f"已确认边界：{'，'.join(boundary_parts)}")
    if prompt:
        soft_parts.append(f"偏好描述：{prompt}")

    hard_text = "，".join(parts) if parts else config.user_input
    if not soft_parts:
        return hard_text
    return f"{hard_text}；偏好信息：{'；'.join(soft_parts)}。"


def _display_hard_filters(hard_filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_province": _clean_text(hard_filters.get("source_province")),
        "subject_type": _clean_text(hard_filters.get("subject_type")),
        "reselected_subjects": _clean_list(hard_filters.get("reselected_subjects")),
        "user_rank": _optional_int(hard_filters.get("user_rank")),
        "major_keyword": _clean_text(hard_filters.get("major_keyword")),
        "preferred_cities": _clean_list(hard_filters.get("preferred_cities")),
        "tuition_cap_yuan": _optional_int(hard_filters.get("tuition_cap_yuan")),
    }


def _boundary_context(soft_preferences: dict[str, Any]) -> dict[str, Any]:
    return {
        "safety_margin_percent": _optional_int(
            soft_preferences.get("safety_margin_percent")
        ),
        "tuition_cap_yuan": _optional_int(soft_preferences.get("tuition_cap_yuan")),
    }


def _display_soft_preferences(soft_preferences: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": _clean_text(soft_preferences.get("prompt")),
        "safety_margin_percent": _optional_int(
            soft_preferences.get("safety_margin_percent")
        ),
        "tuition_cap_yuan": _optional_int(soft_preferences.get("tuition_cap_yuan")),
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_sentence(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return text.rstrip("。；;，, ")


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    cleaned = []
    for item in values:
        text = _clean_text(item)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extracted_preferences(slots: dict[str, Any]) -> list[dict[str, Any]]:
    context = slots.get("user_context", {})
    preferences = slots.get("preferences", {})
    items = [
        ("pref_origin", "生源地", context.get("source_province"), "已对齐字段"),
        ("pref_track", "科类", context.get("subject_type"), "已对齐字段"),
        (
            "pref_reselected_subjects",
            "再选科目",
            context.get("reselected_subjects"),
            "已对齐字段",
        ),
        ("pref_rank", "排位", context.get("user_rank"), "已对齐字段"),
        (
            "pref_major",
            "专业名称",
            preferences.get("major_exact_terms") or preferences.get("major_keyword"),
            "已对齐字段",
        ),
        ("pref_city", "城市", preferences.get("preferred_cities"), "已对齐字段"),
        (
            "pref_school_province",
            "院校所在地省份",
            preferences.get("preferred_school_provinces"),
            "已对齐字段",
        ),
        (
            "pref_recommendation",
            "推荐请求",
            preferences.get("recommendation_request_raw"),
            "待确认",
        ),
        ("pref_stable", "稳一点", preferences.get("risk_preference_raw"), "待确认"),
        ("pref_expensive", "太贵", preferences.get("tuition_preference_raw"), "待确认"),
        (
            "pref_cooperation",
            "中外合作",
            preferences.get("cooperation_preference_raw"),
            "不可执行",
        ),
        (
            "pref_overseas",
            "境外就读",
            preferences.get("overseas_preference_raw"),
            "不可执行",
        ),
    ]
    return [
        {
            "id": item_id,
            "slot": slot,
            "value": value,
            "source_span": _source_span(slot, value),
            "status": status,
        }
        for item_id, slot, value, status in items
        if value not in (None, "", [])
    ]


def _source_span(slot: str, value: Any) -> str:
    if slot == "排位":
        return f"排位{value}"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _display_attribute_grounding(grounding: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": grounding.get("summary", {}),
        "attributes": [
            {
                "slot_path": record.get("slot_path"),
                "slot": _slot_path_label(record.get("slot_path")),
                "value": record.get("value"),
                "field": record.get("source_column") or "无可执行字段",
                "status": _grounding_status_label(record.get("status")),
                "status_type": _grounding_status_type(record.get("status")),
                "reason": _grounding_reason(record.get("reason")),
                "value_index": _display_value_index_audit(
                    record.get("value_index_audit")
                ),
            }
            for record in grounding.get("attributes", [])
        ],
    }


def _display_execution_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "executor": summary.get("executor"),
        "sql": summary.get("sql"),
        "params": summary.get("params", []),
        "input_row_count": summary.get("input_row_count"),
        "filtered_row_count": summary.get("filtered_row_count"),
        "sort_key": summary.get("sort_key", []),
        "top_k": summary.get("top_k"),
        "hard_rule_ids": summary.get("hard_rule_ids", []),
        "skipped_soft_rule_ids": summary.get("skipped_soft_rule_ids", []),
    }


def _display_value_index_audit(audit: Any) -> dict[str, Any] | None:
    if not isinstance(audit, dict):
        return None
    status = audit.get("status")
    return {
        "status": _value_index_status_label(status),
        "status_type": _value_index_status_type(status),
        "profile_kind": audit.get("profile_kind"),
        "lookup_complete": audit.get("lookup_complete"),
        "matched_values": _value_index_matched_values(audit),
        "numeric": audit.get("numeric"),
    }


def _value_index_matched_values(audit: dict[str, Any]) -> list[str]:
    matched = []
    for check in audit.get("checks") or []:
        for value in check.get("matched_values") or []:
            text = str(value)
            if text not in matched:
                matched.append(text)
    return matched[:5]


def _value_index_status_label(status: Any) -> str:
    labels = {
        "matched": "值已在索引中匹配",
        "partial_match": "部分值在索引中匹配",
        "not_found": "值未在完整索引中命中",
        "not_found_in_partial_index": "值未在部分索引中命中",
        "within_numeric_profile": "数值在历史字段范围内",
        "partial_numeric_profile": "部分数值在历史字段范围内",
        "outside_numeric_profile": "数值超出历史字段范围",
        "lookup_unavailable": "字段值索引不可用",
        "field_inactive": "字段未启用",
        "field_not_indexed": "字段未索引",
        "empty_value": "值为空",
        "not_applicable": "不适用",
    }
    return labels.get(str(status), str(status))


def _value_index_status_type(status: Any) -> str:
    if status in {"matched", "within_numeric_profile"}:
        return "success"
    if status in {
        "partial_match",
        "not_found_in_partial_index",
        "partial_numeric_profile",
        "lookup_unavailable",
        "not_applicable",
    }:
        return "warning"
    return "danger"


def _display_proposed_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": rule.get("rule_id"),
            "label": _rule_label(rule),
            "source_text": rule.get("source_text") or "结构化输入",
            "category": _category_label(rule.get("category")),
            "status": _proposed_rule_status_label(rule),
            "status_type": _proposed_rule_status_type(rule),
            "reason": _proposed_rule_reason(rule),
            "checks": _verification_checks(rule.get("verification", {})),
        }
        for rule in rules
    ]


def _display_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rule["rule_id"],
        "label": _rule_label(rule),
        "field": rule.get("field"),
        "operator": rule.get("operator"),
        "value": rule.get("value"),
        "source_span": _source_span(str(rule.get("field", "")), rule.get("value")),
    }


def _candidate_rules(classified_rules: dict[str, Any]) -> list[dict[str, Any]]:
    questions = {
        question["question_id"]: question["options"]
        for question in classified_rules.get("confirmation_questions", [])
    }
    question_id_by_rule = {
        "c_recommendation_rank_floor": "q_recommendation_rank_floor",
        "c_safety_margin": "q_safety_margin",
        "c_tuition_cap": "q_tuition_cap",
        "c_major_expansion": "q_major_expansion",
    }
    rules = []
    for rule in classified_rules.get("candidate_rules", []):
        options = [
            str(option.get("label") or option.get("value"))
            for option in questions.get(question_id_by_rule.get(rule["rule_id"]), [])
        ]
        rules.append(
            {
                "id": rule["rule_id"],
                "preference": rule.get("value") or rule.get("source_text"),
                "label": _candidate_label(rule),
                "reason": _candidate_reason(rule),
                "options": options,
                "simulated_selection": _simulated_label(classified_rules, rule),
            }
        )
    return rules


def _candidate_label(rule: dict[str, Any]) -> str:
    if rule.get("rule_id") == "c_recommendation_rank_floor":
        return "基本可达位次候选规则"
    if rule.get("rule_id") == "c_safety_margin":
        return "位次窗口候选规则"
    if rule.get("rule_id") == "c_tuition_cap":
        return "学费上限候选规则"
    if rule.get("rule_id") == "c_major_expansion":
        return "专业扩展候选规则"
    return "待确认候选规则"


def _candidate_reason(rule: dict[str, Any]) -> str:
    if rule.get("rule_id") == "c_recommendation_rank_floor":
        return "推荐请求需要先确认是否按用户位次排除明显不可达结果。"
    if rule.get("rule_id") == "c_safety_margin":
        return "风险边界需要明确位次窗口；用户选择后才可提升为可执行规则。"
    if rule.get("rule_id") == "c_tuition_cap":
        return "费用偏好需要明确金额；用户选择后才可提升为可执行规则。"
    if rule.get("rule_id") == "c_major_expansion":
        return "“相关专业”是语义扩展，需要确认后才能考虑；当前 MVP 不新增扩展执行规则。"
    return "该偏好需要用户确认边界后才可执行。"


def _simulated_label(classified_rules: dict[str, Any], rule: dict[str, Any]) -> str:
    simulated = classified_rules.get("simulated_confirmations", {})
    if rule.get("rule_id") == "c_recommendation_rank_floor":
        return str(simulated.get("recommendation_rank_floor", {}).get("label", ""))
    if rule.get("rule_id") == "c_safety_margin":
        return str(simulated.get("safety_margin", {}).get("label", ""))
    if rule.get("rule_id") == "c_tuition_cap":
        return str(simulated.get("tuition_threshold", {}).get("label", ""))
    if rule.get("rule_id") == "c_major_expansion":
        return str(simulated.get("major_expansion", {}).get("label", ""))
    return ""


def _not_executed_preferences(classified_rules: dict[str, Any]) -> list[dict[str, Any]]:
    preferences = []
    for index, item in enumerate(
        classified_rules.get("non_executable_preferences", []),
        start=1,
    ):
        source_text = item.get("source_text", "该偏好")
        reason = _sanitize_user_text(item.get("reason") or "缺少可验证数据字段。")
        is_cooperation = (
            item.get("field_id") == "cooperation_type"
            or "中外合作" in str(source_text)
        )
        preferences.append(
            {
                "id": f"not_exec_{index}",
                "preference": source_text,
                "display": (
                    NOT_EXECUTED_COOPERATION_TEXT
                    if is_cooperation
                    else f"{source_text}未执行：{reason}"
                ),
                "reason": NOT_EXECUTED_COOPERATION_REASON if is_cooperation else reason,
                "missing_field": (
                    "合作办学类型字段" if is_cooperation else "缺少已审查数据字段"
                ),
                "source_span": source_text,
            }
        )
    return preferences


def _simulated_confirmations(classified_rules: dict[str, Any]) -> dict[str, Any]:
    simulated = classified_rules.get("simulated_confirmations", {})
    safety_value = simulated.get("safety_margin", {}).get("value")
    return {
        "recommendation_rank_floor": simulated.get(
            "recommendation_rank_floor",
            {},
        ).get("value"),
        "safety_margin_percent": _confirmation_percent(
            simulated.get("safety_margin", {}).get("label")
        ),
        "safety_rank_cutoff": safety_value,
        "tuition_cap": simulated.get("tuition_threshold", {}).get("value"),
        "major_expansion": bool(
            simulated.get("major_expansion", {}).get("expanded_terms")
        ),
    }


def _executable_rule(rule: dict[str, Any]) -> dict[str, Any]:
    origin = "deterministic"
    if str(rule.get("derived_from", "")).startswith("c_"):
        origin = "simulated_confirmation"
    if rule.get("verification_origin") == "verified_proposed_rule":
        origin = "verified_llm_proposal"
    return {
        "id": rule["rule_id"],
        "label": _rule_label(rule),
        "origin": origin,
    }


def _top_result(rank: int, row: dict[str, Any]) -> dict[str, Any]:
    trace = [
        {
            "status": "pass" if item.get("status") == "pass" else "not_executed",
            "text": _trace_text(item),
        }
        for item in row.get("trace", [])
    ]
    return {
        "id": f"result_{rank:03d}",
        "university_name": row.get("院校名称"),
        "group_code": row.get("院校专业组代码"),
        "major_code": row.get("专业代码"),
        "major_name": row.get("专业名称"),
        "full_major_name": row.get("专业全称"),
        "subject_requirement": row.get("选科要求"),
        "city": row.get("城市"),
        "tuition": row.get("学费"),
        "group_min_rank": row.get("专业组最低位次1"),
        "major_min_rank": row.get("最低位次1"),
        "safety_margin": _percent(row.get("safety_margin_pct")),
        "trace": trace,
    }


def _trace_text(item: dict[str, Any]) -> str:
    if item.get("rule_id") == "l_cooperation_type":
        return "中外合作：缺少合作办学类型字段，未执行"
    reason = str(item.get("reason", ""))
    return (
        reason.replace("contains", "包含")
        .replace("matches", "匹配")
        .replace("safety margin", "安全边际")
    )


def _report_from_answer(answer: str, evidence: dict[str, Any]) -> dict[str, Any]:
    safe_answer = _sanitize_user_text(answer)
    result_count = evidence["result_count"]
    warnings = _report_warnings(evidence)
    return {
        "title": "规则验证结果（非最终志愿建议）",
        "summary": (
            f"系统基于已验证规则完成筛选，共 {result_count} 条结果。"
            "候选偏好只在确认或模拟确认后执行；未执行偏好会保留为警告。"
        ),
        "full_text": safe_answer,
        "result_count_text": f"当前共有 {result_count} 条记录通过已验证规则。",
        "executed_rules": [
            rule["description"] for rule in evidence["executed_rules"]
        ],
        "attribute_explanations": evidence.get("attribute_explanations", []),
        "top_results": [_result_text(row) for row in evidence["top_k_results"][:3]],
        "warnings": warnings,
        "disclaimer": "以上内容是规则验证结果和证据汇总，不是最终志愿建议。",
    }


def _rule_label(rule: dict[str, Any]) -> str:
    operator = rule.get("operator")
    field = rule.get("field") or "未映射字段"
    value = _format_value(rule.get("value"))
    if operator == "eq":
        return f"{field} 等于 {value}"
    if operator == "neq":
        return f"{field} 不等于 {value}"
    if operator == "contains":
        return f"{field} 包含 {value}"
    if operator in {"in_contains", "contains_any"}:
        return f"{field} 包含任一：{value}"
    if operator == "in":
        return f"{field} 属于：{value}"
    if operator == "not_in":
        return f"{field} 不属于：{value}"
    if operator == "satisfies_subject_requirement":
        return f"{field} 满足已选再选科目：{value}"
    if operator == "<=":
        if field == "专业组最低位次1":
            return f"{field} 在 {value} 名以内（数值 <= {value}）"
        return f"{field} 不高于 {value}"
    if operator == ">=":
        if field == "专业组最低位次1":
            return f"{field} 在 {value} 名及以后（数值 >= {value}）"
        return f"{field} 不低于 {value}"
    if operator == "between":
        if field == "专业组最低位次1":
            return f"{field} 位于 {_format_rank_window(rule.get('value'))}的窗口内"
        return f"{field} 位于 {value} 之间"
    if operator == "sort":
        return f"{field} 排序：{value}"
    return f"{field} {operator} {value}"


def _slot_path_label(slot_path: Any) -> str:
    labels = {
        "user_context.source_province": "生源地",
        "user_context.subject_type": "科类",
        "user_context.reselected_subjects": "再选科目",
        "user_context.user_rank": "排位",
        "preferences.major_keyword": "专业关键词",
        "preferences.major_exact_terms": "专业精确词",
        "preferences.preferred_cities": "城市偏好",
        "preferences.preferred_school_provinces": "院校所在地省份偏好",
        "preferences.risk_preference_raw": "风险偏好",
        "preferences.tuition_preference_raw": "费用偏好",
        "preferences.tuition_cap_yuan": "明确费用上限",
        "preferences.major_expansion_raw": "专业扩展偏好",
        "preferences.cooperation_preference_raw": "中外合作偏好",
        "preferences.overseas_preference_raw": "境外就读偏好",
        "preferences.school_ownership_preference_raw": "办学性质偏好",
        "preferences.recommendation_request_raw": "推荐请求",
        "preferences.other_vague_preferences[]": "其他模糊偏好",
    }
    return labels.get(str(slot_path), str(slot_path))


def _grounding_status_label(status: Any) -> str:
    labels = {
        "schema_grounded": "已接地到数据字段",
        "confirmable": "字段存在但需要确认",
        "context_only": "仅作为上下文",
        "missing_schema": "缺少可执行字段",
        "ignored_not_schema_mapped": "未映射，已忽略",
        "unmapped_attribute": "未映射",
    }
    return labels.get(str(status), str(status))


def _grounding_status_type(status: Any) -> str:
    if status == "schema_grounded":
        return "success"
    if status in {"confirmable", "context_only"}:
        return "warning"
    return "danger"


def _grounding_reason(reason: Any) -> str:
    if reason is None:
        return ""
    replacements = {
        "Attribute maps to an active Excel schema field; rule verification is still required.": (
            "该属性已映射到当前数据字段，但仍需经过规则验证。"
        ),
        "Attribute maps to an active field but is vague or semantic; confirmation is required.": (
            "该属性有对应字段，但语义或边界需要确认。"
        ),
        "Attribute is context only and must not be executed as an Excel filter.": (
            "该属性只作为上下文，不能直接作为筛表条件。"
        ),
        "Attribute has no active Excel schema field and must not execute.": (
            "当前数据中没有可执行字段，不能进入筛表。"
        ),
        "Extractor emitted an unknown attribute; it is ignored by rule construction.": (
            "抽取器输出了未登记属性，规则构造会忽略它。"
        ),
        "Excel schema": "数据字段",
        "schema": "数据字段定义",
    }
    text = str(reason)
    for source, target in replacements.items():
        text = text.replace(source, target)
    return _sanitize_user_text(text)


def _category_label(category: Any) -> str:
    labels = {
        "deterministic": "确定性提议",
        "candidate": "候选提议",
        "context": "上下文提议",
    }
    return labels.get(str(category), str(category))


def _verification_status_label(status: Any) -> str:
    labels = {
        "executable": "验证通过，可执行",
        "confirmable": "可确认后执行",
        "context_only": "仅作为上下文",
        "rejected_missing_schema": "拒绝：缺少字段",
        "rejected_invalid_operator": "拒绝：操作符不允许",
        "rejected_invalid_value": "拒绝：值无效",
        "rejected_ambiguous": "拒绝：语义模糊",
        "blocked_missing_context": "阻塞：缺少上下文",
        "blocked": "阻塞",
    }
    return labels.get(str(status), str(status))


def _verification_status_type(status: Any) -> str:
    if status == "executable":
        return "success"
    if status in {"confirmable", "context_only", "blocked_missing_context"}:
        return "warning"
    return "danger"


def _proposed_rule_status_label(rule: dict[str, Any]) -> str:
    merge_status = rule.get("execution_merge_status")
    if merge_status == "merged":
        return "验证通过，已进入执行层"
    if merge_status == "not_merged":
        return "已审查，未进入执行层"
    return _verification_status_label(
        rule.get("verification", {}).get("terminal_status")
    )


def _proposed_rule_status_type(rule: dict[str, Any]) -> str:
    merge_status = rule.get("execution_merge_status")
    if merge_status == "merged":
        return "success"
    if merge_status == "not_merged":
        return "warning"
    return _verification_status_type(
        rule.get("verification", {}).get("terminal_status")
    )


def _proposed_rule_reason(rule: dict[str, Any]) -> str:
    if rule.get("execution_merge_reason"):
        return _sanitize_user_text(rule["execution_merge_reason"])
    verification = rule.get("verification", {})
    if verification.get("executable"):
        return "字段、操作符和值均通过确定性验证。"
    if verification.get("terminal_status") == "confirmable":
        return "规则形状可审查，但需要用户确认边界后才能执行。"
    if rule.get("reason"):
        return _sanitize_user_text(rule["reason"])
    error = verification.get("value_error")
    if error == "missing_schema":
        return "当前数据中缺少对应字段。"
    if error == "missing_value":
        return "规则值为空，不能执行。"
    if error:
        return f"规则值未通过规范化：{_value_error_label(error)}"
    return "未通过规则验证。"


def _value_error_label(error: Any) -> str:
    labels = {
        "missing_schema": "缺少可执行字段",
        "missing_value": "规则值为空",
        "confirmation_value_required": "需要用户确认具体边界值",
        "invalid_subject_selection": "再选科目无效",
        "invalid_numeric_range": "数值区间无效",
        "invalid_number": "数值无效",
        "invalid_list": "列表值无效",
        "invalid_text": "文本值无效",
    }
    return labels.get(str(error), "未知值错误")


def _verification_checks(verification: dict[str, Any]) -> list[dict[str, Any]]:
    check_labels = [
        ("field_exists", "字段存在"),
        ("source_column_exists", "源列存在"),
        ("operator_allowed", "操作符允许"),
        ("type_valid", "值类型有效"),
        ("value_normalized", "值已规范化"),
    ]
    return [
        {
            "label": label,
            "passed": bool(verification.get(key)),
        }
        for key, label in check_labels
    ]


def _format_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _format_rank_window(value: Any) -> str:
    if isinstance(value, list) and len(value) == 2:
        return f"{_format_value(value[0])}-{_format_value(value[1])} 名"
    return f"{_format_value(value)} 名"


def _percent(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.1%}"


def _result_text(row: dict[str, Any]) -> str:
    parts = [
        f"{row.get('院校名称')}（专业组 {row.get('院校专业组代码')}）",
        f"专业代码 {row.get('专业代码')}",
        f"专业名称 {row.get('专业名称')}",
    ]
    if row.get("专业全称"):
        parts.append(f"专业全称 {row.get('专业全称')}")
    if row.get("选科要求") not in (None, ""):
        parts.append(f"选科要求 {row.get('选科要求')}")
    parts.extend(
        [
            f"城市 {row.get('城市')}",
            f"学费 {row.get('学费')}",
            f"专业组最低位次 {row.get('专业组最低位次')}",
        ]
    )
    if row.get("专业最低位次") not in (None, ""):
        parts.append(f"专业最低位次 {row.get('专业最低位次')}")
    if row.get("safety_margin"):
        parts.append(f"相对排位差 {row.get('safety_margin')}")
    return "；".join(parts)


def _confirmation_percent(label: Any) -> int | None:
    if not label:
        return None
    text = str(label)
    for percent in (5, 10, 15):
        if f"{percent}%" in text:
            return percent
    return None


def _sanitize_user_text(text: str) -> str:
    protected = {
        "no_schema_field": "__NO_SCHEMA_FIELD__",
        "exact_match": "__EXACT_MATCH__",
        "partial_match": "__PARTIAL_MATCH__",
    }
    for source, marker in protected.items():
        text = text.replace(source, marker)
    replacements = {
        "Missing dedicated cooperation_type field. No text-field inference is used in this MVP.": (
            "缺少合作办学类型字段，未使用文本字段推断。"
        ),
        "Missing dedicated cooperation_type field.": "缺少合作办学类型字段。",
        "No reviewed active school reputation field.": "当前数据中没有已审查的学校声誉字段。",
        "No reviewed active school ranking field.": "当前数据中没有已审查的学校排名字段。",
        "No reviewed active school quality field.": "当前数据中没有已审查的学校质量字段。",
        "No reviewed active school ownership field in MVP schema.": (
            "当前数据中没有已审查的办学性质字段。"
        ),
        "No employment outcome field.": "当前数据中没有就业结果字段。",
        "No home location or distance field.": "当前数据中没有家庭位置或距离字段。",
        "No reviewed active remoteness field.": "当前数据中没有已审查的偏远程度字段。",
        "No major popularity field.": "当前数据中没有专业热度字段。",
        "No admission probability field.": "当前数据中没有录取概率字段。",
        "Needs confirmed city set.": "需要确认具体城市集合。",
        "Needs confirmed Pearl River Delta city set.": "需要确认珠三角城市集合。",
        "Needs confirmed city quality proxy or city set.": (
            "需要确认城市质量代理字段或具体城市集合。"
        ),
        "Conflicts with city preference and needs confirmation.": (
            "与城市偏好可能冲突，需要确认。"
        ),
        "A candidate Excel column exists in the schema profile, but school ownership has not been promoted into the active MVP schema registry.": (
            "字段画像中存在候选办学性质列，但该字段尚未进入当前可执行字段定义。"
        ),
        "No reviewed active school country or overseas study field.": (
            "当前数据中没有已审查的国家或境外办学字段。"
        ),
        "No dedicated school country or overseas study field.": (
            "缺少国家或境外办学字段。"
        ),
        "Guangdong 3+1+2 reselected subjects are matched against the Excel field 选科要求.": (
            "广东 3+1+2 的再选科目需要和数据字段“选科要求”匹配。"
        ),
        "School province preference maps to the Excel field 所在省; rule verification is still required.": (
            "院校所在地省份偏好可以映射到数据字段“所在省”，仍需经过规则验证。"
        ),
        "Recommendation requests need a rank-derived reachability boundary before execution.": (
            "推荐请求需要结合用户位次生成基本可达边界，确认后才能执行。"
        ),
        "User rank is context for candidate formulas, not an Excel source column.": (
            "用户排位用于计算候选规则边界，不是直接筛表的数据源列。"
        ),
        "Explicit major names extracted as a list; execution still requires rule construction and verification.": (
            "明确专业词可以作为列表抽取，但仍需经过规则构造和验证后才能执行。"
        ),
        "Explicit numeric tuition caps such as 学费两万以内 can become executable after rule construction and verification.": (
            "“学费两万以内”等明确数字费用上限，在规则构造和验证通过后可以执行。"
        ),
        "field_id": "字段标识",
        "source_column": "源列",
        "operator": "操作符",
        "value": "规则值",
        "semantic_type": "语义类型",
        "reason": "原因",
        "field": "字段",
        "cooperation_type": "合作办学类型字段",
        "school_country_or_region": "国家或境外办学字段",
        "schema": "数据字段定义",
        "evidence_pack": "证据包",
        "safety margin": "安全边际",
    }
    output = text
    for source, target in replacements.items():
        output = output.replace(source, target)
    for source, marker in protected.items():
        output = output.replace(marker, source)
    return output


def _report_warnings(evidence: dict[str, Any]) -> list[str]:
    warnings = [
        preference.get("safety_warning") or NOT_EXECUTED_COOPERATION_TEXT
        for preference in evidence.get("not_executed_preferences", [])
    ]
    has_safety_rule = any(
        rule.get("field") == "专业组最低位次1"
        and rule.get("operator") in {">=", "between"}
        for rule in evidence.get("executed_rules", [])
    )
    if not has_safety_rule:
        warnings.append(
            "本次没有确认位次窗口规则，结果只表示字段筛选通过，不代表风险已判断。"
        )
    return [_sanitize_user_text(warning) for warning in warnings]


def _with_context_warnings(
    report: dict[str, Any],
    slots: dict[str, Any],
) -> dict[str, Any]:
    user_context = slots.get("user_context", {})
    warnings = list(report.get("warnings", []))
    if not user_context.get("subject_type"):
        warnings.append("缺少科类（物理/历史），结果未按科类过滤，请补充后再判断。")
    if not user_context.get("reselected_subjects"):
        warnings.append("缺少再选科目（化学/生物/政治/地理四选二），结果未按专业选科要求过滤。")
    if not user_context.get("user_rank"):
        warnings.append("缺少省排名/位次，不能判断风险边界。")
    report = dict(report)
    report["warnings"] = warnings
    return report


def _sum_usage(usages: list[dict[str, int] | None]) -> dict[str, int]:
    total: dict[str, int] = {}
    for usage in usages:
        if not usage:
            continue
        for key, value in usage.items():
            total[key] = total.get(key, 0) + int(value)
    return total


def _options(options: dict[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in options.items()]
