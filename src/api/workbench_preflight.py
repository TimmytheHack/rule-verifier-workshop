"""uploaded admissions 查询前检查 contract。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.api import workbench as workbench_module
from src.api.workbench import WorkbenchConfig
from src.domains import DomainConfig


PREFLIGHT_SCHEMA_VERSION = "workbench_preflight.v1"


@dataclass(frozen=True)
class WorkbenchPreflightConfig:
    """查询前检查输入；只描述用户请求，不携带可执行结果。"""

    user_input: str
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    model: str = "deepseek-v4-flash"
    planner_mode: str = "llm_semantic"
    domain_name: str = "admissions"
    domain_path: str | None = None
    dataset_id: str | None = None


def run_workbench_preflight(
    config: WorkbenchPreflightConfig,
    *,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    """返回查询前检查，不执行 SQL、不返回候选行。"""

    if not config.dataset_id:
        return _blocked_response(config, reason="查询前检查只支持上传表格数据源。")
    if config.domain_name != "admissions" or domain_config.domain_id != "admissions":
        return _blocked_response(
            config,
            reason="查询前检查第一版只支持 uploaded admissions。",
        )
    if domain_config.pack_status != "approved":
        return _blocked_response(
            config,
            reason="上传表格尚未完成字段审查和批准。",
        )

    response = _base_response(config)
    response["recognized_facts"] = _recognized_facts_from_inputs(config)
    workbench_config = workbench_config_from_preflight(config)
    planner_attempt = workbench_module._semantic_planner_attempt(
        workbench_config,
        domain_config,
    )
    response["planner"] = {
        "status": _preflight_planner_status(planner_attempt.planner),
        **planner_attempt.planner,
        "semantic_intent": (
            planner_attempt.intent.model_dump()
            if planner_attempt.intent is not None
            else {}
        ),
        "evidence_requirements": {"status": "not_applicable"},
    }
    if planner_attempt.intent is not None:
        response["recognized_facts"].extend(
            _recognized_facts_from_intent(config, planner_attempt.intent.model_dump())
        )
        response["recognized_facts"] = _dedupe_recognized_facts(
            response["recognized_facts"]
        )
        if planner_attempt.intent.query_type == "semantic_recommendation":
            try:
                gate_attempt = (
                    workbench_module._semantic_evidence_requirement_gate_attempt(
                        workbench_config,
                        domain_config,
                        planner_attempt.intent,
                        planner_attempt.planner,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 预检失败不进入执行链路。
                response["status"] = "blocked"
                response["planner"]["evidence_requirements"] = {
                    "status": "classification_failed",
                    "provider": "deepseek",
                    "called": True,
                    "fallback_used": True,
                    "fallback_reason": "evidence_requirement_classification_failed",
                    "error_type": type(exc).__name__,
                }
                response["missing_requirements"].append(
                    {
                        "requirement_id": confirmation_id(
                            response["preflight_id"],
                            "evidence_requirement_gate",
                            "missing_requirement",
                        ),
                        "label": "证据需求分类",
                        "message": "证据需求分类失败，不能进入推荐查询。",
                        "blocking": True,
                    }
                )
                return response
            if gate_attempt.planner:
                response["planner"]["evidence_requirements"] = gate_attempt.planner
            response["not_executable_preferences"].extend(
                _not_executable_preferences(
                    config,
                    gate_attempt.not_executed_preferences,
                )
            )
            response["boundary_confirmations"].extend(
                _boundary_confirmations(
                    config,
                    gate_attempt.not_executed_preferences,
                )
            )
    response["missing_requirements"] = _missing_requirements(config)
    if response["boundary_confirmations"] or response["missing_requirements"]:
        response["status"] = "needs_confirmation"
    return response


def workbench_config_from_preflight(config: WorkbenchPreflightConfig) -> WorkbenchConfig:
    return WorkbenchConfig(
        user_input=config.user_input,
        hard_filters=dict(config.hard_filters),
        soft_preferences=dict(config.soft_preferences),
        model=config.model,
        planner_mode=config.planner_mode,
        domain_name=config.domain_name,
        domain_path=config.domain_path,
        dataset_id=config.dataset_id,
    )


def preflight_input_signature(config: WorkbenchPreflightConfig) -> str:
    payload = {
        "dataset_id": config.dataset_id,
        "domain_name": config.domain_name,
        "user_input": config.user_input,
        "hard_filters": config.hard_filters,
        "soft_preferences": config.soft_preferences,
        "planner_mode": config.planner_mode,
        "model": config.model,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def preflight_id(config: WorkbenchPreflightConfig) -> str:
    return f"pf_{preflight_input_signature(config)[:20]}"


def confirmation_id(preflight: str, source_text: str, kind: str) -> str:
    raw = f"{preflight}|{source_text}|{kind}"
    return f"pfc_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _base_response(config: WorkbenchPreflightConfig) -> dict[str, Any]:
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "status": "ready",
        "preflight_id": preflight_id(config),
        "input_signature": preflight_input_signature(config),
        "dataset_id": config.dataset_id,
        "domain_name": config.domain_name,
        "recognized_facts": [],
        "boundary_confirmations": [],
        "not_executable_preferences": [],
        "missing_requirements": [],
        "planner": {
            "status": "not_called",
            "semantic_intent": {},
            "evidence_requirements": {"status": "not_applicable"},
        },
        "warnings": [],
        "result_count": 0,
        "items": [],
        "top_results": [],
    }


def _blocked_response(config: WorkbenchPreflightConfig, *, reason: str) -> dict[str, Any]:
    response = _base_response(config)
    response["status"] = "blocked"
    response["missing_requirements"] = [
        {
            "requirement_id": confirmation_id(
                response["preflight_id"],
                reason,
                "blocked",
            ),
            "label": "数据源状态",
            "message": reason,
            "blocking": True,
        }
    ]
    return response


def _recognized_facts_from_inputs(
    config: WorkbenchPreflightConfig,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    hard_filters = workbench_module._execution_safe_structured_preferences(
        config.hard_filters or {}
    )
    for field, label in [
        ("user_rank", "全省排位"),
        ("source_province", "生源地"),
        ("subject_type", "科类"),
        ("reselected_subjects", "再选科目"),
    ]:
        value = _hard_filter_fact_value(field, hard_filters.get(field))
        if value in (None, "", []):
            continue
        facts.append(
            {
                "fact_id": confirmation_id(preflight_id(config), field, "fact"),
                "label": label,
                "value": value,
                "source": f"hard_filters.{field}",
                "executable": True,
            }
        )
    return facts


def _hard_filter_fact_value(field: str, value: Any) -> Any:
    if field == "user_rank":
        return workbench_module._optional_int(value)
    if field == "reselected_subjects":
        return workbench_module._clean_list(value)
    return workbench_module._clean_text(value)


def _recognized_facts_from_intent(
    config: WorkbenchPreflightConfig,
    intent_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    context = intent_payload.get("user_context") or {}
    facts: list[dict[str, Any]] = []
    for field, label in [
        ("user_rank", "全省排位"),
        ("source_province", "生源地"),
        ("subject_type", "科类"),
        ("reselected_subjects", "再选科目"),
    ]:
        value = context.get(field)
        if value in (None, "", []):
            continue
        facts.append(
            {
                "fact_id": confirmation_id(
                    preflight_id(config),
                    field,
                    "intent_fact",
                ),
                "label": label,
                "value": value,
                "source": "llm_semantic_intent.user_context",
                "executable": True,
                "message": "LLM 识别为用户事实，仍需后续 verifier 检查。",
            }
        )
    return facts


def _dedupe_recognized_facts(
    facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for fact in facts:
        key = str(fact.get("label") or fact.get("fact_id") or len(deduped))
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = fact
            continue
        source = str(fact.get("source") or "")
        existing_source = str(existing.get("source") or "")
        if source.startswith("hard_filters.") and not existing_source.startswith(
            "hard_filters."
        ):
            deduped[key] = fact
    return list(deduped.values())


def _not_executable_preferences(
    config: WorkbenchPreflightConfig,
    preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for item in preferences:
        requirement_type = str(item.get("requirement_type") or item.get("type") or "")
        if requirement_type == "user_boundary":
            continue
        source_text = str(item.get("source_text") or item.get("preference") or "")
        blocked.append(
            {
                "preference_id": confirmation_id(
                    preflight_id(config),
                    source_text,
                    "not_executable",
                ),
                "source_text": source_text,
                "label": source_text or "未命名偏好",
                "requirement_type": requirement_type,
                "candidate_semantic": item.get("candidate_semantic")
                or item.get("field_id"),
                "reason": _user_facing_requirement_reason(requirement_type, item),
                "treatment": "不会参与筛选、排序或最终回答结论。",
            }
        )
    return blocked


def _boundary_confirmations(
    config: WorkbenchPreflightConfig,
    preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    confirmations: list[dict[str, Any]] = []
    current_preflight_id = preflight_id(config)
    for item in preferences:
        if str(item.get("requirement_type") or item.get("type") or "") != "user_boundary":
            continue
        source_text = str(item.get("source_text") or item.get("preference") or "")
        options = _boundary_options(source_text, item)
        confirmations.append(
            {
                "confirmation_id": confirmation_id(
                    current_preflight_id,
                    source_text,
                    "boundary",
                ),
                "source_text": source_text,
                "label": source_text or "需要确认的边界",
                "reason": str(item.get("reason") or "需要用户确认边界后才能执行。"),
                "requirement_type": "user_boundary",
                "options": options,
                "default_option_id": options[0]["option_id"] if options else None,
            }
        )
    return confirmations


def _boundary_options(
    source_text: str,
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    text = source_text or str(item.get("candidate_semantic") or item.get("field_id") or "")
    if any(term in text for term in ("稳", "保底", "冲")):
        return [
            {
                "option_id": "rank_window_reach",
                "label": "冲一冲",
                "value": "reach",
                "query_patch": {
                    "soft_preferences": {
                        "rank_window_label": "冲一冲",
                        "rank_window_lower_percent": 0,
                        "rank_window_upper_percent": 0,
                    }
                },
            },
            {
                "option_id": "rank_window_steady",
                "label": "稳一点",
                "value": "steady",
                "query_patch": {
                    "soft_preferences": {
                        "rank_window_label": "稳一点",
                        "rank_window_lower_percent": 0,
                        "rank_window_upper_percent": 15,
                    }
                },
            },
            {
                "option_id": "rank_window_safe",
                "label": "保底",
                "value": "safe",
                "query_patch": {
                    "soft_preferences": {
                        "rank_window_label": "保底",
                        "rank_window_lower_percent": 0,
                        "rank_window_upper_percent": 50,
                    }
                },
            },
            _disabled_boundary_option(),
        ]
    return [_disabled_boundary_option()]


def _disabled_boundary_option() -> dict[str, Any]:
    return {
        "option_id": "do_not_use",
        "label": "暂不使用",
        "value": None,
        "query_patch": {},
        "disabled_boundary": True,
    }


def _user_facing_requirement_reason(
    requirement_type: str,
    item: dict[str, Any],
) -> str:
    if requirement_type == "knowledge_base_or_reviewed_field":
        return "需要已审核知识库或已审核字段。"
    if requirement_type == "reviewed_ranking_policy":
        return "需要已审核排序策略。"
    if requirement_type == "unsupported":
        return "当前系统不支持执行该偏好。"
    return str(item.get("reason") or "当前没有可审核证据支持。")


def _missing_requirements(config: WorkbenchPreflightConfig) -> list[dict[str, Any]]:
    if (config.hard_filters or {}).get("user_rank"):
        return []
    return [
        {
            "requirement_id": confirmation_id(
                preflight_id(config),
                "user_rank",
                "missing_requirement",
            ),
            "label": "全省排位",
            "message": "广东志愿填报推荐需要先提供全省排位，不能只凭分数估算风险。",
            "blocking": True,
        }
    ]


def _preflight_planner_status(planner: dict[str, Any]) -> str:
    if planner.get("called") and not planner.get("fallback_used"):
        return "planned"
    if planner.get("fallback_used"):
        return "fallback"
    return "not_called"


__all__ = [
    "PREFLIGHT_SCHEMA_VERSION",
    "WorkbenchPreflightConfig",
    "confirmation_id",
    "preflight_id",
    "preflight_input_signature",
    "run_workbench_preflight",
    "workbench_config_from_preflight",
]
