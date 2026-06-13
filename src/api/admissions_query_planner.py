"""招生领域 query type planner。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from src.domains import DomainConfig


QUERY_TYPE_GROUP_DETAIL = "group_detail_report"
QUERY_TYPE_RECOMMENDATION = "recommendation"
DEFAULT_LIMIT = 30
SECTION_LIMIT = 5
NUMBER_PATTERN = r"\d+(?:\.\d+)?"


@dataclass(frozen=True)
class AdmissionsQueryResult:
    """planner 执行后的 contract-ready 结果。"""

    query_type: str
    status: str
    rows: list[dict[str, Any]]
    result_sections: dict[str, Any]
    execution_summary: dict[str, Any]
    answer: str
    warnings: list[dict[str, Any]] = field(default_factory=list)
    executed_rules: list[dict[str, Any]] = field(default_factory=list)
    candidates_to_confirm: list[dict[str, Any]] = field(default_factory=list)
    no_schema_field_preferences: list[dict[str, Any]] = field(default_factory=list)
    extracted_preferences: list[dict[str, Any]] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _RecommendationInputs:
    year: int
    requested_year: int | None
    score: int | None
    rank: int | None
    major_terms: list[str]
    school_provinces: list[str]
    no_schema_preferences: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    executed_rules: list[dict[str, Any]]
    candidates_to_confirm: list[dict[str, Any]]


class AdmissionsQueryPlanner:
    """用 admissions domain pack 规划少数明确 query type。"""

    def __init__(self, domain_config: DomainConfig, database_path: str | Path) -> None:
        self.domain_config = domain_config
        self.database_path = Path(database_path)
        self.config = domain_config.payload.get("query_planner") or {}
        self.aliases = _load_json(domain_config.value_aliases_path)

    def run(self, config: Any, user_request: str) -> AdmissionsQueryResult | None:
        query_type = self._detect_query_type(config, user_request)
        if query_type == QUERY_TYPE_GROUP_DETAIL:
            return self._group_detail_report(config, user_request)
        if query_type == QUERY_TYPE_RECOMMENDATION:
            return self._recommendation(config, user_request)
        return None

    def _detect_query_type(self, config: Any, user_request: str) -> str | None:
        forced = _clean_text(config.hard_filters.get("query_type"))
        if forced in {QUERY_TYPE_GROUP_DETAIL, QUERY_TYPE_RECOMMENDATION}:
            return forced
        text = user_request
        if (
            "专业组" in text
            and any(term in text for term in ["组内", "里面", "各个专业"])
            and any(term in text for term in ["录取最高", "最高"])
        ):
            return QUERY_TYPE_GROUP_DETAIL
        if _score_from_inputs(config, text) is not None:
            return QUERY_TYPE_RECOMMENDATION
        return None

    def _group_detail_report(
        self,
        config: Any,
        user_request: str,
    ) -> AdmissionsQueryResult:
        report_config = self.config.get(QUERY_TYPE_GROUP_DETAIL) or {}
        year_info = self._resolve_year(config, user_request)
        warnings = list(year_info["warnings"])
        university_name = _clean_text(
            config.hard_filters.get("university_name")
        ) or _parse_university_name(user_request)
        if not university_name:
            warning = _warning(
                "missing_university_name",
                "缺少院校名称，未执行专业组详情 SQL。",
                severity="error",
            )
            return AdmissionsQueryResult(
                query_type=QUERY_TYPE_GROUP_DETAIL,
                status="needs_confirmation",
                rows=[],
                result_sections={"groups": []},
                execution_summary=_empty_execution_summary(
                    QUERY_TYPE_GROUP_DETAIL,
                    warnings=[warning],
                ),
                answer="请先明确院校名称，才能列出专业组和组内专业明细。",
                warnings=[warning],
            )

        metric_config = report_config.get("default_metric") or {}
        metric_field_id = str(metric_config["field_id"])
        metric_direction = str(metric_config.get("direction") or "DESC").upper()
        warnings.append(
            _warning(
                "metric_default_used",
                "“录取最高”按 domain pack 默认指标：专业组最低分最高。",
                metric=metric_field_id,
                sort=metric_direction,
            )
        )
        fields = report_config.get("fields") or {}
        year_col = self._source(fields["year"])
        university_col = self._source(fields["university_name"])
        group_code_col = self._source(fields["group_code"])
        group_title_col = self._source(fields["group_title"])
        major_code_col = self._source(fields["major_code"])
        major_name_col = self._source(fields["major_name"])
        full_major_col = self._source(fields["full_major_name"])
        group_rank_col = self._source(fields["group_rank"])
        major_rank_col = self._source(fields["major_rank"])
        major_score_col = self._source(fields["major_score"])
        max_score_col = self._source(fields["major_max_score"])
        plan_count_col = self._source(fields["plan_count"])
        metric_col = self._source(metric_field_id)

        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            input_count = _input_row_count(connection, self.domain_config.table_name)
            groups, group_sql, group_params = self._fetch_group_rows(
                connection=connection,
                year_col=year_col,
                university_col=university_col,
                group_code_col=group_code_col,
                group_title_col=group_title_col,
                metric_col=metric_col,
                group_rank_col=group_rank_col,
                year=year_info["year"],
                university_name=university_name,
                direction=metric_direction,
                limit=int(report_config.get("limit") or 5),
            )
            details, detail_sql, detail_params = self._fetch_group_major_rows(
                connection=connection,
                year_col=year_col,
                university_col=university_col,
                group_code_col=group_code_col,
                group_title_col=group_title_col,
                major_code_col=major_code_col,
                major_name_col=major_name_col,
                full_major_col=full_major_col,
                major_score_col=major_score_col,
                major_rank_col=major_rank_col,
                max_score_col=max_score_col,
                plan_count_col=plan_count_col,
                group_codes=[str(row["group_code"]) for row in groups],
                year=year_info["year"],
                university_name=university_name,
            )

        groups_section = _build_group_sections(groups, details)
        rows = [
            {
                self._source(fields["year"]): year_info["year"],
                self._source(fields["university_name"]): university_name,
                self._source(fields["group_code"]): group["group_code"],
                self._source(fields["group_title"]): group["group_title"],
                self._source(metric_field_id): group["group_metric_score"],
                self._source(fields["group_rank"]): group.get("group_min_rank"),
                self._source(fields["major_name"]): (
                    f"{group['group_title']}（{len(group.get('majors', []))} 个专业）"
                ),
            }
            for group in groups_section
        ]
        execution_summary = {
            "executor": "duckdb",
            "query_type": QUERY_TYPE_GROUP_DETAIL,
            "sql": group_sql,
            "params": group_params,
            "detail_sql": detail_sql,
            "detail_params": detail_params,
            "input_row_count": input_count,
            "filtered_row_count": len(groups),
            "nested_result_count": sum(len(group["majors"]) for group in groups_section),
            "group_by": [group_code_col, group_title_col],
            "metric": {
                "field_id": metric_field_id,
                "field": metric_col,
                "direction": metric_direction,
            },
            "sort": [{"field": metric_col, "direction": metric_direction}],
            "top_k": int(report_config.get("limit") or 5),
            "hard_rule_ids": ["planned_year", "planned_university_name"],
            "skipped_soft_rule_ids": [],
            "warnings": warnings,
        }
        status = "ok" if groups else "no_results"
        return AdmissionsQueryResult(
            query_type=QUERY_TYPE_GROUP_DETAIL,
            status=status,
            rows=rows,
            result_sections={"groups": groups_section},
            execution_summary=execution_summary,
            answer=_group_detail_answer(
                university_name=university_name,
                year=year_info["year"],
                requested_year=year_info["requested_year"],
                groups=groups_section,
            ),
            warnings=warnings,
            executed_rules=[
                _rule("planned_year", year_col, "eq", year_info["year"]),
                _rule("planned_university_name", university_col, "contains", university_name),
            ],
            extracted_preferences=[
                {
                    "id": "query_type",
                    "slot": "query_type",
                    "value": QUERY_TYPE_GROUP_DETAIL,
                    "status": "planned",
                }
            ],
            policy={"metric_default": metric_config},
        )

    def _recommendation(
        self,
        config: Any,
        user_request: str,
    ) -> AdmissionsQueryResult:
        policy = self.config.get(QUERY_TYPE_RECOMMENDATION) or {}
        fields = policy.get("fields") or {}
        inputs = self._recommendation_inputs(config, user_request, policy)
        if not inputs.major_terms:
            warning = _warning(
                "missing_major_terms",
                "缺少明确专业关键词，未执行推荐 SQL。",
                severity="error",
            )
            return AdmissionsQueryResult(
                query_type=QUERY_TYPE_RECOMMENDATION,
                status="needs_confirmation",
                rows=[],
                result_sections=_empty_recommendation_sections(),
                execution_summary=_empty_execution_summary(
                    QUERY_TYPE_RECOMMENDATION,
                    warnings=[warning],
                ),
                answer="请先明确专业关键词，系统不能用模糊专业偏好生成推荐。",
                warnings=[warning],
                no_schema_field_preferences=inputs.no_schema_preferences,
            )

        year_col = self._source(fields["year"])
        university_col = self._source(fields["university_name"])
        group_code_col = self._source(fields["group_code"])
        group_title_col = self._source(fields["group_title"])
        major_code_col = self._source(fields["major_code"])
        major_name_col = self._source(fields["major_name"])
        full_major_col = self._source(fields["full_major_name"])
        school_province_col = self._source(fields["school_province"])
        city_col = self._source(fields["city"])
        tuition_col = self._source(fields["tuition"])
        group_score_col = self._source(fields["group_score"])
        group_rank_col = self._source(fields["group_rank"])
        major_score_col = self._source(fields["major_score"])
        major_rank_col = self._source(fields["major_rank"])
        plan_count_col = self._source(fields["plan_count"])
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            input_count = _input_row_count(connection, self.domain_config.table_name)
            rows, sql, params = self._fetch_recommendation_rows(
                connection=connection,
                year_col=year_col,
                university_col=university_col,
                group_code_col=group_code_col,
                group_title_col=group_title_col,
                major_code_col=major_code_col,
                major_name_col=major_name_col,
                full_major_col=full_major_col,
                school_province_col=school_province_col,
                city_col=city_col,
                tuition_col=tuition_col,
                group_score_col=group_score_col,
                group_rank_col=group_rank_col,
                major_score_col=major_score_col,
                major_rank_col=major_rank_col,
                plan_count_col=plan_count_col,
                inputs=inputs,
                policy=policy,
            )

        section_payload = _sectioned_recommendations(
            rows=rows,
            score=inputs.score,
            rank=inputs.rank,
            policy=policy,
        )
        projected_rows = [
            _recommendation_row_to_projected(row, self.domain_config)
            for section in section_payload.values()
            for row in section["items"]
        ]
        metric = "rank_margin" if inputs.rank else "score_margin"
        execution_summary = {
            "executor": "duckdb",
            "query_type": QUERY_TYPE_RECOMMENDATION,
            "sql": sql,
            "params": params,
            "input_row_count": input_count,
            "filtered_row_count": len(rows),
            "group_by": [],
            "metric": metric,
            "sort": [{"field": metric, "direction": "ASC"}],
            "top_k": policy.get("limit") or DEFAULT_LIMIT,
            "hard_rule_ids": [rule["rule_id"] for rule in inputs.executed_rules],
            "skipped_soft_rule_ids": [],
            "nested_result_count": 0,
            "warnings": inputs.warnings,
        }
        status = "needs_confirmation" if inputs.candidates_to_confirm else "ok"
        if not rows:
            status = "no_results"
        return AdmissionsQueryResult(
            query_type=QUERY_TYPE_RECOMMENDATION,
            status=status,
            rows=projected_rows,
            result_sections=section_payload,
            execution_summary=execution_summary,
            answer=_recommendation_answer(
                score=inputs.score,
                rank=inputs.rank,
                sections=section_payload,
                warnings=inputs.warnings,
            ),
            warnings=inputs.warnings,
            executed_rules=inputs.executed_rules,
            candidates_to_confirm=inputs.candidates_to_confirm,
            no_schema_field_preferences=inputs.no_schema_preferences,
            extracted_preferences=_recommendation_extracted_preferences(inputs),
            policy=policy.get("margin_policy") or {},
        )

    def _resolve_year(self, config: Any, user_request: str) -> dict[str, Any]:
        hard_year = _parse_positive_int(config.hard_filters.get("year"))
        requested_year = hard_year or _parse_year(user_request)
        latest = int(self.config.get("latest_available_year") or 0)
        available = self._available_years()
        if latest not in available and available:
            latest = max(available)
        warnings = []
        if requested_year is None:
            warnings.append(
                _warning(
                    "default_year_used",
                    f"未指定年份，默认使用 latest_available_year={latest}。",
                    year=latest,
                )
            )
            return {"year": latest, "requested_year": None, "warnings": warnings}
        if requested_year not in available:
            warnings.append(
                _warning(
                    "requested_year_unavailable",
                    f"请求年份 {requested_year} 不在当前 warehouse 中，改用 {latest}。",
                    requested_year=requested_year,
                    year=latest,
                )
            )
            return {
                "year": latest,
                "requested_year": requested_year,
                "warnings": warnings,
            }
        return {"year": requested_year, "requested_year": requested_year, "warnings": warnings}

    def _available_years(self) -> set[int]:
        year_col = self._source("year")
        sql = (
            f"SELECT DISTINCT {_quote(year_col)} FROM "
            f"{_quote(self.domain_config.table_name)} "
            f"WHERE {_quote(year_col)} IS NOT NULL"
        )
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            return {
                int(row[0])
                for row in connection.execute(sql).fetchall()
                if _parse_positive_int(row[0])
            }

    def _recommendation_inputs(
        self,
        config: Any,
        user_request: str,
        policy: dict[str, Any],
    ) -> _RecommendationInputs:
        year_info = self._resolve_year(config, user_request)
        warnings = list(year_info["warnings"])
        score = _score_from_inputs(config, user_request)
        rank = _rank_from_inputs(config, user_request)
        if score and not rank:
            warnings.append(
                _warning(
                    "score_without_rank",
                    "只提供分数没有位次；系统只按历史最低分 margin 分组，不能判断录取概率。",
                )
            )
        major_terms, candidates = self._major_terms(config, user_request)
        school_provinces = self._school_provinces(config, user_request)
        no_schema, schema_rules = self._schema_sensitive_avoidance_rules(
            user_request,
            policy,
        )
        rules = [
            _rule("planned_year", self._source(policy["fields"]["year"]), "eq", year_info["year"]),
        ]
        if major_terms:
            rules.append(
                _rule(
                    "planned_major_keywords",
                    self._source(policy["fields"]["major_name"]),
                    "contains_any",
                    major_terms,
                )
            )
        if school_provinces:
            rules.append(
                _rule(
                    "planned_school_province",
                    self._source(policy["fields"]["school_province"]),
                    "in",
                    school_provinces,
                )
            )
        rules.extend(schema_rules)
        return _RecommendationInputs(
            year=year_info["year"],
            requested_year=year_info["requested_year"],
            score=score,
            rank=rank,
            major_terms=major_terms,
            school_provinces=school_provinces,
            no_schema_preferences=no_schema,
            warnings=warnings,
            executed_rules=rules,
            candidates_to_confirm=candidates,
        )

    def _major_terms(self, config: Any, user_request: str) -> tuple[list[str], list[dict[str, Any]]]:
        hard = config.hard_filters
        hard_terms = _clean_list(
            hard.get("major_keywords")
            or hard.get("major_exact_terms")
            or hard.get("major_keyword")
        )
        if hard_terms:
            return hard_terms, []
        found = []
        for canonical, aliases in (self.aliases.get("major_aliases") or {}).items():
            if any(alias in user_request for alias in aliases):
                found.append(str(canonical))
        found = _unique(found)
        candidates = []
        for mapping in self.domain_config.workbench.get("reviewed_candidate_mappings") or []:
            if mapping.get("field_id") != "major_name":
                continue
            source_texts = set(mapping.get("source_texts") or [])
            if mapping.get("source_text"):
                source_texts.add(str(mapping["source_text"]))
            matched_source = next(
                (source for source in source_texts if source in user_request),
                None,
            )
            if not matched_source:
                continue
            candidate_id = _candidate_id(
                user_request=user_request,
                source_text=matched_source,
                field_id="major_name",
                field=self.domain_config.source_column("major_name"),
                operator=mapping.get("operator"),
                value=mapping.get("value"),
            )
            if candidate_id in set(config.confirmed_candidates or []):
                found.extend(_clean_list(mapping.get("value")))
                continue
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_text": matched_source,
                    "field_id": "major_name",
                    "field": self.domain_config.source_column("major_name"),
                    "match_type": "partial_match",
                    "operator": mapping.get("operator"),
                    "value": mapping.get("value"),
                    "label": mapping.get("label"),
                    "executable": True,
                    "reason": mapping.get("reason"),
                    "matched_values": [],
                }
            )
        return _unique(found), candidates

    def _school_provinces(self, config: Any, user_request: str) -> list[str]:
        hard = config.hard_filters
        hard_values = _clean_list(
            hard.get("preferred_school_provinces")
            or hard.get("school_provinces")
            or hard.get("school_province")
        )
        if hard_values:
            return hard_values
        if any(term in user_request for term in self.aliases.get("school_province_terms") or []):
            return ["广东"]
        if "广东省" in user_request or "留在广东" in user_request:
            return ["广东"]
        return []

    def _schema_sensitive_avoidance_rules(
        self,
        user_request: str,
        policy: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        no_schema = []
        rules = []
        checks = [
            (
                "school_country_or_region",
                self.aliases.get("overseas_avoidance_terms") or [],
                ["国外", "境外", "海外"],
                "境外办学字段",
            ),
            (
                "cooperation_type",
                self.aliases.get("cooperation_terms") or [],
                ["中外合作", "合作办学", "国际合作"],
                "合作办学类型字段",
            ),
        ]
        for field_id, terms, excluded_values, missing_field in checks:
            matched = next((term for term in terms if term in user_request), None)
            if not matched:
                continue
            source_column = self.domain_config.source_column_or_none(field_id)
            if source_column:
                rules.append(
                    _rule(
                        f"planned_exclude_{field_id}",
                        source_column,
                        "not_in",
                        excluded_values,
                    )
                )
                continue
            no_schema.append(
                {
                    "source_text": matched,
                    "field_id": field_id,
                    "field": "无可执行字段",
                    "match_type": "no_schema_field",
                    "executable": False,
                    "reason": f"当前 domain pack 未启用{missing_field}，不能执行该排除条件。",
                }
            )
        return no_schema, rules

    def _fetch_group_rows(self, **kwargs: Any) -> tuple[list[dict[str, Any]], str, list[Any]]:
        connection = kwargs["connection"]
        direction = "DESC" if kwargs["direction"] == "DESC" else "ASC"
        table = _quote(self.domain_config.table_name)
        metric_expr = _numeric_expr(kwargs["metric_col"])
        rank_expr = _numeric_expr(kwargs["group_rank_col"])
        sql = f"""
