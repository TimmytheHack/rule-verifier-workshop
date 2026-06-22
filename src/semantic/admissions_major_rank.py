"""admissions 专业最低位次冲稳保 recipe。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from src.adapters.data_warehouse import load_structured_dataset
from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.query_ast import QueryAST
from src.semantic.query_verifier import SemanticQueryVerifier
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.sql_builder import SemanticSQLBuilder


QUERY_TYPE = "admissions_major_rank"
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
UNANSWERABLE_CONTEXT_FIELDS = [
    "city",
    "tuition_yuan_per_year",
    "group_min_rank",
]


@dataclass(frozen=True)
class AdmissionsMajorRankResult:
    """admissions major-rank planned query result."""

    query_type: str
    status: str
    rows: list[dict[str, Any]]
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]
    execution_summary: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)


class AdmissionsMajorRankPlanner:
    """按专业最低位次执行冲稳保。"""

    def __init__(
        self,
        *,
        domain_config: DomainConfig,
        database_path: str | Path,
        table_name: str,
    ) -> None:
        self.domain_config = domain_config
        self.database_path = Path(database_path)
        self.table_name = table_name

    def run(self, user_request: str) -> AdmissionsMajorRankResult | None:
        if "冲稳保" not in user_request and "最低录取排名" not in user_request:
            return None

        rank = _parse_rank(user_request)
        if rank is None:
            return AdmissionsMajorRankResult(
                query_type=QUERY_TYPE,
                status="needs_confirmation",
                rows=[],
                answerable_intents=[],
                unanswerable_intents=[
                    {
                        "field_id": "user_rank",
                        "answerable": False,
                        "reason": "缺少广东省排位，不能生成冲稳保。",
                    }
                ],
                execution_summary=_empty_execution_summary(),
                warnings=[
                    {
                        "code": "missing_rank",
                        "severity": "error",
                        "message": "缺少广东省排位。",
                    }
                ],
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
            return _blocked_missing_fields(missing_fields, registry)

        ast = _query_ast(rank, registry)
        verification = SemanticQueryVerifier(
            registry,
            table_name=self.table_name,
        ).verify(ast)
        if not verification.ok:
            return AdmissionsMajorRankResult(
                query_type=QUERY_TYPE,
                status="blocked",
                rows=[],
                answerable_intents=verification.answerable_intents,
                unanswerable_intents=verification.unanswerable_intents,
                execution_summary={
                    **_empty_execution_summary(),
                    "verification_issues": [
                        issue.to_dict() for issue in verification.issues
                    ],
                    "verified_query_plan": verification.plan.model_dump(),
                },
                warnings=[
                    {
                        "code": "query_plan_not_verified",
                        "severity": "error",
                        "message": "候选 QueryAST 未通过字段或操作校验。",
                    }
                ],
            )

        built = SemanticSQLBuilder().build(verification.plan)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            raw_rows = connection.execute(built.sql, built.params).fetchdf().to_dict(
                "records"
            )

        rows = _bucket_rows(
            raw_rows,
            rank,
            self.domain_config.semantic_capabilities,
        )
        return AdmissionsMajorRankResult(
            query_type=QUERY_TYPE,
            status="ok" if rows else "no_results",
            rows=rows,
            answerable_intents=[
                *verification.answerable_intents,
                {
                    "intent": "risk_buckets",
                    "answerable": True,
                    "basis": "major_min_rank",
                    "bucket_rules": {
                        "冲": [rank - 1500, rank - 1],
                        "稳": [rank, rank + 3000],
                        "保": [rank + 3001, rank + 9000],
                    },
                },
            ],
            unanswerable_intents=_unsupported_context_intents(registry),
            execution_summary={
                "executor": "duckdb",
                "query_type": QUERY_TYPE,
                "sql": built.sql,
                "params": built.params,
                "input_row_count": graph.row_count,
                "sql_row_count": len(raw_rows),
                "filtered_row_count": len(rows),
                "rank": rank,
                "basis": "major_min_rank",
                "verified_query_plan": verification.plan.model_dump(),
            },
        )


def _query_ast(rank: int, registry: ReviewedMappingRegistry) -> QueryAST:
    return QueryAST.from_candidate(
        {
            "intent": QUERY_TYPE,
            "select": DISPLAY_FIELDS,
            "filters": [
                {"field_id": "year", "op": "eq", "value": 2025},
                _subject_type_filter(registry),
                {
                    "field_id": "major_min_rank",
                    "op": "between",
                    "value": [rank - 1500, rank + 9000],
                },
            ],
            "sort": [{"field_id": "major_min_rank", "direction": "asc"}],
            "limit": 100,
            "requested_output": ["risk_buckets", "major_min_rank"],
            "source": "deterministic_recipe",
        }
    )


def _subject_type_filter(registry: ReviewedMappingRegistry) -> dict[str, Any]:
    if registry.has_op("subject_type", "contains"):
        return {"field_id": "subject_type", "op": "contains", "value": "物理"}
    if registry.has_op("subject_type", "in"):
        return {"field_id": "subject_type", "op": "in", "value": ["物理类"]}
    return {"field_id": "subject_type", "op": "eq", "value": "物理类"}


def _bucket_rows(
    raw_rows: list[dict[str, Any]],
    rank: int,
    capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    special_terms = [str(term) for term in capabilities.get("special_limit_terms") or []]
    normal_rows = [
        row for row in raw_rows if not _has_special_limit(row, special_terms)
    ]
    buckets = [
        ("冲", rank - 1500, rank - 1),
        ("稳", rank, rank + 3000),
        ("保", rank + 3001, rank + 9000),
    ]
    output = []
    for label, lower, upper in buckets:
        candidates = [
            row
            for row in normal_rows
            if _rank_in_bucket(row.get("major_min_rank"), lower, upper)
        ]
        if not candidates:
            continue
        selected = min(
            candidates,
            key=lambda row: abs(int(row["major_min_rank"]) - rank),
        )
        output.append(_project_row(label, selected, rank))
    return output


def _project_row(label: str, row: dict[str, Any], rank: int) -> dict[str, Any]:
    min_rank = int(row["major_min_rank"])
    return {
        "档位": label,
        "院校名称": row.get("university_name"),
        "专业组": row.get("group_code"),
        "专业": row.get("major_name"),
        "专业代码": row.get("major_code"),
        "最低分": _int_or_none(row.get("major_min_score")),
        "最低录取排名": min_rank,
        "相对用户排名": min_rank - rank,
        "学校所在": row.get("school_province"),
        "是否985": row.get("school_is_985"),
        "是否211": row.get("school_is_211"),
        "录取人数": _int_or_none(row.get("plan_count")),
    }


def _rank_in_bucket(value: Any, lower: int, upper: int) -> bool:
    parsed = _int_or_none(value)
    return parsed is not None and lower <= parsed <= upper


def _has_special_limit(row: dict[str, Any], terms: list[str]) -> bool:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ["major_notes", "university_name", "major_name"]
    )
    return any(term and term in haystack for term in terms)


def _missing_recipe_fields(
    domain_config: DomainConfig,
    registry: ReviewedMappingRegistry,
) -> list[str]:
    recipe = (
        domain_config.semantic_capabilities.get("query_recipes") or {}
    ).get(QUERY_TYPE) or {}
    required = recipe.get("required_field_ids") or recipe.get("required_fields") or []
    return [field_id for field_id in required if not registry.has_field(str(field_id))]


def _unsupported_context_intents(
    registry: ReviewedMappingRegistry,
) -> list[dict[str, Any]]:
    return [
        {
            "field_id": field_id,
            "answerable": False,
            "reason": registry.unsupported_reason(field_id)
            or "当前 recipe 未使用该字段执行筛选。",
        }
        for field_id in UNANSWERABLE_CONTEXT_FIELDS
    ]


def _blocked_missing_fields(
    missing_fields: list[str],
    registry: ReviewedMappingRegistry,
) -> AdmissionsMajorRankResult:
    return AdmissionsMajorRankResult(
        query_type=QUERY_TYPE,
        status="blocked",
        rows=[],
        answerable_intents=[],
        unanswerable_intents=[
            {
                "field_id": field_id,
                "answerable": False,
                "reason": registry.unsupported_reason(field_id)
                or "当前数据缺少 admissions_major_rank 必需字段。",
            }
            for field_id in missing_fields
        ],
        execution_summary=_empty_execution_summary(),
        warnings=[
            {
                "code": "missing_recipe_fields",
                "severity": "error",
                "message": "当前数据缺少 admissions_major_rank 必需字段。",
                "missing_fields": missing_fields,
            }
        ],
    )


def _parse_rank(text: str) -> int | None:
    match = re.search(r"(\d{1,3}(?:[,，]\d{3})+|\d+)\s*(?:名|位次|排名)", text)
    if not match:
        return None
    return int(match.group(1).replace(",", "").replace("，", ""))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _empty_execution_summary() -> dict[str, Any]:
    return {
        "executor": None,
        "query_type": QUERY_TYPE,
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
        "rank": None,
        "basis": "major_min_rank",
        "verified_query_plan": None,
    }


__all__ = [
    "AdmissionsMajorRankPlanner",
    "AdmissionsMajorRankResult",
]
