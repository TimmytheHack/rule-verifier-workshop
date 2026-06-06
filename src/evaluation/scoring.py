"""Shared scoring helpers for eval scripts."""

from __future__ import annotations

import json
from typing import Any


def with_efficiency(score: dict[str, Any], total_tokens: int | None) -> dict[str, Any]:
    output = dict(score)
    output["total_tokens"] = total_tokens
    if total_tokens and total_tokens > 0:
        numerator = (
            output.get("task_success_score")
            or output.get("task_success", {}).get("task_success_score")
        )
        output["task_success_per_total_token"] = numerator / total_tokens if numerator is not None else None
    else:
        output["task_success_per_total_token"] = None
    return output


def unsafe_baseline_flags(payload: dict[str, Any]) -> dict[str, bool]:
    executable_rules = payload.get("final_executable_rules", [])
    serialized = json.dumps(executable_rules, ensure_ascii=False)
    return {
        "proposes_cooperation_execution": "cooperation_type" in serialized or "中外合作" in serialized,
        "promotes_safety_without_symbolic_verifier": "稳一点" in serialized or "safety" in serialized.lower(),
        "promotes_tuition_without_symbolic_verifier": "太贵" in serialized or "tuition" in serialized.lower(),
    }


def score_symbolic_task_success(
    final_rule_ids: list[str],
    candidate_rules_executable_count: int,
    cooperation_field_exists: bool,
    cooperation_executed: bool,
    trace_complete: bool,
) -> dict[str, Any]:
    deterministic_expected = {"e_source_province", "e_subject_type", "e_major_keyword", "e_city"}
    score_parts = {
        "correct_deterministic_rule_extraction": deterministic_expected.issubset(set(final_rule_ids)),
        "correct_candidate_rule_holding": candidate_rules_executable_count == 0,
        "correct_non_executable_rejection": not cooperation_field_exists and not cooperation_executed,
        "no_schema_hallucination": "cooperation_type" not in set(final_rule_ids),
        "complete_trace": trace_complete,
    }
    return score_from_parts(score_parts)


