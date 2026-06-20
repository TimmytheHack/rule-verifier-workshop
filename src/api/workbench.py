"""Display adapter for the frontend workbench.

This module runs the existing verified pipeline and reshapes its artifacts for
the UI. It does not add verifier, promoter, executor, or recommendation logic.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.adapters.data_warehouse import (
    SchemaValueIndex,
    audit_data_warehouse_fingerprints,
    load_structured_dataset,
)
from src.adapters.excel_adapter import ExcelDataSet
from src.domains import DomainConfig
from src.executors.duckdb_executor import (
    DuckDBExecutor,
    ExecutionResult,
    hard_filter_rules,
)
from src.api.admissions_query_planner import AdmissionsQueryPlanner
from src.extractors.deepseek_extractor import (
    DeepSeekClient,
)
from src.extractors.extractor_pipeline import ExtractorFallbackPipeline
from src.extractors.llm_slot_adapter import (
    DeepSeekSlotAdapter,
    deepseek_slot_adapter_enabled,
    llm_runtime_enabled,
)
from src.extractors.regex_extractor import RegexExtractor
from src.reporting.career_guidance import career_guidance_for_query
from src.reporting.deepseek_answer_generator import (
    DeepSeekAnswerGenerator,
)
from src.reporting.evidence_pack import EvidencePack
from src.reporting.policy_reference import policy_references_for_query
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
ADMISSIONS_DOMAIN = DomainConfig.load("admissions")

EXTRACTOR_OPTIONS = {
    "hybrid": "规则优先，LLM 补槽",
    "regex": "规则解析软偏好",
    "deepseek": "LLM 辅助解析软偏好",
}
EXTRACTOR_ALIASES = {
    "deepseek_slots": "deepseek",
}

GENERATOR_OPTIONS = {
    "template_evidence": "模板证据回答",
    "deepseek_evidence": "LLM 证据回答",
}

MODEL_OPTIONS = {
    "deepseek-v4-flash": "LLM 快速模型",
    "deepseek-v4-pro": "LLM 高质量模型",
}

RANK_WINDOW_OPTIONS = [
    {
        "value": "reach",
        "label": "冲一冲",
        "rank_window_lower_percent": 0,
        "rank_window_upper_percent": 0,
        "description": "只执行后 0% 上界，不设置前向下界。",
    },
    {
        "value": "steady",
        "label": "稳一点",
        "rank_window_lower_percent": 0,
        "rank_window_upper_percent": 15,
        "description": "只执行后 15% 上界，不设置前向下界。",
    },
    {
        "value": "safe",
        "label": "保底",
        "rank_window_lower_percent": 0,
        "rank_window_upper_percent": 50,
        "description": "只执行后 50% 上界，不设置前向下界。",
    },
]

SORT_MODE_OPTIONS = {
    "rank_asc": "按历史位次从高到低看（更冲）",
    "rank_desc": "按历史位次从低到高看（更稳）",
    "school_rank_asc": "同等条件下优先院校排名",
}

ADMISSIONS_SORT_POLICIES = {
    "rank_asc": [
        {
            "helper": "__group_rank_num",
            "label_field_id": "group_min_rank_2024",
            "direction": "ASC",
            "nulls": "LAST",
        },
        {
            "helper": "__school_rank_num",
            "label_field_id": "school_rank",
            "direction": "ASC",
            "nulls": "LAST",
            "optional": True,
        },
        {
            "helper": "__id_num",
            "label_field_id": "row_id",
            "direction": "ASC",
            "nulls": "LAST",
            "optional": True,
        },
    ],
    "rank_desc": [
        {
            "helper": "__group_rank_num",
            "label_field_id": "group_min_rank_2024",
            "direction": "DESC",
            "nulls": "LAST",
        },
        {
            "helper": "__school_rank_num",
            "label_field_id": "school_rank",
            "direction": "ASC",
            "nulls": "LAST",
            "optional": True,
        },
        {
            "helper": "__id_num",
            "label_field_id": "row_id",
            "direction": "ASC",
            "nulls": "LAST",
            "optional": True,
        },
    ],
    "school_rank_asc": [
        {
            "helper": "__school_rank_num",
            "label_field_id": "school_rank",
            "direction": "ASC",
            "nulls": "LAST",
            "optional": True,
        },
        {
            "helper": "__group_rank_num",
            "label_field_id": "group_min_rank_2024",
            "direction": "ASC",
            "nulls": "LAST",
        },
        {
            "helper": "__id_num",
            "label_field_id": "row_id",
            "direction": "ASC",
            "nulls": "LAST",
            "optional": True,
        },
    ],
}

WORKBENCH_STATUS_VALUES = {
    "ok",
    "needs_confirmation",
    "no_results",
    "blocked",
    "error",
}
INTERACTIVE_DEEPSEEK_TIMEOUT_SECONDS = 25
INTERACTIVE_DEEPSEEK_MAX_RETRIES = 1
EVIDENCE_TOP_K = 5
WORKBENCH_SCHEMA_VERSION = "workbench_response.v1"

WAREHOUSE_DATABASE_PATH = Path("outputs/data/guangdong_admissions.duckdb")
WAREHOUSE_VALUE_INDEX_PATH = Path("outputs/data/schema_value_index.json")
WORKBOOK_NAME = ADMISSIONS_DOMAIN.workbook_path
SCHEMA_PATH = ADMISSIONS_DOMAIN.schema_path
TAXONOMY_PATH = ADMISSIONS_DOMAIN.rule_taxonomy_path
REQUIRED_COLUMNS = ADMISSIONS_DOMAIN.required_columns


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
    domain_name: str = "admissions"
    domain_path: str | None = None
    dataset_id: str | None = None


@dataclass(frozen=True)
class RankWindowSelection:
    """用户显式确认的位次窗口。"""

    label: str
    lower_percent: int
    upper_percent: int
    upper_only: bool = True


@dataclass(frozen=True)
class WorkbenchResponse:
    """前端可依赖的 Workbench 固定响应契约。"""

    schema_version: str
    domain: str
    domain_version: str
    domain_pack_status: str
    status: str
    query_type: str
    query: dict[str, Any]
    answer: str
    items: list[dict[str, Any]]
    top_results: list[dict[str, Any]]
    result_sections: dict[str, Any]
    result_count: int
    executed_filters: list[dict[str, Any]]
    candidates_to_confirm: list[dict[str, Any]]
    confirmed_rules: list[dict[str, Any]]
    unconfirmed_candidates: list[dict[str, Any]]
    unexecuted_preferences: list[dict[str, Any]]
    no_schema_field_preferences: list[dict[str, Any]]
    rejected_confirmations: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    evidence_pack: dict[str, Any]
    debug_trace: dict[str, Any]

    def __post_init__(self) -> None:
        if self.status not in WORKBENCH_STATUS_VALUES:
            raise ValueError(f"Unsupported workbench status: {self.status}")
        if self.domain_pack_status not in {
            "draft",
            "needs_review",
            "approved",
            "blocked",
        }:
            raise ValueError(
                f"Unsupported domain pack status: {self.domain_pack_status}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "domain": self.domain,
            "domain_version": self.domain_version,
            "domain_pack_status": self.domain_pack_status,
            "status": self.status,
            "query_type": self.query_type,
            "query": self.query,
            "answer": self.answer,
            "items": self.items,
            "top_results": self.top_results,
            "result_sections": self.result_sections,
            "result_count": self.result_count,
            "executed_filters": self.executed_filters,
            "candidates_to_confirm": self.candidates_to_confirm,
            "confirmed_rules": self.confirmed_rules,
            "unconfirmed_candidates": self.unconfirmed_candidates,
            "unexecuted_preferences": self.unexecuted_preferences,
            "no_schema_field_preferences": self.no_schema_field_preferences,
            "rejected_confirmations": self.rejected_confirmations,
            "warnings": self.warnings,
            "evidence_pack": self.evidence_pack,
            "debug_trace": self.debug_trace,
        }


def available_options() -> dict[str, Any]:
    """Return the user-facing option whitelist for API mode."""

    return {
        "extractors": _options(EXTRACTOR_OPTIONS),
        "generators": _options(GENERATOR_OPTIONS),
        "models": _options(MODEL_OPTIONS),
        "rank_windows": [dict(item) for item in RANK_WINDOW_OPTIONS],
        "sort_modes": _options(SORT_MODE_OPTIONS),
    }


def _domain_config(config: WorkbenchConfig) -> DomainConfig:
    if config.domain_path:
        return DomainConfig.from_path(config.domain_path, domain_id=config.domain_name)
    return DomainConfig.load(config.domain_name)


def _workbook_path(domain_config: DomainConfig) -> Path:
    if _is_builtin_admissions_domain(domain_config):
        return Path(WORKBOOK_NAME)
    return domain_config.workbook_path


def _warehouse_database_path(domain_config: DomainConfig) -> Path:
    if _is_builtin_admissions_domain(domain_config):
        return Path(WAREHOUSE_DATABASE_PATH)
    return domain_config.warehouse_database_path


def _warehouse_value_index_path(domain_config: DomainConfig) -> Path:
    if _is_builtin_admissions_domain(domain_config):
        return Path(WAREHOUSE_VALUE_INDEX_PATH)
    return domain_config.value_index_path


def _is_builtin_admissions_domain(domain_config: DomainConfig) -> bool:
    return (
        domain_config.domain_id == ADMISSIONS_DOMAIN.domain_id
        and domain_config.root.resolve() == ADMISSIONS_DOMAIN.root.resolve()
    )


def run_workbench(config: WorkbenchConfig) -> dict[str, Any]:
    """Run the verified pipeline and return UI-ready artifacts."""

    config = _normalize_config(config)
    try:
        return _run_workbench(config)
    except Exception as exc:  # noqa: BLE001 - API contract 不暴露内部 traceback。
        return _error_payload(config, exc)


def _run_workbench(config: WorkbenchConfig) -> dict[str, Any]:
    """在 contract 包装下运行已验证 pipeline。"""

    _validate_config(config)
    domain_config = _domain_config(config)
    if not _domain_pack_can_execute(domain_config):
        return _domain_pack_blocked_payload(config, domain_config)
    warehouse_audit = _data_warehouse_audit(domain_config)
    if not warehouse_audit["ok"]:
        return _data_warehouse_warning_payload(config, warehouse_audit)
    planned_result = _run_admissions_planned_query(config, domain_config)
    if planned_result is not None:
        return _planned_query_payload(
            config=config,
            domain_config=domain_config,
            warehouse_audit=warehouse_audit,
            planned_result=planned_result,
        )

    dataset = _load_dataset(domain_config)
    schema_registry = _load_schema_registry(tuple(dataset.headers), domain_config)
    value_index = _load_value_index(domain_config)
    slots, extractor_usage = _extract_slots(
        config,
        schema_registry=schema_registry,
        domain_config=domain_config,
    )
    verifier = RuleVerifier(schema_registry, domain_config=domain_config)
    attribute_grounding = AttributeGrounder(
        schema_registry,
        value_index=value_index,
        domain_config=domain_config,
    ).ground(slots)
    confirmation_candidates = _build_confirmation_candidates(
        user_request=_compose_user_request(config),
        attribute_grounding=attribute_grounding,
        domain_config=domain_config,
    )
    confirmation_state = _resolve_confirmed_candidates(
        confirmed_candidates=config.confirmed_candidates,
        confirmation_candidates=confirmation_candidates,
        verifier=verifier,
    )
    if _confirmation_blocks_execution(confirmation_state):
        return _confirmation_blocked_payload(
            config=config,
            warehouse_audit=warehouse_audit,
            slots=slots,
            extractor_usage=extractor_usage,
            attribute_grounding=attribute_grounding,
            confirmation_candidates=confirmation_candidates,
            confirmation_state=confirmation_state,
        )
    proposed_rules = verifier.audit_proposed_rules(slots.get("proposed_rules", []))
    classified_rules = RuleClassifier(
        domain_config.rule_taxonomy_path,
        verifier,
        domain_config=domain_config,
    ).classify(slots)
    classified_rules = _append_unmapped_preferences(classified_rules, slots)
    classified_rules = _append_grounding_non_executable_preferences(
        classified_rules,
        attribute_grounding,
        domain_config,
    )
    classified_rules["attribute_grounding"] = attribute_grounding
    classified_rules["proposed_rules"] = proposed_rules
    classified_rules["confirmation_state"] = confirmation_state
    classified_rules = _apply_soft_confirmations(
        classified_rules,
        config,
        slots,
        domain_config,
    )
    final_rules = RulePromoter(
        domain_config.rule_taxonomy_path,
        simulated_confirmation_enabled=True,
        domain_config=domain_config,
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
        domain_config=domain_config,
        config=config,
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
    extracted_preferences = _extracted_preferences(slots, domain_config)
    policy_references = _policy_references_for_config(config, domain_config)
    decision_guidance = _decision_guidance_for_payload(
        config,
        domain_config,
        slots,
    )
    base_no_schema_preferences = confirmation_state.get(
        "no_schema_field_preferences",
        [],
    )
    guidance_no_schema = _guidance_no_schema_preferences(
        decision_guidance,
        existing_preferences=base_no_schema_preferences,
    )
    guidance_not_executed = _guidance_not_executed_preferences(
        decision_guidance,
        guidance_no_schema,
    )
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
        domain_config=domain_config,
        policy_references=policy_references,
        decision_guidance=decision_guidance,
    )
    report, generator_usage = _generate_report(
        config=config,
        evidence=evidence,
        schema_registry=schema_registry,
        domain_config=domain_config,
    )

    legacy_payload = {
        "mode": "api",
        "status": "ok",
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "hard_filters": _display_hard_filters_for_domain(config, domain_config),
        "soft_preferences": _display_soft_preferences_for_domain(
            config,
            domain_config,
        ),
        "selected_options": _selected_options(config),
        "extracted_preferences": extracted_preferences,
        "extracted_slots": slots,
        "attribute_grounding": _display_attribute_grounding(
            attribute_grounding,
            domain_config,
        ),
        "confirmation_candidates": confirmation_candidates,
        "confirmation_state": _display_confirmation_state(confirmation_state),
        "proposed_rules": _display_proposed_rules(proposed_rules),
        "deterministic_rules": [_display_rule(rule) for rule in classified_rules["deterministic_rules"]],
        "candidate_rules": _candidate_rules(classified_rules),
        "not_executed_preferences": (
            _not_executed_preferences(
                classified_rules,
                domain_config,
            )
            + guidance_not_executed
        ),
        "no_schema_field_preferences": (
            base_no_schema_preferences
            + guidance_no_schema
        ),
        "simulated_confirmations": _simulated_confirmations(classified_rules),
        "executable_rules": [_executable_rule(rule) for rule in hard_rules],
        "execution": _display_execution_summary(execution.audit.to_dict()),
        "result_count": len(traced_results),
        "top_results": [
            _top_result(rank, row, domain_config)
            for rank, row in enumerate(traced_results[:EVIDENCE_TOP_K], start=1)
        ],
        "items": [
            _item_card(rank, row, hard_rules, domain_config)
            for rank, row in enumerate(traced_results[:EVIDENCE_TOP_K], start=1)
        ],
        "trace": {},
        "evidence_pack": evidence.to_dict(),
        "natural_language_report": _with_context_warnings(
            report,
            slots,
            domain_config,
        ),
        "token_usage": {
            "extractor": extractor_usage,
            "generator": generator_usage,
            "total": _sum_usage([extractor_usage, generator_usage]),
        },
    }
    return _contract_success_payload(
        legacy_payload=legacy_payload,
        hard_rules=hard_rules,
        confirmation_state=confirmation_state,
        config=config,
        domain_config=domain_config,
    )


def _run_admissions_planned_query(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> Any | None:
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return None
    return AdmissionsQueryPlanner(
        domain_config=domain_config,
        database_path=_warehouse_database_path(domain_config),
    ).run(config, _compose_user_request(config))


def _planned_rows_with_trace(
    rows: list[dict[str, Any]],
    hard_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    traced_rows = []
    for row in rows:
        traced = dict(row)
        traced["trace"] = [
            _planned_trace_item(rule, row)
            for rule in hard_rules
        ]
        traced_rows.append(traced)
    return traced_rows


def _planned_trace_item(
    rule: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    field = rule.get("field")
    return {
        "rule_id": rule.get("rule_id"),
        "field": field,
        "operator": rule.get("operator"),
        "value": rule.get("value"),
        "status": "pass",
        "reason": f"{field} {rule.get('operator')} {rule.get('value')} 已执行",
        "matched_value": row.get(str(field)) if field else None,
    }


def _planned_query_payload(
    *,
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    warehouse_audit: dict[str, Any],
    planned_result: Any,
) -> dict[str, Any]:
    hard_rules = list(planned_result.executed_rules)
    planned_rows = _planned_rows_with_trace(planned_result.rows, hard_rules)
    top_results = [
        _top_result(rank, row, domain_config)
        for rank, row in enumerate(planned_rows[:EVIDENCE_TOP_K], start=1)
    ]
    evidence_top_results = [
        dict(row)
        for row in planned_rows[:EVIDENCE_TOP_K]
    ]
    items = [
        _item_card(rank, row, hard_rules, domain_config)
        for rank, row in enumerate(planned_rows[:EVIDENCE_TOP_K], start=1)
    ]
    result_count = len(planned_rows)
    policy_references = _policy_references_for_config(config, domain_config)
    decision_guidance = _decision_guidance_for_payload(
        config,
        domain_config,
        _guidance_slots_for_payload(config, domain_config),
    )
    planned_no_schema_preferences = planned_result.no_schema_field_preferences
    guidance_no_schema = _guidance_no_schema_preferences(
        decision_guidance,
        existing_preferences=planned_no_schema_preferences,
    )
    guidance_not_executed = _guidance_not_executed_preferences(
        decision_guidance,
        guidance_no_schema,
    )
    combined_no_schema_preferences = (
        planned_no_schema_preferences
        + guidance_no_schema
    )
    answer = _append_policy_reference_answer(
        _append_decision_guidance_answer(
            _planned_answer_with_audit(
                planned_result.answer,
                hard_rules,
                combined_no_schema_preferences,
            ),
            decision_guidance,
        ),
        policy_references,
    )
    evidence_pack = {
        "user_request": _compose_user_request(config),
        "query_type": planned_result.query_type,
        "executed_rules": hard_rules,
        "candidate_confirmations": planned_result.candidates_to_confirm,
        "not_executed_preferences": (
            planned_no_schema_preferences
            + guidance_not_executed
        ),
        "result_count": result_count,
        "top_k_results": evidence_top_results,
        "result_sections": planned_result.result_sections,
        "trace_summary": {
            "executed_rule_ids": [
                rule.get("rule_id")
                for rule in hard_rules
            ],
            "top_k": EVIDENCE_TOP_K,
            "query_type": planned_result.query_type,
            "result_count": result_count,
            "traced_result_count": result_count,
        },
        "extracted_preferences": planned_result.extracted_preferences,
        "attribute_grounding_summary": {},
        "proposed_rule_audit": [],
        "execution_summary": planned_result.execution_summary,
        "attribute_explanations": [],
        "confirmed_rules": [],
        "confirmation_source": [],
        "executed_after_confirmation": [],
        "unconfirmed_candidates": planned_result.candidates_to_confirm,
        "no_schema_field_preferences": combined_no_schema_preferences,
        "rejected_confirmations": [],
        "policy_references": policy_references,
        "decision_guidance": decision_guidance,
    }
    legacy_payload = {
        "mode": "api",
        "status": planned_result.status,
        "query_type": planned_result.query_type,
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "hard_filters": _display_hard_filters_for_domain(config, domain_config),
        "soft_preferences": _display_soft_preferences_for_domain(
            config,
            domain_config,
        ),
        "selected_options": _selected_options(config),
        "extracted_preferences": planned_result.extracted_preferences,
        "extracted_slots": {},
        "attribute_grounding": {"summary": {}, "attributes": []},
        "confirmation_candidates": planned_result.candidates_to_confirm,
        "confirmation_state": {
            "requested_candidate_ids": list(config.confirmed_candidates),
            "accepted_candidate_ids": [],
            "rejected_candidates": [],
            "confirmed_rules": [],
            "confirmation_source": [],
            "executed_after_confirmation": [],
            "unconfirmed_candidates": planned_result.candidates_to_confirm,
            "no_schema_field_preferences": combined_no_schema_preferences,
        },
        "proposed_rules": [],
        "deterministic_rules": [_display_rule(rule) for rule in hard_rules],
        "candidate_rules": planned_result.candidates_to_confirm,
        "not_executed_preferences": [
            _planned_not_executed_preference(index, item)
            for index, item in enumerate(
                planned_no_schema_preferences,
                start=1,
            )
        ] + guidance_not_executed,
        "simulated_confirmations": {},
        "executable_rules": [_executable_rule(rule) for rule in hard_rules],
        "execution": _display_execution_summary(planned_result.execution_summary),
        "result_count": result_count,
        "items": items,
        "top_results": top_results,
        "result_sections": planned_result.result_sections,
        "trace": {},
        "evidence_pack": evidence_pack,
        "natural_language_report": {
            "title": "Admissions query planner 结果",
            "summary": answer,
            "full_text": answer,
            "result_count_text": f"当前返回 {result_count} 条结果。",
            "executed_rules": [_rule_label(rule) for rule in hard_rules],
            "attribute_explanations": [],
            "top_results": top_results,
            "warnings": planned_result.warnings,
            "disclaimer": _planned_query_disclaimer(planned_result),
        },
        "token_usage": {
            "extractor": None,
            "generator": None,
            "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    }
    response = WorkbenchResponse(
        schema_version=WORKBENCH_SCHEMA_VERSION,
        domain=domain_config.domain_id,
        domain_version=domain_config.domain_version,
        domain_pack_status=domain_config.pack_status,
        status=planned_result.status,
        query_type=planned_result.query_type,
        query=_contract_query(config),
        answer=answer,
        items=items,
        top_results=top_results,
        result_sections=planned_result.result_sections,
        result_count=result_count,
        executed_filters=[_display_rule(rule) for rule in hard_rules],
        candidates_to_confirm=planned_result.candidates_to_confirm,
        confirmed_rules=[],
        unconfirmed_candidates=planned_result.candidates_to_confirm,
        unexecuted_preferences=legacy_payload["not_executed_preferences"],
        no_schema_field_preferences=combined_no_schema_preferences,
        rejected_confirmations=[],
        warnings=_contract_warnings(
            planned_result.warnings,
            status=planned_result.status,
            confirmation_state=legacy_payload["confirmation_state"],
        ),
        evidence_pack=evidence_pack,
        debug_trace=_debug_trace(legacy_payload),
    ).to_dict()
    return {**legacy_payload, **response}


def _planned_query_disclaimer(planned_result: Any) -> str:
    warning_codes = {item.get("code") for item in planned_result.warnings}
    if "score_without_rank" in warning_codes:
        return "只给分数时不会执行 recommendation SQL；请补充广东省排位/位次。"
    return "推荐分组基于历史最低分/最低位次，不代表录取概率。"


def _planned_answer_with_audit(
    answer: str,
    hard_rules: list[dict[str, Any]],
    no_schema_preferences: list[dict[str, Any]],
) -> str:
    lines = [answer, "", "字段值审计解释："]
    for rule in hard_rules:
        lines.append(
            "- "
            f"[已执行] {rule.get('value')} -> {rule.get('field')}："
            f"{rule.get('operator')}"
        )
    for preference in no_schema_preferences:
        lines.append(
            "- "
            f"[未执行] {preference.get('source_text')} -> "
            f"{preference.get('field')}：no_schema_field"
        )
    lines.extend(["", "已执行规则："])
    for rule in hard_rules:
        lines.append(
            "- "
            f"{rule.get('rule_id')}：{rule.get('field')} "
            f"{rule.get('operator')} {rule.get('value')}"
        )
    return "\n".join(lines)


def _policy_references_for_config(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> list[dict[str, Any]]:
    return policy_references_for_query(domain_config, _compose_user_request(config))


def _append_policy_reference_answer(
    answer: str,
    policy_references: list[dict[str, Any]],
) -> str:
    if not policy_references:
        return answer
    lines = [answer, "", "参考说明（不参与筛选）："]
    for reference in policy_references:
        terms = "、".join(str(item) for item in reference.get("matched_terms") or [])
        lines.append(
            "- "
            f"{reference.get('title')}：{reference.get('excerpt')}；"
            f"来源：{reference.get('source')}；命中：{terms}；该说明不参与筛选。"
        )
    return "\n".join(lines)


def _append_decision_guidance_answer(
    answer: str,
    decision_guidance: dict[str, Any],
) -> str:
    if not decision_guidance.get("matched_rules"):
        return answer
    lines = [answer, "", "就业与家庭资源说明（不参与筛选）："]
    lines.extend(
        _decision_guidance_line(item)
        for item in decision_guidance.get("matched_rules", [])
    )
    if decision_guidance.get("information_requests"):
        lines.extend(["", "需要补充的信息："])
        lines.extend(
            _information_request_line(item)
            for item in decision_guidance["information_requests"]
        )
    return "\n".join(lines)


def _decision_guidance_for_payload(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return career_guidance_for_query(
        _compose_user_request(config),
        slots or {},
        domain_config,
    )


def _guidance_slots_for_payload(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return {}
    prompt = _soft_prompt(config) or config.user_input or _compose_user_request(config)
    slots = RegexExtractor(alias_path=domain_config.value_aliases_path).extract(prompt)
    return _slots_from_inputs(slots, config=config)


def _guidance_not_executed_preferences(
    guidance: dict[str, Any],
    no_schema_preferences: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    items = []
    for index, item in enumerate(
        no_schema_preferences
        if no_schema_preferences is not None
        else guidance.get("no_schema_field_preferences") or [],
        start=1,
    ):
        source_text = str(item.get("source_text") or "就业偏好")
        reason = str(item.get("reason") or "当前数据中没有可执行字段。")
        items.append(
            {
                "id": f"career_guidance_not_exec_{index}",
                "source_text": source_text,
                "preference": source_text,
                "display": f"{source_text}未执行：{reason}",
                "reason": reason,
                "missing_field": (
                    item.get("field")
                    or item.get("field_id")
                    or "缺少已审查数据字段"
                ),
                "source_span": source_text,
            }
        )
    return items


def _guidance_no_schema_preferences(
    guidance: dict[str, Any],
    existing_preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _records_without_existing_preference_keys(
        guidance.get("no_schema_field_preferences") or [],
        existing_preferences,
    )


def _records_without_existing_preference_keys(
    records: list[dict[str, Any]],
    existing_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = {
        key
        for item in existing_records
        if (key := _preference_record_key(item)) is not None
    }
    output = []
    for item in records:
        key = _preference_record_key(item)
        if key is not None and key in seen:
            continue
        output.append(item)
        if key is not None:
            seen.add(key)
    return output


def _preference_record_key(item: dict[str, Any]) -> tuple[str, str] | None:
    source_text = item.get("source_text") or item.get("source_span")
    if source_text in (None, ""):
        source_text = item.get("preference")
    if source_text in (None, ""):
        return None
    field_id = item.get("field_id")
    if field_id not in (None, ""):
        return (str(field_id), str(source_text))
    return ("source_text", str(source_text))


def _decision_guidance_line(item: dict[str, Any]) -> str:
    return (
        f"- {item.get('label')}：该规则只进入解释证据，"
        "不改变 SQL、不改变结果数量。"
    )


def _information_request_line(item: dict[str, Any]) -> str:
    options = item.get("fixed_options") or []
    option_text = (
        f"固定选项：{'、'.join(str(option) for option in options)}。"
        if options
        else ""
    )
    return f"- {item.get('label')}：{item.get('question')}{option_text}"


def _planned_not_executed_preference(
    index: int,
    item: dict[str, Any],
) -> dict[str, Any]:
    source_text = str(item.get("source_text") or "该偏好")
    reason = str(item.get("reason") or "缺少可执行字段。")
    return {
        "id": f"planned_not_exec_{index}",
        "preference": source_text,
        "display": f"{source_text}未执行：{reason}",
        "reason": reason,
        "missing_field": item.get("field_id") or "缺少已审查数据字段",
        "source_span": source_text,
    }


def _contract_success_payload(
    legacy_payload: dict[str, Any],
    hard_rules: list[dict[str, Any]],
    confirmation_state: dict[str, Any],
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    status = _success_status(legacy_payload, confirmation_state)
    no_schema_preferences = legacy_payload.get("no_schema_field_preferences")
    if no_schema_preferences is None:
        no_schema_preferences = confirmation_state.get(
            "no_schema_field_preferences",
            [],
        )
    response = WorkbenchResponse(
        schema_version=WORKBENCH_SCHEMA_VERSION,
        domain=domain_config.domain_id,
        domain_version=domain_config.domain_version,
        domain_pack_status=domain_config.pack_status,
        status=status,
        query_type=str(legacy_payload.get("query_type") or "verified_filter"),
        query=_contract_query(config),
        answer=legacy_payload["natural_language_report"]["full_text"],
        items=legacy_payload["items"],
        top_results=legacy_payload["top_results"],
        result_sections=legacy_payload.get("result_sections") or {},
        result_count=legacy_payload["result_count"],
        executed_filters=[_display_rule(rule) for rule in hard_rules],
        candidates_to_confirm=confirmation_state.get("unconfirmed_candidates", []),
        confirmed_rules=_contract_confirmed_rules(confirmation_state),
        unconfirmed_candidates=confirmation_state.get("unconfirmed_candidates", []),
        unexecuted_preferences=legacy_payload["not_executed_preferences"],
        no_schema_field_preferences=no_schema_preferences,
        rejected_confirmations=confirmation_state.get("rejected_candidates", []),
        warnings=_contract_warnings(
            legacy_payload.get("natural_language_report", {}).get("warnings", []),
            status=status,
            confirmation_state=confirmation_state,
        ),
        evidence_pack=legacy_payload["evidence_pack"],
        debug_trace=_debug_trace(legacy_payload),
    ).to_dict()
    return {**legacy_payload, **response}


def _success_status(
    legacy_payload: dict[str, Any],
    confirmation_state: dict[str, Any],
) -> str:
    execution = legacy_payload.get("execution") or {}
    if (
        execution.get("executor")
        and int(execution.get("filtered_row_count") or 0) == 0
    ):
        return "no_results"
    if confirmation_state.get("unconfirmed_candidates"):
        return "needs_confirmation"
    evidence = legacy_payload.get("evidence_pack") or {}
    if any(
        explanation.get("action") == "needs_confirmation"
        for explanation in evidence.get("attribute_explanations", [])
    ):
        return "needs_confirmation"
    return "ok"


def _contract_confirmed_rules(
    confirmation_state: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            **_display_rule(rule),
            "candidate_id": rule.get("derived_from"),
            "executed": rule.get("rule_id")
            in set(confirmation_state.get("executed_after_confirmation") or []),
            "confirmation_source": rule.get("confirmation_source"),
        }
        for rule in confirmation_state.get("confirmed_rules", [])
    ]


def _contract_warnings(
    raw_warnings: list[Any],
    status: str,
    confirmation_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings = [_normalize_warning(item) for item in raw_warnings]
    has_unconfirmed_candidates = bool(
        (confirmation_state or {}).get("unconfirmed_candidates")
    )
    if status == "needs_confirmation" and has_unconfirmed_candidates:
        warnings.append(
            {
                "code": "needs_confirmation",
                "severity": "warning",
                "message": "存在未确认 partial_match candidate，未进入 hard filter。",
            }
        )
    if status == "no_results":
        warnings.append(
            {
                "code": "no_results",
                "severity": "warning",
                "message": "SQL 正常执行但 filtered_row_count 为 0，不能生成推荐。",
            }
        )
    for item in (confirmation_state or {}).get("rejected_candidates", []):
        warnings.append(
            {
                "code": item.get("reason_code") or "rejected_confirmation",
                "severity": "warning",
                "message": item.get("reason") or "candidate_id 未被接受。",
                "candidate_id": item.get("candidate_id"),
            }
        )
    return warnings


def _normalize_warning(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "code": item.get("code") or "warning",
            "severity": item.get("severity") or "warning",
            "message": item.get("message") or str(item),
            **{
                key: value
                for key, value in item.items()
                if key not in {"code", "severity", "message"}
            },
        }
    return {
        "code": "report_warning",
        "severity": "warning",
        "message": str(item),
    }


def _debug_trace(payload: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "mode",
        "query_type",
        "user_input",
        "data_warehouse",
        "hard_filters",
        "soft_preferences",
        "selected_options",
        "extracted_preferences",
        "extracted_slots",
        "attribute_grounding",
        "confirmation_candidates",
        "confirmation_state",
        "proposed_rules",
        "deterministic_rules",
        "candidate_rules",
        "not_executed_preferences",
        "simulated_confirmations",
        "executable_rules",
        "execution",
        "trace",
        "items",
        "result_sections",
        "natural_language_report",
        "token_usage",
    ]
    return {key: payload.get(key) for key in keys if key in payload}


def _data_warehouse_audit(domain_config: DomainConfig) -> dict[str, Any]:
    return audit_data_warehouse_fingerprints(
        workbook_path=_workbook_path(domain_config),
        database_path=_warehouse_database_path(domain_config),
        index_path=_warehouse_value_index_path(domain_config),
        table_name=domain_config.table_name,
    )


def _data_warehouse_warning_payload(
    config: WorkbenchConfig,
    warehouse_audit: dict[str, Any],
) -> dict[str, Any]:
    domain_config = _domain_config(config)
    messages = [
        str(warning.get("message"))
        for warning in warehouse_audit.get("warnings", [])
    ]
    full_text = "\n".join(
        ["数据仓库 fingerprint guard 未通过，未执行筛选。"]
        + [f"- {message}" for message in messages]
    )
    legacy_payload = {
        "mode": "api",
        "status": "blocked",
        "warning_type": "data_warehouse_fingerprint_guard",
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "structured_warnings": warehouse_audit.get("warnings", []),
        "warnings": warehouse_audit.get("warnings", []),
        "hard_filters": _display_hard_filters_for_domain(config, domain_config),
        "soft_preferences": _display_soft_preferences_for_domain(
            config,
            domain_config,
        ),
        "selected_options": _selected_options(config),
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
        "items": [],
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
    return _contract_blocked_payload(legacy_payload, config, domain_config)


def _domain_pack_can_execute(domain_config: DomainConfig) -> bool:
    return domain_config.pack_status == "approved"


def _domain_pack_blocked_payload(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    message = (
        f"domain pack 状态为 {domain_config.pack_status}，未 approve 前不能执行 SQL。"
    )
    legacy_payload = {
        "mode": "api",
        "status": "blocked",
        "warning_type": "domain_pack_status_guard",
        "user_input": _compose_user_request(config),
        "data_warehouse": {},
        "structured_warnings": [
            {
                "code": "domain_pack_not_approved",
                "message": message,
                "severity": "error",
                "domain": domain_config.domain_id,
                "domain_pack_status": domain_config.pack_status,
            }
        ],
        "warnings": [
            {
                "code": "domain_pack_not_approved",
                "message": message,
                "severity": "error",
                "domain": domain_config.domain_id,
                "domain_pack_status": domain_config.pack_status,
            }
        ],
        "hard_filters": _display_hard_filters_for_domain(config, domain_config),
        "soft_preferences": _display_soft_preferences_for_domain(
            config,
            domain_config,
        ),
        "selected_options": _selected_options(config),
        "extracted_preferences": [],
        "extracted_slots": {},
        "attribute_grounding": {"summary": {}, "attributes": []},
        "confirmation_candidates": [],
        "confirmation_state": _display_confirmation_state({}),
        "proposed_rules": [],
        "deterministic_rules": [],
        "candidate_rules": [],
        "not_executed_preferences": [],
        "simulated_confirmations": {},
        "executable_rules": [],
        "execution": _blocked_execution_summary(),
        "result_count": 0,
        "items": [],
        "top_results": [],
        "trace": {},
        "evidence_pack": {},
        "natural_language_report": {
            "title": "Domain pack 未启用",
            "summary": message,
            "full_text": message,
            "result_count_text": "当前未执行筛选，结果数为 0。",
            "executed_rules": [],
            "attribute_explanations": [],
            "top_results": [],
            "warnings": [message],
            "disclaimer": "draft/needs_review domain pack 不能执行 hard filters。",
        },
        "token_usage": {
            "extractor": None,
            "generator": None,
            "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    }
    return _contract_blocked_payload(legacy_payload, config, domain_config)


def _confirmation_blocked_payload(
    config: WorkbenchConfig,
    warehouse_audit: dict[str, Any],
    slots: dict[str, Any],
    extractor_usage: dict[str, int] | None,
    attribute_grounding: dict[str, Any],
    confirmation_candidates: list[dict[str, Any]],
    confirmation_state: dict[str, Any],
) -> dict[str, Any]:
    domain_config = _domain_config(config)
    rejected = confirmation_state.get("rejected_candidates", [])
    messages = [
        item.get("reason") or "candidate_id 未被接受。"
        for item in rejected
        if item.get("blocks_execution")
    ]
    full_text = "\n".join(
        ["candidate_id 确认失败，Workbench 未执行 SQL。"]
        + [f"- {message}" for message in messages]
    )
    legacy_payload = {
        "mode": "api",
        "status": "blocked",
        "warning_type": "candidate_confirmation_guard",
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "structured_warnings": [
            {
                "code": item.get("reason_code")
                or "candidate_id_not_current_query",
                "message": item.get("reason") or "candidate_id 未被接受。",
                "severity": "error",
                "candidate_id": item.get("candidate_id"),
            }
            for item in rejected
            if item.get("blocks_execution")
        ],
        "warnings": [
            {
                "code": item.get("reason_code")
                or "candidate_id_not_current_query",
                "message": item.get("reason") or "candidate_id 未被接受。",
                "severity": "error",
                "candidate_id": item.get("candidate_id"),
            }
            for item in rejected
            if item.get("blocks_execution")
        ],
        "hard_filters": _display_hard_filters_for_domain(config, domain_config),
        "soft_preferences": _display_soft_preferences_for_domain(
            config,
            domain_config,
        ),
        "selected_options": _selected_options(config),
        "extracted_preferences": _extracted_preferences(slots, domain_config),
        "extracted_slots": slots,
        "attribute_grounding": _display_attribute_grounding(
            attribute_grounding,
            domain_config,
        ),
        "confirmation_candidates": confirmation_candidates,
        "confirmation_state": _display_confirmation_state(confirmation_state),
        "proposed_rules": [],
        "deterministic_rules": [],
        "candidate_rules": [],
        "not_executed_preferences": [],
        "simulated_confirmations": {},
        "executable_rules": [],
        "execution": _blocked_execution_summary(),
        "result_count": 0,
        "items": [],
        "top_results": [],
        "trace": {},
        "evidence_pack": {},
        "natural_language_report": {
            "title": "确认请求被阻断",
            "summary": "收到伪造、过期或不属于当前 query 的 candidate_id。",
            "full_text": full_text,
            "result_count_text": "当前未执行筛选，结果数为 0。",
            "executed_rules": [],
            "attribute_explanations": [],
            "top_results": [],
            "warnings": messages,
            "disclaimer": "只能提交上一轮同一 query 由系统生成的 candidate_id。",
        },
        "token_usage": {
            "extractor": extractor_usage,
            "generator": None,
            "total": _sum_usage([extractor_usage]),
        },
    }
    return _contract_blocked_payload(legacy_payload, config, domain_config)


def _contract_blocked_payload(
    legacy_payload: dict[str, Any],
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    warnings = legacy_payload.get("warnings", [])
    response = WorkbenchResponse(
        schema_version=WORKBENCH_SCHEMA_VERSION,
        domain=domain_config.domain_id,
        domain_version=domain_config.domain_version,
        domain_pack_status=domain_config.pack_status,
        status="blocked",
        query_type=str(legacy_payload.get("query_type") or "verified_filter"),
        query=_contract_query(config),
        answer=legacy_payload["natural_language_report"]["full_text"],
        items=[],
        top_results=[],
        result_sections=legacy_payload.get("result_sections") or {},
        result_count=0,
        executed_filters=[],
        candidates_to_confirm=(
            legacy_payload.get("confirmation_state", {}) or {}
        ).get("unconfirmed_candidates", []),
        confirmed_rules=[],
        unconfirmed_candidates=(
            legacy_payload.get("confirmation_state", {}) or {}
        ).get("unconfirmed_candidates", []),
        unexecuted_preferences=legacy_payload.get("not_executed_preferences", []),
        no_schema_field_preferences=(
            legacy_payload.get("confirmation_state", {}) or {}
        ).get("no_schema_field_preferences", []),
        rejected_confirmations=(
            legacy_payload.get("confirmation_state", {}) or {}
        ).get("rejected_candidates", []),
        warnings=_contract_warnings(warnings, status="blocked"),
        evidence_pack=legacy_payload.get("evidence_pack", {}),
        debug_trace=_debug_trace(legacy_payload),
    ).to_dict()
    return {**legacy_payload, **response}


def _blocked_execution_summary() -> dict[str, Any]:
    return {
        "executor": None,
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
        "sort_key": [],
        "top_k": EVIDENCE_TOP_K,
        "hard_rule_ids": [],
        "skipped_soft_rule_ids": [],
    }


def _error_payload(config: WorkbenchConfig, exc: Exception) -> dict[str, Any]:
    message = (
        _sanitize_user_text(str(exc))
        if isinstance(exc, ValueError)
        else "Workbench 运行失败，前端不应展示内部异常细节。"
    )
    legacy_payload = {
        "mode": "api",
        "status": "error",
        "warning_type": "workbench_error",
        "user_input": _compose_user_request(config),
        "data_warehouse": {},
        "structured_warnings": [
            {
                "code": "workbench_error",
                "message": message,
                "severity": "error",
                "error_type": type(exc).__name__,
            }
        ],
        "warnings": [
            {
                "code": "workbench_error",
                "message": message,
                "severity": "error",
                "error_type": type(exc).__name__,
            }
        ],
        "hard_filters": dict(config.hard_filters),
        "soft_preferences": dict(config.soft_preferences),
        "selected_options": _selected_options(config),
        "extracted_preferences": [],
        "extracted_slots": {},
        "attribute_grounding": {"summary": {}, "attributes": []},
        "confirmation_candidates": [],
        "confirmation_state": _display_confirmation_state({}),
        "proposed_rules": [],
        "deterministic_rules": [],
        "candidate_rules": [],
        "not_executed_preferences": [],
        "simulated_confirmations": {},
        "executable_rules": [],
        "execution": _blocked_execution_summary(),
        "result_count": 0,
        "items": [],
        "top_results": [],
        "trace": {},
        "evidence_pack": {},
        "natural_language_report": {
            "title": "Workbench 运行失败",
            "summary": "运行过程中出现非预期错误。",
            "full_text": "Workbench 运行失败，未返回推荐结果。",
            "result_count_text": "当前未执行筛选，结果数为 0。",
            "executed_rules": [],
            "attribute_explanations": [],
            "top_results": [],
            "warnings": [message],
            "disclaimer": "前端不会收到服务端 traceback。",
        },
        "token_usage": {
            "extractor": None,
            "generator": None,
            "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    }
    response = WorkbenchResponse(
        schema_version=WORKBENCH_SCHEMA_VERSION,
        domain=config.domain_name,
        domain_version="unknown",
        domain_pack_status="blocked",
        status="error",
        query_type="unknown",
        query=_contract_query(config),
        answer=legacy_payload["natural_language_report"]["full_text"],
        items=[],
        top_results=[],
        result_sections={},
        result_count=0,
        executed_filters=[],
        candidates_to_confirm=[],
        confirmed_rules=[],
        unconfirmed_candidates=[],
        unexecuted_preferences=[],
        no_schema_field_preferences=[],
        rejected_confirmations=[],
        warnings=_contract_warnings(legacy_payload["warnings"], status="error"),
        evidence_pack={},
        debug_trace=_debug_trace(legacy_payload),
    ).to_dict()
    return {**legacy_payload, **response}


def _load_dataset(domain_config: DomainConfig) -> ExcelDataSet:
    database_path = _warehouse_database_path(domain_config)
    if not database_path.exists():
        raise RuntimeError("DuckDB 数据仓库不存在，Workbench 不执行静默 Excel 回退。")
    stat = database_path.stat()
    return _load_warehouse_dataset_cached(
        str(database_path),
        stat.st_mtime_ns,
        stat.st_size,
        tuple(domain_config.required_columns),
        domain_config.table_name,
    )


@lru_cache(maxsize=1)
def _load_warehouse_dataset_cached(
    database_path: str,
    modified_ns: int,
    file_size: int,
    required_columns: tuple[str, ...],
    table_name: str,
) -> ExcelDataSet:
    _ = (modified_ns, file_size)
    return load_structured_dataset(
        database_path,
        list(required_columns),
        table_name=table_name,
    )


def _execute_verified_hard_rules(
    executable_rules: list[dict[str, Any]],
    user_rank: int | None,
    top_k: int,
    domain_config: DomainConfig,
    config: WorkbenchConfig,
) -> ExecutionResult:
    database_path = _warehouse_database_path(domain_config)
    if not database_path.exists():
        raise RuntimeError("DuckDB 数据仓库不存在，Workbench 不执行静默 Pandas 回退。")
    return DuckDBExecutor(
        database_path,
        table_name=domain_config.table_name,
        domain_config=domain_config,
    ).execute(
        executable_rules,
        user_rank=user_rank,
        top_k=top_k,
        sort_policy_override=_admissions_sort_policy(config),
    )


def _admissions_sort_policy(config: WorkbenchConfig) -> list[dict[str, Any]] | None:
    if config.domain_name != ADMISSIONS_DOMAIN.domain_id or config.domain_path:
        return None
    sort_mode = _clean_text(config.soft_preferences.get("sort_mode"))
    if sort_mode in SORT_MODE_OPTIONS and sort_mode in ADMISSIONS_SORT_POLICIES:
        return ADMISSIONS_SORT_POLICIES[sort_mode]
    return None


def _load_schema_registry(
    headers: tuple[str, ...],
    domain_config: DomainConfig,
) -> SchemaRegistry:
    schema_path = Path(domain_config.schema_path)
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


def _load_value_index(domain_config: DomainConfig) -> SchemaValueIndex | None:
    index_path = _warehouse_value_index_path(domain_config)
    if not index_path.exists():
        return None
    stat = index_path.stat()
    return _load_value_index_cached(
        str(index_path),
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


def _normalize_config(config: WorkbenchConfig) -> WorkbenchConfig:
    extractor = EXTRACTOR_ALIASES.get(config.extractor, config.extractor)
    if extractor == config.extractor:
        return config
    return replace(config, extractor=extractor)


def _selected_options(config: WorkbenchConfig) -> dict[str, str]:
    return {
        "extractor": EXTRACTOR_OPTIONS.get(config.extractor, str(config.extractor)),
        "generator": GENERATOR_OPTIONS.get(config.generator, str(config.generator)),
        "model": MODEL_OPTIONS.get(config.model, str(config.model)),
        "domain": config.domain_name,
    }


def _contract_query(config: WorkbenchConfig) -> dict[str, Any]:
    return {
        "text": _compose_user_request(config),
        "domain": config.domain_name,
        "dataset_id": config.dataset_id,
        "query_type": config.hard_filters.get("query_type"),
        "hard_filters": dict(config.hard_filters),
        "soft_preferences": dict(config.soft_preferences),
        "confirmed_candidates": list(config.confirmed_candidates),
    }


def _extract_slots(
    config: WorkbenchConfig,
    schema_registry: SchemaRegistry | None = None,
    domain_config: DomainConfig | None = None,
) -> tuple[dict[str, Any], dict[str, int] | None]:
    domain_config = domain_config or _domain_config(config)
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return _generic_domain_slots(config), None
    soft_prompt = _soft_prompt(config)
    if config.extractor == "regex":
        return _slots_from_inputs(
            RegexExtractor(alias_path=domain_config.value_aliases_path).extract(
                soft_prompt
            ),
            config=config,
        ), None
    if config.extractor == "hybrid":
        client = (
            _interactive_deepseek_client(config.model)
            if deepseek_slot_adapter_enabled()
            else None
        )
        slots = _slots_from_inputs(
            ExtractorFallbackPipeline(
                deterministic_extractor=RegexExtractor(
                    alias_path=domain_config.value_aliases_path
                ),
                fallback_extractor=(
                    DeepSeekSlotAdapter.from_client(client)
                    if client is not None
                    else None
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

    slots = _slots_from_inputs(
        ExtractorFallbackPipeline(
            deterministic_extractor=RegexExtractor(
                alias_path=domain_config.value_aliases_path
            ),
            fallback_extractor=(
                DeepSeekSlotAdapter.from_client(
                    _interactive_deepseek_client(config.model)
                )
                if deepseek_slot_adapter_enabled()
                else None
            ),
            fallback_enabled=deepseek_slot_adapter_enabled(),
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


def _generate_report(
    config: WorkbenchConfig,
    evidence: EvidencePack,
    schema_registry: SchemaRegistry,
    domain_config: DomainConfig,
) -> tuple[dict[str, Any], dict[str, int] | None]:
    evidence_dict = evidence.to_dict()

    if config.generator == "template_evidence" or not llm_runtime_enabled():
        answer = TemplateReportBuilder(domain_config=domain_config).build(evidence)
        return _report_from_answer(answer, evidence_dict, domain_config), None

    client = _interactive_deepseek_client(config.model)
    payload = DeepSeekAnswerGenerator(client=client).generate(evidence)
    return (
        _report_from_answer(payload["answer"], evidence_dict, domain_config),
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

    rank_window = _rank_window_selection(soft)
    if rank_window:
        preferences["risk_preference_raw"] = (
            preferences.get("risk_preference_raw")
            or f"已选择{_rank_window_boundary_text(rank_window)}"
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


def _generic_domain_slots(config: WorkbenchConfig) -> dict[str, Any]:
    """把非招生 toy domain 的结构化输入作为 slots 进入同一验证管线。"""

    preferences = {
        key: value
        for key, value in {
            **config.hard_filters,
            **{
                key: value
                for key, value in config.soft_preferences.items()
                if key != "prompt"
            },
        }.items()
        if value not in (None, "", [])
    }
    return {
        "input": _compose_user_request(config),
        "user_context": {},
        "preferences": preferences,
        "raw_sources": {
            f"preferences.{key}": value
            for key, value in preferences.items()
        },
        "raw_phrases": [
            str(value)
            for value in preferences.values()
            if value not in (None, "", [])
        ],
    }


def _apply_soft_confirmations(
    classified_rules: dict[str, Any],
    config: WorkbenchConfig,
    slots: dict[str, Any],
    domain_config: DomainConfig | None = None,
) -> dict[str, Any]:
    domain_config = domain_config or _domain_config(config)
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return classified_rules
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

    rank_window = _rank_window_selection(soft)
    user_rank = _optional_int(slots.get("user_context", {}).get("user_rank"))
    rank_field = domain_config.source_column_or_none("group_min_rank_2024")
    if (
        rank_window
        and "c_safety_margin" in candidate_rule_ids
        and user_rank
        and rank_field
    ):
        lower_bound = max(
            1,
            int(user_rank * (1 - rank_window.lower_percent / 100)),
        )
        upper_bound = int(user_rank * (1 + rank_window.upper_percent / 100))
        if rank_window.upper_only:
            simulated["safety_margin"] = {
                "selected_option": f"+{rank_window.upper_percent}%",
                "label": _rank_window_boundary_text(rank_window),
                "field": rank_field,
                "operator": "<=",
                "value": upper_bound,
                "source_expression": (
                    f"{user_rank} * {1 + rank_window.upper_percent / 100:.2f}"
                ),
            }
        else:
            simulated["safety_margin"] = {
                "selected_option": (
                    f"-{rank_window.lower_percent}%/+{rank_window.upper_percent}%"
                ),
                "label": _rank_window_boundary_text(rank_window),
                "field": rank_field,
                "operator": "between",
                "value": [lower_bound, upper_bound],
                "source_expression": (
                    f"{user_rank} * {1 - rank_window.lower_percent / 100:.2f} 到 "
                    f"{user_rank} * {1 + rank_window.upper_percent / 100:.2f}"
                ),
            }

    tuition_cap = _optional_int(soft.get("tuition_cap_yuan"))
    tuition_field = domain_config.source_column_or_none("tuition_yuan_per_year")
    if (
        tuition_cap in {10000, 20000, 40000}
        and "c_tuition_cap" in candidate_rule_ids
        and tuition_field
    ):
        simulated["tuition_threshold"] = {
            "selected_option": str(tuition_cap),
            "label": f"不高于 {tuition_cap} 元/年",
            "field": tuition_field,
            "operator": "<=",
            "value": tuition_cap,
        }

    if "c_major_expansion" in candidate_rule_ids:
        if bool(soft.get("major_expansion")):
            simulated["major_expansion"] = {
                "selected_option": "expand",
                "label": "扩展到相关专业",
                "expanded_terms": domain_config.workbench.get(
                    "major_expansion_terms",
                    [],
                ),
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
    domain_config: DomainConfig,
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
        mapping = _reviewed_candidate_mapping(record, domain_config)
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
                    "reason_code": "candidate_id_not_current_query",
                    "blocks_execution": True,
                    "reason": "candidate_id 不属于当前 query，或不是系统上一轮生成的候选。",
                }
            )
            continue
        if not candidate.get("executable"):
            rejected_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_text": candidate.get("source_text"),
                    "reason_code": "candidate_not_executable",
                    "blocks_execution": False,
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
                    "reason_code": "candidate_rule_not_verified",
                    "blocks_execution": False,
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


def _confirmation_blocks_execution(confirmation_state: dict[str, Any]) -> bool:
    return any(
        bool(item.get("blocks_execution"))
        for item in confirmation_state.get("rejected_candidates", [])
    )


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


def _reviewed_candidate_mapping(
    record: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any] | None:
    field_id = record.get("field_id")
    source_text = _display_record_source_text(record)
    for mapping in domain_config.workbench.get("reviewed_candidate_mappings") or []:
        source_texts = set(mapping.get("source_texts") or [])
        if mapping.get("source_text"):
            source_texts.add(str(mapping["source_text"]))
        if mapping.get("field_id") == field_id and source_text in source_texts:
            return {
                "operator": mapping.get("operator"),
                "value": mapping.get("value"),
                "label": mapping.get("label"),
                "reason": mapping.get("reason"),
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
    domain_config: DomainConfig | None = None,
) -> dict[str, Any]:
    domain_config = domain_config or DomainConfig.load()
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
        _matches_not_executed_override(item, domain_config)
        for item in updated.get("non_executable_preferences", [])
    )
    preferences = list(updated.get("non_executable_preferences", []))
    for record in attribute_grounding.get("attributes", []):
        if record.get("status") not in {"missing_schema", "unmapped_attribute"}:
            continue
        if _matches_not_executed_override(record, domain_config) and has_cooperation_warning:
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


def _matches_not_executed_override(
    item: dict[str, Any],
    domain_config: DomainConfig,
) -> bool:
    source_text = str(item.get("source_text") or item.get("value") or "")
    return bool(_not_executed_override(item, source_text, domain_config))


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
            domain_config=DomainConfig.load(),
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
    domain_config: DomainConfig,
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
    if domain_config.is_rank_field(field):
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
    if config.domain_name != ADMISSIONS_DOMAIN.domain_id or config.domain_path:
        prompt = _clean_sentence(config.soft_preferences.get("prompt"))
        if prompt:
            return prompt
        parts = []
        for key, value in {**config.hard_filters, **config.soft_preferences}.items():
            if value in (None, "", []):
                continue
            parts.append(f"{key}={_format_value(value)}")
        return "，".join(parts) if parts else config.user_input

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
    soft_tuition_cap = _optional_int(soft.get("tuition_cap_yuan"))
    rank_window = _rank_window_selection(soft)
    if rank_window:
        boundary_parts.append(_rank_window_boundary_text(rank_window))
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


def _display_hard_filters_for_domain(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    if domain_config.domain_id == ADMISSIONS_DOMAIN.domain_id:
        return _display_hard_filters(config.hard_filters)
    return dict(config.hard_filters)


def _boundary_context(soft_preferences: dict[str, Any]) -> dict[str, Any]:
    rank_window = _rank_window_selection(soft_preferences)
    return {
        "safety_margin_percent": (
            rank_window.lower_percent
            if rank_window
            and not rank_window.upper_only
            and rank_window.lower_percent == rank_window.upper_percent
            else None
        ),
        "rank_window_label": rank_window.label if rank_window else None,
        "rank_window_lower_percent": (
            rank_window.lower_percent if rank_window else None
        ),
        "rank_window_upper_percent": (
            rank_window.upper_percent if rank_window else None
        ),
        "tuition_cap_yuan": _optional_int(soft_preferences.get("tuition_cap_yuan")),
    }


def _display_soft_preferences(soft_preferences: dict[str, Any]) -> dict[str, Any]:
    rank_window = _rank_window_selection(soft_preferences)
    return {
        "prompt": _clean_text(soft_preferences.get("prompt")),
        "safety_margin_percent": (
            rank_window.lower_percent
            if rank_window
            and not rank_window.upper_only
            and rank_window.lower_percent == rank_window.upper_percent
            else None
        ),
        "rank_window_label": rank_window.label if rank_window else None,
        "rank_window_lower_percent": (
            rank_window.lower_percent if rank_window else None
        ),
        "rank_window_upper_percent": (
            rank_window.upper_percent if rank_window else None
        ),
        "tuition_cap_yuan": _optional_int(soft_preferences.get("tuition_cap_yuan")),
    }


def _display_soft_preferences_for_domain(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    if domain_config.domain_id == ADMISSIONS_DOMAIN.domain_id:
        return _display_soft_preferences(config.soft_preferences)
    return dict(config.soft_preferences)


def _rank_window_selection(
    soft_preferences: dict[str, Any],
) -> RankWindowSelection | None:
    lower_percent = _optional_percent(
        soft_preferences.get("rank_window_lower_percent")
    )
    upper_percent = _optional_percent(
        soft_preferences.get("rank_window_upper_percent")
    )
    if lower_percent is not None or upper_percent is not None:
        lower = lower_percent if lower_percent is not None else 0
        upper = upper_percent if upper_percent is not None else 0
        return RankWindowSelection(
            label=_rank_window_label(soft_preferences, lower, upper),
            lower_percent=lower,
            upper_percent=upper,
            upper_only=True,
        )

    safety_percent = _optional_percent(soft_preferences.get("safety_margin_percent"))
    if safety_percent is None:
        return None
    return RankWindowSelection(
        label=_rank_window_label(soft_preferences, safety_percent, safety_percent),
        lower_percent=safety_percent,
        upper_percent=safety_percent,
        upper_only=False,
    )


def _rank_window_label(
    soft_preferences: dict[str, Any],
    lower_percent: int,
    upper_percent: int,
) -> str:
    explicit_label = _clean_text(
        soft_preferences.get("rank_window_label")
        or soft_preferences.get("safety_margin_label")
    )
    if explicit_label:
        return explicit_label
    if lower_percent == upper_percent:
        return f"{lower_percent}% 位次窗口"
    return f"前 {lower_percent}% / 后 {upper_percent}% 位次窗口"


def _rank_window_boundary_text(rank_window: RankWindowSelection) -> str:
    if rank_window.upper_only:
        return f"{rank_window.label}（后 {rank_window.upper_percent}% 以内）"
    return (
        f"{rank_window.label}（前 {rank_window.lower_percent}% / "
        f"后 {rank_window.upper_percent}%）"
    )


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


def _optional_percent(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 100 else None


def _extracted_preferences(
    slots: dict[str, Any],
    domain_config: DomainConfig,
) -> list[dict[str, Any]]:
    items = []
    for spec in domain_config.workbench.get("extracted_preferences") or []:
        value = None
        for path in spec.get("paths") or [spec.get("path")]:
            if not path:
                continue
            value = _value_at_path(slots, str(path))
            if value not in (None, "", []):
                break
        if value in (None, "", []):
            continue
        slot = spec.get("slot")
        items.append(
            {
                "id": spec.get("id"),
                "slot": slot,
                "value": value,
                "source_span": _source_span(str(slot), value),
                "status": spec.get("status"),
            }
        )
    return items


def _value_at_path(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for key in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _source_span(slot: str, value: Any) -> str:
    if slot == "排位":
        return f"排位{value}"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _display_attribute_grounding(
    grounding: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    return {
        "summary": grounding.get("summary", {}),
        "attributes": [
            {
                "slot_path": record.get("slot_path"),
                "slot": _slot_path_label(record.get("slot_path"), domain_config),
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
        "query_type": summary.get("query_type"),
        "sql": summary.get("sql"),
        "params": summary.get("params", []),
        "detail_sql": summary.get("detail_sql", ""),
        "detail_params": summary.get("detail_params", []),
        "input_row_count": summary.get("input_row_count"),
        "filtered_row_count": summary.get("filtered_row_count"),
        "nested_result_count": summary.get("nested_result_count", 0),
        "group_by": summary.get("group_by", []),
        "metric": summary.get("metric"),
        "sort_key": summary.get("sort_key", []),
        "sort": summary.get("sort", []),
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


def _not_executed_preferences(
    classified_rules: dict[str, Any],
    domain_config: DomainConfig,
) -> list[dict[str, Any]]:
    preferences = []
    for index, item in enumerate(
        classified_rules.get("non_executable_preferences", []),
        start=1,
    ):
        source_text = item.get("source_text", "该偏好")
        reason = _sanitize_user_text(item.get("reason") or "缺少可验证数据字段。")
        override = _not_executed_override(item, source_text, domain_config)
        preferences.append(
            {
                "id": f"not_exec_{index}",
                "preference": source_text,
                "display": (
                    override["display"]
                    if override
                    else f"{source_text}未执行：{reason}"
                ),
                "reason": override["reason"] if override else reason,
                "missing_field": (
                    override["missing_field"]
                    if override
                    else "缺少已审查数据字段"
                ),
                "source_span": source_text,
            }
        )
    return preferences


def _not_executed_override(
    item: dict[str, Any],
    source_text: Any,
    domain_config: DomainConfig,
) -> dict[str, Any] | None:
    for override in domain_config.workbench.get("not_executed_overrides") or []:
        if override.get("field_id") and item.get("field_id") == override.get("field_id"):
            return override
        contains = override.get("source_text_contains") or []
        if any(term in str(source_text) for term in contains):
            return override
    return None


def _simulated_confirmations(classified_rules: dict[str, Any]) -> dict[str, Any]:
    simulated = classified_rules.get("simulated_confirmations", {})
    safety_confirmation = simulated.get("safety_margin", {})
    safety_value = safety_confirmation.get("value")
    rank_window_bounds = _rank_window_bounds_from_confirmation(safety_confirmation)
    return {
        "recommendation_rank_floor": simulated.get(
            "recommendation_rank_floor",
            {},
        ).get("value"),
        "safety_margin_percent": _symmetric_rank_window_percent(rank_window_bounds),
        "rank_window_label": safety_confirmation.get("label"),
        "rank_window_bounds": rank_window_bounds,
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


def _top_result(
    rank: int,
    row: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    trace = [
        {
            "status": "pass" if item.get("status") == "pass" else "not_executed",
            "text": _trace_text(item),
        }
        for item in row.get("trace", [])
    ]
    result = {
        "id": f"result_{rank:03d}",
        "trace": trace,
    }
    for item in domain_config.top_result_mapping:
        key = item["key"]
        if item.get("computed") == "percent:safety_margin_pct":
            result[key] = _percent(row.get("safety_margin_pct"))
            if result[key] == "" and row.get("rank_margin") not in (None, ""):
                result[key] = row.get("rank_margin")
        elif item.get("field_id"):
            result[key] = row.get(domain_config.source_column(item["field_id"]))
        else:
            result[key] = _first_row_value(
                row,
                domain_config,
                item.get("field_ids") or [],
            )
    return result


def _item_card(
    rank: int,
    row: dict[str, Any],
    hard_rules: list[dict[str, Any]],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    top_result = _top_result(rank, row, domain_config)
    raw = {key: value for key, value in row.items() if key != "trace"}
    title = _item_title(top_result, raw, domain_config, rank)
    subtitle = _item_subtitle(top_result, raw, title)
    attributes = _item_attributes(top_result)
    return {
        "item_id": str(top_result.get("id") or f"item_{rank:03d}"),
        "title": title,
        "subtitle": subtitle,
        "primary_attributes": attributes[:4],
        "secondary_attributes": attributes[4:],
        "matched_filters": _item_matched_filters(row, hard_rules),
        "raw": raw,
    }


def _item_title(
    top_result: dict[str, Any],
    raw: dict[str, Any],
    domain_config: DomainConfig,
    rank: int,
) -> str:
    preferred_keys = [
        "university_name",
        "product_name",
        "listing_id",
        "title",
        "name",
        "major_name",
    ]
    for key in preferred_keys:
        value = top_result.get(key)
        if value not in (None, ""):
            return str(value)
    for field_id in ["university_name", "product_name", "listing_id", "major_name"]:
        source_column = domain_config.source_column_or_none(field_id)
        if source_column and raw.get(source_column) not in (None, ""):
            return str(raw[source_column])
    return f"Item {rank}"


def _item_subtitle(
    top_result: dict[str, Any],
    raw: dict[str, Any],
    title: str,
) -> str:
    preferred_keys = [
        "full_major_name",
        "major_name",
        "group_code",
        "category",
        "property_type",
        "city",
        "brand",
    ]
    for key in preferred_keys:
        value = top_result.get(key)
        if value not in (None, "") and str(value) != title:
            return str(value)
    for value in raw.values():
        if value not in (None, "") and str(value) != title:
            return str(value)
    return ""


def _item_attributes(top_result: dict[str, Any]) -> list[dict[str, Any]]:
    skipped = {"id", "trace"}
    attributes = []
    for key, value in top_result.items():
        if key in skipped or value in (None, ""):
            continue
        attributes.append(
            {
                "key": key,
                "label": key,
                "value": value,
            }
        )
    return attributes


def _item_matched_filters(
    row: dict[str, Any],
    hard_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    trace_by_rule = {
        item.get("rule_id"): item
        for item in row.get("trace", [])
        if item.get("status") == "pass"
    }
    matched = []
    for rule in hard_rules:
        rule_id = rule.get("rule_id")
        trace = trace_by_rule.get(rule_id)
        matched.append(
            {
                "id": rule_id,
                "field": rule.get("field"),
                "operator": rule.get("operator"),
                "value": rule.get("value"),
                "matched": bool(trace),
                "text": _trace_text(trace or rule),
            }
        )
    return matched


def _first_row_value(
    row: dict[str, Any],
    domain_config: DomainConfig,
    field_ids: list[str],
) -> Any:
    for field_id in field_ids:
        source_column = domain_config.source_column_or_none(field_id)
        if source_column and row.get(source_column) not in (None, ""):
            return row.get(source_column)
    return None


def _trace_text(item: dict[str, Any]) -> str:
    if item.get("rule_id") == "l_cooperation_type":
        return "中外合作：缺少合作办学类型字段，未执行"
    reason = str(item.get("reason", ""))
    return (
        reason.replace("contains", "包含")
        .replace("matches", "匹配")
        .replace("safety margin", "安全边际")
    )


def _report_from_answer(
    answer: str,
    evidence: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    safe_answer = _sanitize_user_text(answer)
    result_count = evidence["result_count"]
    warnings = _report_warnings(evidence, domain_config)
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
        "top_results": [
            _result_text(row, domain_config)
            for row in evidence["top_k_results"][:3]
        ],
        "warnings": warnings,
        "disclaimer": "以上内容是规则验证结果和证据汇总，不是最终志愿建议。",
    }


def _rule_label(
    rule: dict[str, Any],
    domain_config: DomainConfig | None = None,
) -> str:
    domain_config = domain_config or DomainConfig.load()
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
        if domain_config.is_rank_field(field):
            return f"{field} 在 {value} 名以内（数值 <= {value}）"
        return f"{field} 不高于 {value}"
    if operator == ">=":
        if domain_config.is_rank_field(field):
            return f"{field} 在 {value} 名及以后（数值 >= {value}）"
        return f"{field} 不低于 {value}"
    if operator == "between":
        if domain_config.is_rank_field(field):
            return f"{field} 位于 {_format_rank_window(rule.get('value'))}的窗口内"
        return f"{field} 位于 {value} 之间"
    if operator == "sort":
        return f"{field} 排序：{value}"
    return f"{field} {operator} {value}"


def _slot_path_label(slot_path: Any, domain_config: DomainConfig) -> str:
    labels = domain_config.workbench.get("slot_labels") or {}
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


def _result_text(row: dict[str, Any], domain_config: DomainConfig) -> str:
    parts = []
    for spec in domain_config.answer_templates.get("result_text_fields") or []:
        value = _answer_row_value(row, spec, domain_config)
        if spec.get("optional") and value in (None, ""):
            continue
        if spec.get("format") == "heading_with_group_code":
            group_code = row.get(domain_config.source_column("group_code"))
            parts.append(f"{value}（专业组 {group_code}）")
            continue
        label = spec.get("label")
        if label:
            parts.append(f"{label} {value}")
    return "；".join(parts)


def _answer_row_value(
    row: dict[str, Any],
    spec: dict[str, Any],
    domain_config: DomainConfig,
) -> Any:
    if spec.get("key"):
        return row.get(spec["key"])
    field_id = spec.get("field_id")
    if not field_id:
        return None
    return row.get(domain_config.source_column(field_id))


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


def _symmetric_rank_window_percent(
    bounds: dict[str, int] | None,
) -> int | None:
    if not bounds:
        return None
    lower = bounds.get("lower_percent")
    upper = bounds.get("upper_percent")
    return lower if lower == upper else None


def _rank_window_bounds_from_confirmation(
    confirmation: dict[str, Any],
) -> dict[str, int] | None:
    option = str(confirmation.get("selected_option") or "")
    match = re.fullmatch(r"-(\d{1,3})%/\+(\d{1,3})%", option)
    if not match:
        return None
    lower = int(match.group(1))
    upper = int(match.group(2))
    if not (0 <= lower <= 100 and 0 <= upper <= 100):
        return None
    return {"lower_percent": lower, "upper_percent": upper}


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


def _report_warnings(
    evidence: dict[str, Any],
    domain_config: DomainConfig,
) -> list[str]:
    warnings = [
        preference.get("safety_warning") or "存在未执行偏好。"
        for preference in evidence.get("not_executed_preferences", [])
    ]
    rank_field = domain_config.source_column_or_none(
        str(domain_config.execution.get("rank_field_id") or "")
    )
    has_safety_rule = any(
        rule.get("rule_id") == "e_safety_margin"
        or (
            rank_field
            and rule.get("field") == rank_field
            and rule.get("operator") in {"<=", ">=", "between"}
        )
        for rule in evidence.get("executed_rules", [])
    )
    if rank_field and not has_safety_rule:
        warnings.append(
            "本次没有确认位次窗口规则，结果只表示字段筛选通过，不代表风险已判断。"
        )
    return [_sanitize_user_text(warning) for warning in warnings]


def _with_context_warnings(
    report: dict[str, Any],
    slots: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    warnings = list(report.get("warnings", []))
    for item in domain_config.workbench.get("context_warnings") or []:
        if not _present(_value_at_path(slots, item.get("path") or "")):
            warnings.append(item.get("message"))
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
