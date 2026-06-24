"""admissions 语义推荐 orchestration。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from src.adapters.data_warehouse import load_structured_dataset
from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.generic_ranking import GenericRankingEngine
from src.semantic.intent_models import SemanticIntent
from src.semantic.preference_grounder import PreferenceGrounder
from src.semantic.query_ast import QueryAST
from src.semantic.query_verifier import SemanticQueryVerifier
from src.semantic.ranking_verifier import RankingVerifier
from src.semantic.rerank_validator import RerankValidationResult, RerankValidator
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.sql_builder import SemanticSQLBuilder


SEMANTIC_QUERY_TYPE = "semantic_recommendation"
PUBLIC_QUERY_TYPE = "recommendation"
DISPLAY_FIELDS = [
    "year",
    "university_name",
    "group_code",
    "major_name",
    "major_code",
    "major_notes",
    "subject_type",
    "subject_requirement",
    "major_min_score",
    "major_min_rank",
    "school_province",
    "school_is_985",
    "school_is_211",
    "plan_count",
]
OPTIONAL_CONTEXT_FIELDS = [
    "city",
    "tuition_yuan_per_year",
    "group_min_rank",
    "school_ownership",
]
RESELECTED_SUBJECTS = ["化学", "生物", "政治", "地理"]
BUCKET_ORDER = ["reach", "match", "safety"]
BUCKET_LABELS = {"reach": "冲", "match": "稳", "safety": "保"}
DEFAULT_BUCKET_QUOTAS = {"reach": 10, "match": 13, "safety": 10}
RANKING_FIELD_ALIASES = {
    "year": "年份",
    "university_name": "院校名称",
    "group_code": "专业组",
    "major_name": "专业",
    "major_code": "专业代码",
    "major_min_score": "最低分",
    "major_min_rank": "最低录取排名",
    "school_province": "学校所在",
    "city": "城市",
    "tuition_yuan_per_year": "学费",
    "group_min_rank": "专业组最低位次",
    "school_is_985": "是否985",
    "school_is_211": "是否211",
    "plan_count": "录取人数",
}


@dataclass(frozen=True)
class SemanticAdmissionsRecommendationResult:
    """uploaded admissions 语义推荐结果。"""

    query_type: str
    status: str
    rows: list[dict[str, Any]]
    result_sections: dict[str, list[dict[str, Any]]]
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]
    execution_summary: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    not_executed_preferences: list[dict[str, Any]] = field(default_factory=list)
    selection_evidence: list[dict[str, Any]] = field(default_factory=list)


class SemanticAdmissionsRecommendationPlanner:
    """把 LLM 候选意图约束成 verified SQL 和证据化推荐候选。"""

    def __init__(
        self,
        *,
        domain_config: DomainConfig,
        database_path: str | Path,
        table_name: str,
        reranker: Any | None = None,
        rerank_validator: RerankValidator | None = None,
        ranking_plan: Any | None = None,
        ranking_verifier: Any | None = None,
        ranking_engine: Any | None = None,
        pre_not_executed_preferences: list[dict[str, Any]] | None = None,
        pre_unanswerable_intents: list[dict[str, Any]] | None = None,
    ) -> None:
        self.domain_config = domain_config
        self.database_path = Path(database_path)
        self.table_name = table_name
        self.reranker = reranker
        self.rerank_validator = rerank_validator or RerankValidator()
        self.ranking_plan = ranking_plan
        self.ranking_verifier = ranking_verifier
        self.ranking_engine = ranking_engine
        self.pre_not_executed_preferences = list(
            pre_not_executed_preferences or []
        )
        self.pre_unanswerable_intents = list(pre_unanswerable_intents or [])

    def run(
        self,
        intent: SemanticIntent,
    ) -> SemanticAdmissionsRecommendationResult | None:
        if intent.query_type != SEMANTIC_QUERY_TYPE:
            return None

        pre_not_executed = list(self.pre_not_executed_preferences)
        pre_unanswerable = list(self.pre_unanswerable_intents)
        rank = intent.user_context.user_rank
        if rank is None:
            return _rank_confirmation_result(
                intent,
                pre_not_executed_preferences=pre_not_executed,
                pre_unanswerable_intents=pre_unanswerable,
            )

        dataset = load_structured_dataset(
            self.database_path,
            required_columns=[],
            table_name=self.table_name,
        )
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(self.domain_config, graph)
        missing_fields = _missing_recipe_fields(self.domain_config, registry)
        if missing_fields:
            return _blocked_missing_fields(
                missing_fields,
                registry,
                intent=intent,
                pre_not_executed_preferences=pre_not_executed,
                pre_unanswerable_intents=pre_unanswerable,
            )

        rank_basis = _rank_basis(self.domain_config, registry)
        year_value = _latest_year(graph, registry)
        grounded = PreferenceGrounder(registry).ground(intent.preferences)
        combined_not_executed = [
            *pre_not_executed,
            *grounded.not_executed_preferences,
        ]
        combined_unanswerable = [
            *pre_unanswerable,
            *grounded.unanswerable_intents,
        ]
        ast = _query_ast(
            intent=intent,
            rank=rank,
            year_value=year_value,
            rank_basis=rank_basis,
            registry=registry,
            grounded_filters=grounded.filters,
        )
        verification = SemanticQueryVerifier(
            registry,
            table_name=self.table_name,
        ).verify(ast)
        if not verification.ok:
            return SemanticAdmissionsRecommendationResult(
                query_type=PUBLIC_QUERY_TYPE,
                status="blocked",
                rows=[],
                result_sections=_empty_sections(),
                answerable_intents=[
                    *grounded.answerable_intents,
                    *verification.answerable_intents,
                ],
                unanswerable_intents=[
                    *combined_unanswerable,
                    *verification.unanswerable_intents,
                ],
                not_executed_preferences=combined_not_executed,
                execution_summary={
                    **_empty_execution_summary(rank=rank, rank_basis=rank_basis),
                    "verification_issues": [
                        issue.to_dict() for issue in verification.issues
                    ],
                    "not_executed_preferences": combined_not_executed,
                    "verified_query_plan": verification.plan.model_dump(),
                },
                warnings=[
                    {
                        "code": "query_plan_not_verified",
                        "severity": "error",
                        "message": "候选 QueryAST 未通过字段或操作校验。",
                    },
                    *_context_warnings(intent, combined_not_executed),
                ],
            )

        built = SemanticSQLBuilder().build(verification.plan)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            sql_rows = connection.execute(built.sql, built.params).fetchdf().to_dict(
                "records"
            )

        subject_rows = _filter_subject_rows(
            rows=sql_rows,
            selected_subjects=intent.user_context.reselected_subjects,
        )
        normal_rows, excluded_rows = _split_special_limit_rows(
            subject_rows,
            self.domain_config.semantic_capabilities,
        )
        quotas = _bucket_quotas(self.domain_config)
        candidate_sections = _bucket_candidates(
            normal_rows,
            rank=rank,
            rank_basis=rank_basis,
        )
        candidate_rows = _ordered_rows(candidate_sections)
        rerank_validation = _rerank_or_fallback(
            reranker=self.reranker,
            validator=self.rerank_validator,
            intent=intent,
            candidates=candidate_rows,
            quotas=quotas,
        )
        result_sections = rerank_validation.result_sections
        rows = _ordered_rows(result_sections)
        rows, ranking_summary = _apply_ranking_plan(
            ranking_plan=self.ranking_plan,
            ranking_verifier=self.ranking_verifier,
            ranking_engine=self.ranking_engine,
            registry=registry,
            rows=rows,
            value_evidence=_ranking_value_evidence(
                intent=intent,
                ranking_plan=self.ranking_plan,
                rank_basis=rank_basis,
            ),
        )
        result_sections = _sections_from_ordered_rows(rows)
        for index, row in enumerate(rows, start=1):
            row["次序"] = index

        selection_evidence = _selection_evidence(rows, rank_basis)
        return SemanticAdmissionsRecommendationResult(
            query_type=PUBLIC_QUERY_TYPE,
            status="ok" if rows else "no_results",
            rows=rows,
            result_sections=result_sections,
            answerable_intents=[
                {
                    "field_id": "user_rank",
                    "answerable": True,
                    "capability": "recommendation_context",
                    "value": rank,
                },
                *grounded.answerable_intents,
                *verification.answerable_intents,
                {
                    "intent": "risk_buckets",
                    "answerable": True,
                    "basis": rank_basis,
                    "bucket_rules": {
                        "冲": "最低位次 < 用户位次",
                        "稳": "0 <= 最低位次 - 用户位次 <= 8000",
                        "保": "最低位次 - 用户位次 > 8000",
                    },
                },
            ],
            unanswerable_intents=[
                *combined_unanswerable,
                *_missing_context_intents(registry),
            ],
            not_executed_preferences=combined_not_executed,
            selection_evidence=selection_evidence,
            execution_summary={
                "executor": "duckdb",
                "query_type": SEMANTIC_QUERY_TYPE,
                "public_query_type": PUBLIC_QUERY_TYPE,
                "sql": built.sql,
                "params": built.params,
                "input_row_count": graph.row_count,
                "sql_row_count": len(sql_rows),
                "subject_compatible_row_count": len(subject_rows),
                "special_limit_excluded_count": len(excluded_rows),
                "filtered_row_count": len(rows),
                "rank": rank,
                "year": year_value,
                "basis": rank_basis,
                "bucket_candidate_counts": {
                    bucket: len(items) for bucket, items in candidate_sections.items()
                },
                "selected_counts": {
                    bucket: len(result_sections[bucket]) for bucket in BUCKET_ORDER
                },
                "rerank_validation": rerank_validation.to_dict(),
                "ranking": ranking_summary,
                "selection_evidence": selection_evidence,
                "excluded_rows": excluded_rows,
                "not_executed_preferences": combined_not_executed,
                "verified_query_plan": verification.plan.model_dump(),
            },
            warnings=_context_warnings(intent, combined_not_executed),
        )


def _rank_confirmation_result(
    intent: SemanticIntent,
    *,
    pre_not_executed_preferences: list[dict[str, Any]] | None = None,
    pre_unanswerable_intents: list[dict[str, Any]] | None = None,
) -> SemanticAdmissionsRecommendationResult:
    pre_not_executed = list(pre_not_executed_preferences or [])
    pre_unanswerable = list(pre_unanswerable_intents or [])
    warnings = [
        {
            "code": "score_without_rank",
            "severity": "error",
            "message": "只给高考分数时不执行推荐 SQL；请补充广东省排位/位次。",
        }
    ] if intent.user_context.user_score is not None else [
        {
            "code": "missing_rank",
            "severity": "error",
            "message": "缺少广东省排位，不能执行推荐 SQL。",
        }
    ]
    if pre_not_executed:
        warnings = [
            *warnings,
            *_preference_not_executed_warnings(pre_not_executed),
        ]
    return SemanticAdmissionsRecommendationResult(
        query_type=PUBLIC_QUERY_TYPE,
        status="needs_confirmation",
        rows=[],
        result_sections=_empty_sections(),
        answerable_intents=[],
        unanswerable_intents=[
            {
                "field_id": "user_rank",
                "answerable": False,
                "reason": "score_without_rank"
                if intent.user_context.user_score is not None
                else "missing_rank",
                "message": warnings[0]["message"],
            },
            *pre_unanswerable,
        ],
        not_executed_preferences=pre_not_executed,
        execution_summary={
            **_empty_execution_summary(rank_basis="major_min_rank"),
            "not_executed_preferences": pre_not_executed,
        },
        warnings=warnings,
    )


def _query_ast(
    *,
    intent: SemanticIntent,
    rank: int,
    year_value: int | None,
    rank_basis: str,
    registry: ReviewedMappingRegistry,
    grounded_filters: list[dict[str, Any]],
) -> QueryAST:
    filters: list[dict[str, Any]] = []
    if year_value is not None and registry.has_field("year") and registry.has_op("year", "eq"):
        filters.append({"field_id": "year", "op": "eq", "value": year_value})
    subject_filter = _subject_type_filter(intent, registry)
    if subject_filter:
        filters.append(subject_filter)
    filters.append(
        {
            "field_id": rank_basis,
            "op": "between",
            "value": [max(1, rank - 8000), rank + 30000],
        }
    )
    filters.extend(_query_filters(grounded_filters))
    return QueryAST.from_candidate(
        {
            "intent": SEMANTIC_QUERY_TYPE,
            "select": _select_fields(registry, rank_basis),
            "filters": filters,
            "sort": [{"field_id": rank_basis, "direction": "asc"}],
            "limit": _default_limit(registry),
            "requested_output": ["recommendation_sections", "minimum_rank"],
            "source": "llm_semantic_intent_verified_recipe",
        }
    )


def _select_fields(
    registry: ReviewedMappingRegistry,
    rank_basis: str,
) -> list[str]:
    fields = [
        *DISPLAY_FIELDS,
        *OPTIONAL_CONTEXT_FIELDS,
        rank_basis,
    ]
    output: list[str] = []
    for field_id in fields:
        if field_id not in output and registry.has_field(field_id):
            output.append(field_id)
    return output


def _query_filters(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "field_id": item["field_id"],
            "op": item["op"],
            "value": item["value"],
        }
        for item in filters
    ]


def _subject_type_filter(
    intent: SemanticIntent,
    registry: ReviewedMappingRegistry,
) -> dict[str, Any] | None:
    subject_type = _normalize_subject_type(intent.user_context.subject_type)
    if not subject_type or not registry.has_field("subject_type"):
        return None
    if registry.has_op("subject_type", "in"):
        return {
            "field_id": "subject_type",
            "op": "in",
            "value": _subject_type_values(subject_type),
        }
    if registry.has_op("subject_type", "eq"):
        return {
            "field_id": "subject_type",
            "op": "eq",
            "value": subject_type,
        }
    return None


def _subject_type_values(subject_type: str) -> list[str]:
    if subject_type == "物理类":
        return ["物理类", "物理"]
    if subject_type == "历史类":
        return ["历史类", "历史"]
    return [subject_type]


def _normalize_subject_type(value: Any) -> str | None:
    text = "" if value is None else str(value)
    if "物理" in text:
        return "物理类"
    if "历史" in text:
        return "历史类"
    return None


def _filter_subject_rows(
    *,
    rows: list[dict[str, Any]],
    selected_subjects: list[str],
) -> list[dict[str, Any]]:
    if not selected_subjects:
        return list(rows)
    return [
        row
        for row in rows
        if _subject_requirement_compatible(
            row.get("subject_requirement"),
            selected_subjects,
        )
    ]


def _subject_requirement_compatible(
    requirement: Any,
    selected_subjects: list[str],
) -> bool:
    required_groups = _required_subject_groups(requirement)
    if not required_groups:
        return True
    selected = set(_unique_subjects(selected_subjects))
    return any(group.issubset(selected) for group in required_groups)


def _required_subject_groups(requirement: Any) -> list[set[str]]:
    text = _normalize_subject_text(requirement)
    if not text or text in {"不限", "无", "nan"} or "不限" in text:
        return []
    if "或" in text or "/" in text:
        return [
            subjects
            for subjects in (
                _subjects_in_text(part) for part in re.split(r"或|/", text)
            )
            if subjects
        ]
    subjects = _subjects_in_text(text)
    return [subjects] if subjects else []


def _subjects_in_text(text: str) -> set[str]:
    return {subject for subject in RESELECTED_SUBJECTS if subject in text}


def _normalize_subject_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text.replace("思想政治", "政治").replace("生物学", "生物")


def _unique_subjects(values: Any) -> list[str]:
    output = []
    for value in values:
        text = _normalize_subject_text(value)
        if text in RESELECTED_SUBJECTS and text not in output:
            output.append(text)
    return output[:2]


def _split_special_limit_rows(
    rows: list[dict[str, Any]],
    capabilities: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    special_terms = [str(term) for term in capabilities.get("special_limit_terms") or []]
    normal_rows = []
    excluded_rows = []
    for index, row in enumerate(rows, start=1):
        matched_terms = _matched_special_terms(row, special_terms)
        if matched_terms:
            excluded_rows.append(
                {
                    "row_id": f"candidate_{index:03d}",
                    "reason": "special_limit",
                    "matched_terms": matched_terms,
                    "university_name": row.get("university_name"),
                    "major_name": row.get("major_name"),
                    "major_notes": row.get("major_notes"),
                }
            )
            continue
        normal_rows.append(row)
    return normal_rows, excluded_rows


def _matched_special_terms(row: dict[str, Any], terms: list[str]) -> list[str]:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ["major_notes", "university_name", "major_name"]
    )
    return [term for term in terms if term and term in haystack]


def _rerank_or_fallback(
    *,
    reranker: Any | None,
    validator: RerankValidator,
    intent: SemanticIntent,
    candidates: list[dict[str, Any]],
    quotas: dict[str, int],
) -> RerankValidationResult:
    if reranker is None:
        return RerankValidationResult(
            ok=True,
            result_sections=_fallback_sections(candidates, quotas),
            raw_payload={"used": False},
        )
    try:
        payload = reranker.rerank(
            intent=intent,
            candidates=candidates,
            quotas=quotas,
        )
    except Exception as exc:  # noqa: BLE001 - rerank 失败不能影响 verified SQL 结果。
        return RerankValidationResult(
            ok=False,
            result_sections=_fallback_sections(candidates, quotas),
            issues=[
                {
                    "code": "reranker_error",
                    "message": str(exc),
                }
            ],
            fallback_used=True,
            raw_payload={"used": True},
        )
    return validator.validate(payload, candidates=candidates, quotas=quotas)


def _apply_ranking_plan(
    *,
    ranking_plan: Any | None,
    ranking_verifier: Any | None,
    ranking_engine: Any | None,
    registry: ReviewedMappingRegistry,
    rows: list[dict[str, Any]],
    value_evidence: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = {
        "status": "candidate_list_only",
        "verified_ranking_plan": None,
        "excluded_criteria": [],
        "criterion_evidence": [],
    }
    if ranking_plan is None:
        return rows, summary

    verifier = ranking_verifier or RankingVerifier(
        registry,
        value_evidence=value_evidence,
    )
    ranking_result = verifier.verify(ranking_plan)
    summary["verified_ranking_plan"] = ranking_result.verified_plan.model_dump()
    summary["excluded_criteria"] = ranking_result.excluded_criteria
    if not ranking_result.ok:
        summary["status"] = "not_ranked_unverified_plan"
        return rows, summary
    if ranking_result.verified_plan.criteria:
        ranked = (ranking_engine or GenericRankingEngine()).rank(
            rows=_ranking_rows(rows),
            plan=ranking_result.verified_plan,
        )
        summary["status"] = "ranked"
        summary["criterion_evidence"] = ranked.criterion_evidence
        return _restore_ranked_rows(rows, ranked.rows), summary
    return rows, summary


def _ranking_value_evidence(
    *,
    intent: SemanticIntent,
    ranking_plan: Any | None,
    rank_basis: str,
) -> list[dict[str, Any]]:
    if ranking_plan is None:
        return []
    evidence: list[dict[str, Any]] = []
    for criterion in getattr(ranking_plan, "criteria", []) or []:
        if (
            criterion.required_field == rank_basis
            and criterion.operation == "numeric_distance_to_user_value"
            and intent.user_context.user_rank is not None
            and _int_or_none(criterion.value) == intent.user_context.user_rank
        ):
            evidence.append(
                {
                    "criterion_id": criterion.criterion_id,
                    "source": "user_input",
                    "field_id": criterion.required_field,
                    "operation": criterion.operation,
                    "value": intent.user_context.user_rank,
                }
            )
    return evidence


def _ranking_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_ranking_row(row) for row in rows]


def _ranking_row(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    for field_id, display_key in RANKING_FIELD_ALIASES.items():
        if field_id not in output and display_key in row:
            output[field_id] = row.get(display_key)
    return output


def _restore_ranked_rows(
    original_rows: list[dict[str, Any]],
    ranked_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_id = {row.get("row_id"): row for row in original_rows}
    return [
        rows_by_id.get(row.get("row_id"), row)
        for row in ranked_rows
    ]


def _fallback_sections(
    candidates: list[dict[str, Any]],
    quotas: dict[str, int],
) -> dict[str, list[dict[str, Any]]]:
    sections = {bucket: [] for bucket in BUCKET_ORDER}
    for candidate in candidates:
        bucket = candidate.get("bucket")
        if bucket not in sections:
            continue
        if len(sections[bucket]) >= quotas[bucket]:
            continue
        sections[bucket].append(dict(candidate))
    return sections


def _bucket_candidates(
    rows: list[dict[str, Any]],
    *,
    rank: int,
    rank_basis: str,
) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKET_ORDER}
    for index, row in enumerate(rows, start=1):
        rank_value = _int_or_none(row.get(rank_basis))
        if rank_value is None:
            continue
        bucket = _bucket_key(rank_value - rank)
        candidates[bucket].append(
            _project_row(
                bucket=bucket,
                row_id=f"candidate_{index:03d}",
                row=row,
                rank=rank,
                rank_basis=rank_basis,
                rank_value=rank_value,
            )
        )
    return {
        bucket: sorted(candidates[bucket], key=_deterministic_selection_key)
        for bucket in BUCKET_ORDER
    }


def _bucket_key(margin: int) -> str:
    if margin < 0:
        return "reach"
    if margin <= 8000:
        return "match"
    return "safety"


def _project_row(
    *,
    bucket: str,
    row_id: str,
    row: dict[str, Any],
    rank: int,
    rank_basis: str,
    rank_value: int,
) -> dict[str, Any]:
    margin = rank_value - rank
    return {
        "row_id": row_id,
        "档位": BUCKET_LABELS[bucket],
        "bucket": bucket,
        "院校名称": row.get("university_name"),
        "专业组": row.get("group_code"),
        "专业": row.get("major_name"),
        "专业代码": row.get("major_code"),
        "最低分": _int_or_none(row.get("major_min_score")),
        "最低录取排名": _int_or_none(row.get("major_min_rank")),
        "排序依据最低位次": rank_value,
        "排序依据字段": rank_basis,
        "相对用户排名": margin,
        "学校所在": row.get("school_province"),
        "城市": row.get("city"),
        "学费": _int_or_none(row.get("tuition_yuan_per_year")),
        "专业组最低位次": _int_or_none(row.get("group_min_rank")),
        "是否985": row.get("school_is_985"),
        "是否211": row.get("school_is_211"),
        "录取人数": _int_or_none(row.get("plan_count")),
    }


def _deterministic_selection_key(row: dict[str, Any]) -> tuple[int, int, int, str, str]:
    school_score = 0
    if str(row.get("是否985")) == "是":
        school_score -= 2
    if str(row.get("是否211")) == "是":
        school_score -= 1
    return (
        abs(int(row.get("相对用户排名") or 0)),
        school_score,
        int(row.get("排序依据最低位次") or 0),
        str(row.get("院校名称") or ""),
        str(row.get("专业") or ""),
    )


def _ordered_rows(bucketed: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in BUCKET_ORDER:
        rows.extend(bucketed.get(bucket) or [])
    return rows


def _sections_from_ordered_rows(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKET_ORDER}
    for row in rows:
        bucket = row.get("bucket")
        if bucket in sections:
            sections[bucket].append(row)
    return sections


def _selection_evidence(
    rows: list[dict[str, Any]],
    rank_basis: str,
) -> list[dict[str, Any]]:
    return [
        {
            "row_id": row["row_id"],
            "bucket": row["bucket"],
            "bucket_label": row["档位"],
            "basis": rank_basis,
            "rank_value": row["排序依据最低位次"],
            "margin": row["相对用户排名"],
            "reason_codes": row.get("rerank_reason_codes")
            or [
                "verified_sql_filter",
                "rank_distance_bucket",
                "deterministic_rank_distance_order",
            ],
        }
        for row in rows
    ]


def _missing_recipe_fields(
    domain_config: DomainConfig,
    registry: ReviewedMappingRegistry,
) -> list[str]:
    recipe = _recipe(domain_config)
    required = recipe.get("required_field_ids") or recipe.get("required_fields") or []
    return [field_id for field_id in required if not registry.has_field(str(field_id))]


def _rank_basis(
    domain_config: DomainConfig,
    registry: ReviewedMappingRegistry,
) -> str:
    recipe = _recipe(domain_config)
    for field_id in recipe.get("rank_basis_preference") or ["major_min_rank"]:
        if registry.has_field(str(field_id)):
            return str(field_id)
    return "major_min_rank"


def _latest_year(
    graph: DatasetCapabilityGraph,
    registry: ReviewedMappingRegistry,
) -> int | None:
    source_column = registry.source_column_or_none("year")
    if not source_column:
        return None
    field = graph.fields.get(source_column)
    if field is None or field.numeric_max is None:
        return None
    return int(field.numeric_max)


def _bucket_quotas(domain_config: DomainConfig) -> dict[str, int]:
    recipe = _recipe(domain_config)
    configured = recipe.get("bucket_quotas") or {}
    return {
        bucket: int(configured.get(bucket) or DEFAULT_BUCKET_QUOTAS[bucket])
        for bucket in BUCKET_ORDER
    }


def _default_limit(registry: ReviewedMappingRegistry) -> int:
    _ = registry
    return 100


def _recipe(domain_config: DomainConfig) -> dict[str, Any]:
    return (
        domain_config.semantic_capabilities.get("query_recipes") or {}
    ).get(SEMANTIC_QUERY_TYPE) or {}


def _missing_context_intents(
    registry: ReviewedMappingRegistry,
) -> list[dict[str, Any]]:
    return [
        {
            "field_id": field_id,
            "answerable": False,
            "reason": registry.unsupported_reason(field_id)
            or "当前数据缺少该可展示字段。",
        }
        for field_id in OPTIONAL_CONTEXT_FIELDS
        if not registry.has_field(field_id)
    ]


def _context_warnings(
    intent: SemanticIntent,
    not_executed_preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings = _preference_not_executed_warnings(not_executed_preferences)
    if not intent.user_context.subject_type:
        warnings.append(
            {
                "code": "subject_type_not_provided",
                "severity": "info",
                "message": "用户未提供科类，未执行科类筛选。",
            }
        )
    if not intent.user_context.reselected_subjects:
        warnings.append(
            {
                "code": "subject_requirement_not_provided",
                "severity": "info",
                "message": "用户未提供再选科目，未执行选科要求过滤。",
            }
        )
    return warnings


def _preference_not_executed_warnings(
    not_executed_preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "code": "preference_not_executed",
            "severity": "warning",
            "field_id": item.get("field_id"),
            "message": item.get("reason") or "偏好未执行。",
            "source_text": item.get("source_text"),
        }
        for item in not_executed_preferences
    ]


def _blocked_missing_fields(
    missing_fields: list[str],
    registry: ReviewedMappingRegistry,
    *,
    intent: SemanticIntent,
    pre_not_executed_preferences: list[dict[str, Any]] | None = None,
    pre_unanswerable_intents: list[dict[str, Any]] | None = None,
) -> SemanticAdmissionsRecommendationResult:
    pre_not_executed = list(pre_not_executed_preferences or [])
    pre_unanswerable = list(pre_unanswerable_intents or [])
    warnings = [
        {
            "code": "missing_recipe_fields",
            "severity": "error",
            "message": "当前数据缺少 semantic_recommendation 必需字段。",
            "missing_fields": missing_fields,
        }
    ]
    if pre_not_executed:
        warnings = [
            *warnings,
            *_preference_not_executed_warnings(pre_not_executed),
        ]
    return SemanticAdmissionsRecommendationResult(
        query_type=PUBLIC_QUERY_TYPE,
        status="blocked",
        rows=[],
        result_sections=_empty_sections(),
        answerable_intents=[],
        unanswerable_intents=[
            *[
                {
                    "field_id": field_id,
                    "answerable": False,
                    "reason": registry.unsupported_reason(field_id)
                    or "当前数据缺少 semantic_recommendation 必需字段。",
                }
                for field_id in missing_fields
            ],
            *pre_unanswerable,
        ],
        not_executed_preferences=pre_not_executed,
        execution_summary={
            **_empty_execution_summary(),
            "not_executed_preferences": pre_not_executed,
        },
        warnings=warnings,
    )


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text or text.lower() == "nan":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    parsed = float(match.group(0))
    if not math.isfinite(parsed):
        return None
    return int(parsed)


def _empty_sections() -> dict[str, list[dict[str, Any]]]:
    return {bucket: [] for bucket in BUCKET_ORDER}


def _empty_execution_summary(
    rank: int | None = None,
    rank_basis: str | None = None,
) -> dict[str, Any]:
    return {
        "executor": None,
        "query_type": SEMANTIC_QUERY_TYPE,
        "public_query_type": PUBLIC_QUERY_TYPE,
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
        "rank": rank,
        "basis": rank_basis,
        "verified_query_plan": None,
    }


__all__ = [
    "SemanticAdmissionsRecommendationPlanner",
    "SemanticAdmissionsRecommendationResult",
]