SELECT
  CAST({_quote(kwargs["group_code_col"])} AS VARCHAR) AS group_code,
  ANY_VALUE(CAST({_quote(kwargs["group_title_col"])} AS VARCHAR)) AS group_title,
  MAX({metric_expr}) AS group_metric_score,
  MIN({rank_expr}) AS group_min_rank,
  COUNT(*) AS major_count
FROM {table}
WHERE {_numeric_expr(kwargs["year_col"])} = ?
  AND STRPOS(CAST({_quote(kwargs["university_col"])} AS VARCHAR), ?) > 0
  AND {_quote(kwargs["group_code_col"])} IS NOT NULL
GROUP BY CAST({_quote(kwargs["group_code_col"])} AS VARCHAR)
ORDER BY group_metric_score {direction} NULLS LAST, group_code ASC
LIMIT ?
""".strip()
        params = [kwargs["year"], kwargs["university_name"], kwargs["limit"]]
        rows = [
            dict(row)
            for row in connection.execute(sql, params).fetchdf().to_dict("records")
        ]
        return rows, sql, params

    def _fetch_group_major_rows(self, **kwargs: Any) -> tuple[list[dict[str, Any]], str, list[Any]]:
        group_codes = kwargs["group_codes"]
        if not group_codes:
            return [], "", []
        connection = kwargs["connection"]
        table = _quote(self.domain_config.table_name)
        placeholders = ", ".join(["?"] * len(group_codes))
        sql = f"""