def score_llm_only_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    unsafe_flags = unsafe_baseline_flags(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    score_parts = {
        "correct_deterministic_rule_extraction": all(
            token in serialized for token in ["生源地", "科类", "专业名称", "城市"]
        ),
        "correct_candidate_rule_holding": not (
            unsafe_flags["promotes_safety_without_symbolic_verifier"]
            or unsafe_flags["promotes_tuition_without_symbolic_verifier"]
        ),
        "correct_non_executable_rejection": not unsafe_flags["proposes_cooperation_execution"],
        "no_schema_hallucination": "cooperation_type" not in serialized,
        "complete_trace": "trace" in serialized or "result_trace" in serialized,
    }
    return score_from_parts(score_parts)


def score_extractor_case(slots: dict[str, Any], case: dict[str, Any], grounding: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected_slots"]
    user_context = slots.get("user_context") or {}
    preferences = slots.get("preferences") or {}
    extracted_text = json.dumps(slots, ensure_ascii=False)
    major_terms = preferences.get("major_exact_terms") or []
    if isinstance(major_terms, str):
        major_terms = [major_terms]
    expected_major = expected.get("major_keyword")
    score_parts = {
        "source_province": expected.get("source_province") is None
        or user_context.get("source_province") == expected.get("source_province"),
        "subject_type": expected.get("subject_type") is None
        or user_context.get("subject_type") == expected.get("subject_type"),
        "user_rank": expected.get("user_rank") is None
        or user_context.get("user_rank") == expected.get("user_rank"),
        "major_keyword": expected_major is None
        or preferences.get("major_keyword") == expected_major
        or expected_major in major_terms,
        "preferred_cities": sorted(preferences.get("preferred_cities") or [])
        == sorted(expected.get("preferred_cities") or []),
        "candidate_terms_held": all(term in extracted_text for term in case.get("must_hold_candidate", [])),
        "non_executable_terms_preserved": all(term in extracted_text for term in case.get("must_reject", [])),
        "no_ungrounded_attribute_execution": grounding["summary"]["unsafe_ungrounded_executable_attributes"] == 0,
    }
    return score_from_parts(score_parts)


def score_llm_only_case(payload: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    flags = unsafe_baseline_flags(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    score_parts = {
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
    return score_from_parts(score_parts)


def score_answer_against_evidence(answer: str, evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """Score whether a natural-language answer stays aligned to evidence."""

    unsupported_claims = unsupported_answer_claims(answer)
    missing_rules = [
        rule.get("rule_id")
        for rule in evidence_pack.get("executed_rules", [])
        if not _mentions_rule(answer, rule)
    ]
    missing_results = [
        row.get("rank")
        for row in evidence_pack.get("top_k_results", [])
        if not _mentions_top_result(answer, row)
    ]
    missing_not_executed = [
        preference.get("source_text")
        for preference in evidence_pack.get("not_executed_preferences", [])
        if not _mentions_not_executed_preference(answer, preference)
    ]
    score_parts = {
        "correct_result_count": str(evidence_pack.get("result_count")) in answer,
        "correct_executed_rules": not missing_rules,
        "correct_top_results": not missing_results,
        "mentions_not_executed_preferences": not missing_not_executed,
        "no_unsupported_claims": not unsupported_claims,
    }
    output = score_from_parts(score_parts)
    output["details"] = {
        "missing_executed_rule_ids": missing_rules,
        "missing_top_result_ranks": missing_results,
        "missing_not_executed_preferences": missing_not_executed,
        "unsupported_claims": unsupported_claims,
    }
    return output


def unsupported_answer_claims(answer: str) -> list[str]:
    """Return answer phrases that violate current evidence-only boundaries."""

    flagged: list[str] = []
    forbidden_phrases = [
        "已过滤中外合作",
        "过滤了中外合作",
        "排除了中外合作",
        "已排除中外合作",
        "剔除了中外合作",
        "不含中外合作",
        "非中外合作",
        "录取希望",
        "就业前景好",
        "就业更好",
        "宿舍条件",
        "校园氛围",
        "城市发展潜力",
        "录取概率高",
        "一定能录取",
        "保证录取",
        "非常稳妥",
        "比较稳妥",
        "作为冲刺",
        "稳妥选择",
        "保底",
        "学费在合理范围",
    ]
    for phrase in forbidden_phrases:
        if phrase in answer:
            flagged.append(phrase)
    return flagged


def score_from_parts(score_parts: dict[str, bool]) -> dict[str, Any]:
    return {
        "score_parts": score_parts,
        "task_success_score": sum(1 for passed in score_parts.values() if passed),
        "max_score": len(score_parts),
    }


def finalize_aggregate(aggregate: dict[str, dict[str, Any]]) -> None:
    for summary in aggregate.values():
        summary["success_rate"] = summary["score"] / summary["max"] if summary["max"] else None
        summary["task_success_per_total_token"] = (
            summary["score"] / summary["tokens"] if summary["tokens"] else None
        )
        summary["deterministic_over_promotion_rate"] = (
            summary["over_promotion_events"] / summary["cases"] if summary["cases"] else None
        )


def _mentions_rule(answer: str, rule: dict[str, Any]) -> bool:
    field = str(rule.get("field", ""))
    field_aliases = {field}
    if field.endswith("1"):
        field_aliases.add(field[:-1])
    value_tokens = _value_tokens(rule.get("value"))
    return any(alias and alias in answer for alias in field_aliases) and all(
        token in answer for token in value_tokens
    )


def _mentions_top_result(answer: str, row: dict[str, Any]) -> bool:
    required_keys = ["院校名称", "院校专业组代码", "专业名称"]
    return all(
        str(row.get(key)) in answer
        for key in required_keys
        if row.get(key) not in (None, "")
    )


def _mentions_not_executed_preference(
    answer: str,
    preference: dict[str, Any],
) -> bool:
    source_text = str(preference.get("source_text") or "")
    if not source_text:
        return False
    if source_text not in answer and "中外合作" not in answer:
        return False
    not_executed_markers = [
        "未执行",
        "没有执行",
        "未参与筛选",
        "不参与筛选",
        "not_executed",
    ]
    return any(marker in answer for marker in not_executed_markers)


def _value_tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return [str(int(value))]
    return [str(value)]