SELECT
  CAST({_quote(kwargs["group_code_col"])} AS VARCHAR) AS group_code,
  CAST({_quote(kwargs["group_title_col"])} AS VARCHAR) AS group_title,
  CAST({_quote(kwargs["major_code_col"])} AS VARCHAR) AS major_code,
  CAST({_quote(kwargs["major_name_col"])} AS VARCHAR) AS major_name,
  CAST({_quote(kwargs["full_major_col"])} AS VARCHAR) AS full_major_name,
  {_numeric_expr(kwargs["major_score_col"])} AS min_score,
  {_numeric_expr(kwargs["major_rank_col"])} AS min_rank,
  {_numeric_expr(kwargs["max_score_col"])} AS max_score,
  {_numeric_expr(kwargs["plan_count_col"])} AS plan_count
FROM {table}
WHERE {_numeric_expr(kwargs["year_col"])} = ?
  AND STRPOS(CAST({_quote(kwargs["university_col"])} AS VARCHAR), ?) > 0
  AND CAST({_quote(kwargs["group_code_col"])} AS VARCHAR) IN ({placeholders})
ORDER BY group_code ASC, min_score DESC NULLS LAST, major_code ASC
""".strip()
        params = [kwargs["year"], kwargs["university_name"], *group_codes]
        rows = [
            dict(row)
            for row in connection.execute(sql, params).fetchdf().to_dict("records")
        ]
        return rows, sql, params

    def _fetch_recommendation_rows(self, **kwargs: Any) -> tuple[list[dict[str, Any]], str, list[Any]]:
        inputs: _RecommendationInputs = kwargs["inputs"]
        policy = kwargs["policy"]
        table = _quote(self.domain_config.table_name)
        conditions = [f"{_numeric_expr(kwargs['year_col'])} = ?"]
        params: list[Any] = [inputs.year]
        if inputs.school_provinces:
            conditions.append(
                f"CAST({_quote(kwargs['school_province_col'])} AS VARCHAR) "
                f"IN ({_placeholders(inputs.school_provinces)})"
            )
            params.extend(inputs.school_provinces)
        if inputs.major_terms:
            clauses = []
            for term in inputs.major_terms:
                clauses.append(f"STRPOS(CAST({_quote(kwargs['major_name_col'])} AS VARCHAR), ?) > 0")
                params.append(term)
            conditions.append("(" + " OR ".join(clauses) + ")")
        for rule in inputs.executed_rules:
            if not str(rule["rule_id"]).startswith("planned_exclude_"):
                continue
            values = _clean_list(rule.get("value"))
            conditions.append(
                f"CAST({_quote(str(rule['field']))} AS VARCHAR) "
                f"NOT IN ({_placeholders(values)})"
            )
            params.extend(values)
        margin = policy.get("margin_policy") or {}
        order_metric = ""
        if inputs.rank:
            rank_expr = _numeric_expr(kwargs["group_rank_col"])
            rank_window = margin.get("rank_margin") or {}
            lower = max(1, inputs.rank - int(rank_window.get("reach_max_abs") or 8000))
            upper = inputs.rank + int(rank_window.get("safety_min") or 30000)
            conditions.append(f"{rank_expr} BETWEEN ? AND ?")
            params.extend([lower, upper])
            order_metric = f"ABS({rank_expr} - ?)"
            order_params = [inputs.rank]
        elif inputs.score:
            score_expr = _numeric_expr(kwargs["group_score_col"])
            score_window = margin.get("score_margin") or {}
            lower = inputs.score - int(score_window.get("reach_max_abs") or 30)
            upper = inputs.score + int(score_window.get("safety_min") or 30)
            conditions.append(f"{score_expr} BETWEEN ? AND ?")
            params.extend([lower, upper])
            order_metric = f"ABS(? - {score_expr})"
            order_params = [inputs.score]
        else:
            order_metric = _numeric_expr(kwargs["group_rank_col"])
            order_params = []
        where_sql = " AND ".join(conditions)
        sql = f"""
SELECT
  {_quote(kwargs["year_col"])} AS year,
  {_quote(kwargs["university_col"])} AS university_name,
  {_quote(kwargs["group_code_col"])} AS group_code,
  {_quote(kwargs["group_title_col"])} AS group_title,
  {_quote(kwargs["major_code_col"])} AS major_code,
  {_quote(kwargs["major_name_col"])} AS major_name,
  {_quote(kwargs["full_major_col"])} AS full_major_name,
  {_quote(kwargs["school_province_col"])} AS school_province,
  {_quote(kwargs["city_col"])} AS city,
  {_quote(kwargs["tuition_col"])} AS tuition,
  {_numeric_expr(kwargs["group_score_col"])} AS group_min_score,
  {_numeric_expr(kwargs["group_rank_col"])} AS group_min_rank,
  {_numeric_expr(kwargs["major_score_col"])} AS major_min_score,
  {_numeric_expr(kwargs["major_rank_col"])} AS major_min_rank,
  {_numeric_expr(kwargs["plan_count_col"])} AS plan_count
FROM {table}
WHERE {where_sql}
ORDER BY {order_metric} ASC NULLS LAST, group_min_score DESC NULLS LAST
LIMIT ?
""".strip()
        final_params = params + order_params + [int(policy.get("limit") or DEFAULT_LIMIT)]
        rows = [
            dict(row)
            for row in kwargs["connection"].execute(sql, final_params).fetchdf().to_dict("records")
        ]
        return rows, sql, final_params

    def _source(self, field_id: str) -> str:
        return self.domain_config.source_column(field_id)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _input_row_count(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    return int(
        connection.execute(f"SELECT count(*) FROM {_quote(table_name)}").fetchone()[0]
    )


def _build_group_sections(
    groups: list[dict[str, Any]],
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    details_by_group: dict[str, list[dict[str, Any]]] = {}
    for row in details:
        details_by_group.setdefault(str(row["group_code"]), []).append(
            {
                "major_code": row.get("major_code"),
                "major_name": row.get("major_name"),
                "full_major_name": row.get("full_major_name"),
                "min_score": _int_or_none(row.get("min_score")),
                "min_rank": _int_or_none(row.get("min_rank")),
                "max_score": _int_or_none(row.get("max_score")),
                "plan_count": _int_or_none(row.get("plan_count")),
            }
        )
    return [
        {
            "group_code": group.get("group_code"),
            "group_title": group.get("group_title") or group.get("group_code"),
            "group_metric_score": _int_or_none(group.get("group_metric_score")),
            "group_min_rank": _int_or_none(group.get("group_min_rank")),
            "major_count": _int_or_none(group.get("major_count")),
            "majors": details_by_group.get(str(group.get("group_code")), []),
        }
        for group in groups
    ]


def _sectioned_recommendations(
    rows: list[dict[str, Any]],
    score: int | None,
    rank: int | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    sections = {
        "reach": {"label": "冲", "items": []},
        "match": {"label": "稳", "items": []},
        "safety": {"label": "保", "items": []},
    }
    margin_policy = policy.get("margin_policy") or {}
    for row in rows:
        item = dict(row)
        if rank and _int_or_none(row.get("group_min_rank")) is not None:
            rank_margin = int(row["group_min_rank"]) - rank
            item["rank_margin"] = rank_margin
            key = _rank_section(rank_margin, margin_policy.get("rank_margin") or {})
        elif score and _int_or_none(row.get("group_min_score")) is not None:
            score_margin = score - int(row["group_min_score"])
            item["score_margin"] = score_margin
            key = _score_section(score_margin, margin_policy.get("score_margin") or {})
        else:
            key = "match"
        if len(sections[key]["items"]) < SECTION_LIMIT:
            sections[key]["items"].append(_recommendation_section_item(item))
    return sections


def _rank_section(rank_margin: int, policy: dict[str, Any]) -> str:
    if rank_margin < 0:
        return "reach"
    if rank_margin <= int(policy.get("match_max") or 15000):
        return "match"
    return "safety"


def _score_section(score_margin: int, policy: dict[str, Any]) -> str:
    if score_margin < 0:
        return "reach"
    if score_margin <= int(policy.get("match_max") or 20):
        return "match"
    return "safety"


def _recommendation_section_item(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "year",
        "university_name",
        "group_code",
        "group_title",
        "major_code",
        "major_name",
        "full_major_name",
        "school_province",
        "city",
        "tuition",
        "group_min_score",
        "group_min_rank",
        "major_min_score",
        "major_min_rank",
        "plan_count",
        "score_margin",
        "rank_margin",
    ]
    return {key: _json_scalar(row.get(key)) for key in keys if key in row}


def _recommendation_row_to_projected(
    row: dict[str, Any],
    domain_config: DomainConfig,
) -> dict[str, Any]:
    mapping = {
        "year": "year",
        "university_name": "university_name",
        "group_code": "group_code",
        "group_title": "group_name",
        "major_code": "major_code",
        "major_name": "major_name",
        "full_major_name": "full_major_name",
        "school_province": "school_province",
        "city": "city",
        "tuition": "tuition_yuan_per_year",
        "group_min_rank": "group_min_rank_2024",
        "major_min_rank": "major_min_rank_2024",
        "plan_count": "plan_count",
    }
    projected = {}
    for source_key, field_id in mapping.items():
        source_column = domain_config.source_column_or_none(field_id)
        if source_column:
            projected[source_column] = _json_scalar(row.get(source_key))
    projected["group_min_score"] = _json_scalar(row.get("group_min_score"))
    projected["score_margin"] = _json_scalar(row.get("score_margin"))
    projected["rank_margin"] = _json_scalar(row.get("rank_margin"))
    return projected


def _group_detail_answer(
    university_name: str,
    year: int,
    requested_year: int | None,
    groups: list[dict[str, Any]],
) -> str:
    if not groups:
        return f"未找到 {year} 年 {university_name} 的专业组录取明细。"
    year_text = f"{year} 年"
    if requested_year and requested_year != year:
        year_text = f"{requested_year} 年请求已改用当前可用的 {year} 年"
    first = groups[0]
    return (
        f"按 {year_text} 数据，{university_name} 录取分数最高的专业组是 "
        f"{first['group_code']}（{first['group_title']}），专业组最低分为 "
        f"{first['group_metric_score']}。以下 sections.groups 展开了组内专业最低分。"
    )


def _recommendation_answer(
    score: int | None,
    rank: int | None,
    sections: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> str:
    total = sum(len(section["items"]) for section in sections.values())
    metric = "位次 margin" if rank else "分数 margin"
    basis = f"位次 {rank}" if rank else f"分数 {score}"
    warning_text = ""
    if warnings:
        warning_text = "；" + "；".join(warning["message"] for warning in warnings[:2])
    return (
        f"基于历史最低分/最低位次和{basis}，按{metric}分为冲、稳、保，"
        f"共返回 {total} 条分组结果。该分组不是录取概率判断{warning_text}。"
    )


def _recommendation_extracted_preferences(
    inputs: _RecommendationInputs,
) -> list[dict[str, Any]]:
    items = [
        {
            "id": "pref_major",
            "slot": "专业名称",
            "value": inputs.major_terms,
            "status": "已对齐字段",
        }
    ]
    if inputs.score:
        items.append(
            {
                "id": "pref_score",
                "slot": "分数",
                "value": inputs.score,
                "status": "仅用于 score_margin",
            }
        )
    if inputs.rank:
        items.append(
            {
                "id": "pref_rank",
                "slot": "排位",
                "value": inputs.rank,
                "status": "优先用于 rank_margin",
            }
        )
    if inputs.school_provinces:
        items.append(
            {
                "id": "pref_school_province",
                "slot": "院校所在地省份",
                "value": inputs.school_provinces,
                "status": "已对齐字段",
            }
        )
    return items


def _empty_recommendation_sections() -> dict[str, Any]:
    return {
        "reach": {"label": "冲", "items": []},
        "match": {"label": "稳", "items": []},
        "safety": {"label": "保", "items": []},
    }


def _empty_execution_summary(
    query_type: str,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "executor": None,
        "query_type": query_type,
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
        "nested_result_count": 0,
        "group_by": [],
        "metric": None,
        "sort": [],
        "top_k": 0,
        "hard_rule_ids": [],
        "skipped_soft_rule_ids": [],
        "warnings": warnings or [],
    }


def _rule(rule_id: str, field: str, operator: str, value: Any) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "field": field,
        "operator": operator,
        "value": value,
    }


def _warning(
    code: str,
    message: str,
    *,
    severity: str = "warning",
    **extra: Any,
) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, **extra}


def _score_from_inputs(config: Any, text: str) -> int | None:
    hard_score = _parse_positive_int(
        config.hard_filters.get("user_score") or config.hard_filters.get("score")
    )
    if hard_score:
        return hard_score
    match = re.search(rf"(?:高考)?(?:分数|成绩)?\s*({NUMBER_PATTERN})\s*分", text)
    if match:
        return _parse_positive_int(match.group(1))
    match = re.search(rf"(?:高考分数|分数|成绩)\s*({NUMBER_PATTERN})", text)
    return _parse_positive_int(match.group(1)) if match else None


def _rank_from_inputs(config: Any, text: str) -> int | None:
    hard_rank = _parse_positive_int(config.hard_filters.get("user_rank"))
    if hard_rank:
        return hard_rank
    match = re.search(r"(?:排位|位次|排名|省排|省排名)\s*(\d+)", text)
    return _parse_positive_int(match.group(1)) if match else None


def _parse_year(text: str) -> int | None:
    match = re.search(r"(20\d{2})\s*年?", text)
    return int(match.group(1)) if match else None


def _parse_university_name(text: str) -> str | None:
    candidates = re.findall(r"([\u4e00-\u9fa5A-Za-z（）()]{2,}(?:大学|学院))", text)
    for candidate in candidates:
        cleaned = re.split(r"[年月日]", candidate)[-1]
        cleaned = re.sub(r"^(列出|查看|查询|请问|请列出)", "", cleaned)
        if cleaned:
            return cleaned
    return None


def _parse_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_list(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        values = re.split(r"[、,，/ ]+", value)
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return _unique([str(item).strip() for item in values if str(item).strip()])


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _candidate_id(
    *,
    user_request: str,
    source_text: str,
    field_id: str,
    field: str,
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
    return "cand_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _numeric_expr(column: str) -> str:
    return (
        "TRY_CAST(regexp_extract(REPLACE(CAST("
        f"{_quote(column)} AS VARCHAR), ',', ''), '{NUMBER_PATTERN}') AS DOUBLE)"
    )


def _quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _placeholders(values: list[Any]) -> str:
    return ", ".join(["?"] * len(values))


def _int_or_none(value: Any) -> int | None:
    parsed = _parse_positive_int(value)
    return parsed if parsed is not None else None


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value
