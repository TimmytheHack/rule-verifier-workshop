"""基于 DuckDB 执行已验证 hard rules。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from src.adapters.data_warehouse import DEFAULT_TABLE_NAME
from src.executors.pandas_executor import clean_value, parse_number, cell_text


NUMERIC_PATTERN = r"\d+(?:\.\d+)?"
SORT_KEY = [
    "专业组最低位次1 ASC NULLS LAST",
    "院校排名 ASC NULLS LAST",
    "ID ASC NULLS LAST",
]


@dataclass(frozen=True)
class ExecutionAudit:
    """执行层证据，只记录 hard filter SQL 和统计信息。"""

    executor: str
    sql: str
    params: list[Any]
    input_row_count: int
    filtered_row_count: int
    sort_key: list[str]
    top_k: int
    hard_rule_ids: list[str]
    skipped_soft_rule_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "executor": self.executor,
            "sql": self.sql,
            "params": self.params,
            "input_row_count": self.input_row_count,
            "filtered_row_count": self.filtered_row_count,
            "sort_key": self.sort_key,
            "top_k": self.top_k,
            "hard_rule_ids": self.hard_rule_ids,
            "skipped_soft_rule_ids": self.skipped_soft_rule_ids,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """执行结果和对应的审计信息。"""

    rows: list[dict[str, Any]]
    audit: ExecutionAudit


class DuckDBExecutor:
    """把已验证 hard rules 编译为参数化 DuckDB SQL。"""

    def __init__(
        self,
        database_path: str | Path,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> None:
        self.database_path = Path(database_path)
        self.table_name = table_name

    def execute(
        self,
        executable_rules: list[dict[str, Any]],
        user_rank: int | None = None,
        top_k: int = 5,
    ) -> ExecutionResult:
        hard_rules, skipped_soft_rules = hard_filter_rules(executable_rules)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            columns = _table_columns(connection, self.table_name)
            compiled = _compile_select_sql(
                table_name=self.table_name,
                columns=columns,
                hard_rules=hard_rules,
            )
            input_row_count = _input_row_count(connection, self.table_name)
            filtered_row_count = int(
                connection.execute(
                    compiled.count_sql,
                    compiled.params,
                ).fetchone()[0]
            )
            dataframe = connection.execute(
                compiled.select_sql,
                compiled.params,
            ).fetchdf()

        rows = [
            _project_row(row.to_dict(), user_rank=user_rank)
            for _, row in dataframe.iterrows()
        ]
        return ExecutionResult(
            rows=[row for row in rows if row is not None],
            audit=ExecutionAudit(
                executor="duckdb",
                sql=compiled.select_sql,
                params=list(compiled.params),
                input_row_count=input_row_count,
                filtered_row_count=filtered_row_count,
                sort_key=list(SORT_KEY),
                top_k=top_k,
                hard_rule_ids=[str(rule.get("rule_id")) for rule in hard_rules],
                skipped_soft_rule_ids=[
                    str(rule.get("rule_id")) for rule in skipped_soft_rules
                ],
            ),
        )


@dataclass(frozen=True)
class _CompiledSQL:
    select_sql: str
    count_sql: str
    params: list[Any]


def hard_filter_rules(
    executable_rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """拆分真正 hard filters 和不能进入 SQL hard filter 的规则。"""

    hard_rules = []
    skipped_soft_rules = []
    for rule in executable_rules:
        if _is_soft_confirmation_rule(rule) or rule.get("hard_filter_allowed") is False:
            skipped_soft_rules.append(rule)
            continue
        hard_rules.append(rule)
    return hard_rules, skipped_soft_rules


def _is_soft_confirmation_rule(rule: dict[str, Any]) -> bool:
    derived_from = str(rule.get("derived_from") or "")
    return bool(
        derived_from.startswith("c_")
        or rule.get("verification_origin") == "verified_proposed_rule"
    )


def _compile_select_sql(
    table_name: str,
    columns: set[str],
    hard_rules: list[dict[str, Any]],
) -> _CompiledSQL:
    for required in ["专业组最低位次1", "学费"]:
        if required not in columns:
            raise ValueError(f"DuckDBExecutor missing required output column: {required}")

    params: list[Any] = []
    conditions = []
    for rule in hard_rules:
        condition, condition_params = _compile_rule(rule, columns)
        conditions.append(condition)
        params.extend(condition_params)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    table_sql = _quote_identifier(table_name)
    group_rank_expr = _numeric_expression("专业组最低位次1")
    tuition_expr = _numeric_expression("学费")
    school_rank_expr = (
        _numeric_expression("院校排名") if "院校排名" in columns else "NULL"
    )
    id_expr = _numeric_expression("ID") if "ID" in columns else "NULL"
    cte = f"""
WITH source AS (
  SELECT row_number() OVER () AS "__source_row_number", *
  FROM {table_sql}
),
filtered AS (
  SELECT
    source.*,
    {group_rank_expr} AS "__group_rank_num",
    {tuition_expr} AS "__tuition_num",
    {school_rank_expr} AS "__school_rank_num",
    {id_expr} AS "__id_num"
  FROM source
  WHERE {where_clause}
),
projectable AS (
  SELECT *
  FROM filtered
  WHERE "__group_rank_num" IS NOT NULL
    AND "__tuition_num" IS NOT NULL
)
""".strip()
    select_sql = f"""
{cte}
SELECT *
FROM projectable
ORDER BY
  "__group_rank_num" ASC NULLS LAST,
  "__school_rank_num" ASC NULLS LAST,
  "__id_num" ASC NULLS LAST
""".strip()
    count_sql = f"{cte}\nSELECT count(*) FROM projectable"
    return _CompiledSQL(select_sql=select_sql, count_sql=count_sql, params=params)


def _compile_rule(
    rule: dict[str, Any],
    columns: set[str],
) -> tuple[str, list[Any]]:
    field = str(rule.get("field") or "")
    if field not in columns:
        raise ValueError(f"DuckDBExecutor cannot compile unknown field: {field}")
    operator = str(rule.get("operator") or "")
    value = rule.get("value")
    column = _quote_identifier(field)
    text_expr = f"CAST({column} AS VARCHAR)"

    if operator == "eq":
        return f"{text_expr} = ?", [cell_text(value)]
    if operator == "contains":
        return f"STRPOS({text_expr}, ?) > 0", [cell_text(value)]
    if operator in {"in_contains", "contains_any"}:
        values = _value_list(value)
        if not values:
            raise ValueError(f"DuckDBExecutor rule has empty value list: {rule}")
        return (
            "(" + " OR ".join([f"STRPOS({text_expr}, ?) > 0"] * len(values)) + ")",
            [cell_text(item) for item in values],
        )
    if operator == "in":
        values = _value_list(value)
        if not values:
            raise ValueError(f"DuckDBExecutor rule has empty value list: {rule}")
        return (
            f"{text_expr} IN ({_placeholders(values)})",
            [cell_text(item) for item in values],
        )
    if operator == "not_in":
        values = _value_list(value)
        if not values:
            raise ValueError(f"DuckDBExecutor rule has empty value list: {rule}")
        return (
            f"{text_expr} NOT IN ({_placeholders(values)})",
            [cell_text(item) for item in values],
        )
    if operator in {">=", "<="}:
        threshold = parse_number(value)
        if threshold is None:
            raise ValueError(f"DuckDBExecutor rule has invalid numeric value: {rule}")
        numeric = _numeric_expression(field)
        return f"{numeric} {operator} ?", [threshold]
    if operator == "between":
        lower, upper = _numeric_range(value)
        if lower is None or upper is None:
            raise ValueError(f"DuckDBExecutor rule has invalid numeric range: {rule}")
        numeric = _numeric_expression(field)
        return f"({numeric} >= ? AND {numeric} <= ?)", [lower, upper]
    if operator == "satisfies_subject_requirement":
        return _compile_subject_requirement(column, value)
    raise ValueError(f"DuckDBExecutor cannot compile operator: {operator}")


def _compile_subject_requirement(
    column: str,
    selected_subjects: Any,
) -> tuple[str, list[Any]]:
    selected = {
        _normalize_subject(subject)
        for subject in _value_list(selected_subjects)
        if _normalize_subject(subject)
    }
    if not selected:
        text_expr = f"CAST({column} AS VARCHAR)"
        return _no_subject_requirement_condition(text_expr), []

    unselected = [subject for subject in ["化学", "生物", "政治", "地理"] if subject not in selected]
    text_expr = (
        f"REPLACE(REPLACE(CAST({column} AS VARCHAR), '思想政治', '政治'), "
        "'生物学', '生物')"
    )
    no_requirement = _no_subject_requirement_condition(text_expr)
    or_condition = (
        "("
        + " OR ".join([f"STRPOS({text_expr}, ?) > 0"] * len(selected))
        + ")"
    )
    non_or_parts = [f"STRPOS({text_expr}, ?) = 0" for _ in unselected]
    non_or_condition = " AND ".join(non_or_parts) if non_or_parts else "TRUE"
    selected_values = sorted(selected)
    params = selected_values + unselected
    return (
        f"({no_requirement} OR ((STRPOS({text_expr}, '或') > 0 OR "
        f"STRPOS({text_expr}, '/') > 0) AND {or_condition}) OR "
        f"((STRPOS({text_expr}, '或') = 0 AND STRPOS({text_expr}, '/') = 0) "
        f"AND {non_or_condition}))",
        params,
    )


def _no_subject_requirement_condition(text_expr: str) -> str:
    return (
        f"({text_expr} IS NULL OR TRIM({text_expr}) = '' OR {text_expr} = 'nan' "
        f"OR {text_expr} = '无' OR STRPOS({text_expr}, '不限') > 0)"
    )


def _project_row(
    row: dict[str, Any],
    user_rank: int | None,
) -> dict[str, Any] | None:
    group_rank = parse_number(row.get("__group_rank_num"))
    tuition = parse_number(row.get("__tuition_num"))
    if group_rank is None or tuition is None:
        return None
    ranking_key = int(group_rank - user_rank) if user_rank else None
    safety_margin_pct = (
        round((group_rank - user_rank) / user_rank, 4)
        if user_rank
        else None
    )
    source_row_number = parse_number(row.get("__source_row_number"))
    excel_row_number = int(source_row_number) + 3 if source_row_number else None
    return {
        "excel_row_number": excel_row_number,
        "ID": clean_value(row.get("ID")),
        "年份": clean_value(row.get("年份")),
        "批次": clean_value(row.get("批次")),
        "院校代码": clean_value(row.get("院校代码")),
        "院校名称": clean_value(row.get("院校名称")),
        "院校专业组代码": clean_value(row.get("院校专业组代码")),
        "专业组名称": clean_value(row.get("专业组名称")),
        "科类": clean_value(row.get("科类")),
        "选科要求": clean_value(row.get("选科要求")),
        "专业代码": clean_value(row.get("专业代码")),
        "专业名称": cell_text(row.get("专业名称")),
        "专业全称": clean_value(row.get("专业全称")),
        "所在省": clean_value(row.get("所在省")),
        "城市": cell_text(row.get("城市")),
        "学费": tuition,
        "专业组最低位次1": int(group_rank),
        "最低位次1": clean_value(row.get("最低位次1")),
        "院校标签": clean_value(row.get("院校标签")),
        "院校排名": clean_value(row.get("院校排名")),
        "ranking_key": ranking_key,
        "safety_margin_pct": safety_margin_pct,
        "cooperation_filter_status": "not_executed_missing_cooperation_type_field",
        "中外合作筛选状态": "未执行：缺少合作办学类型字段",
    }


def _table_columns(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        f"DESCRIBE SELECT * FROM {_quote_identifier(table_name)}"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _input_row_count(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> int:
    return int(
        connection.execute(
            f"SELECT count(*) FROM {_quote_identifier(table_name)}"
        ).fetchone()[0]
    )


def _numeric_expression(field: str) -> str:
    column = _quote_identifier(field)
    return (
        "TRY_CAST("
        f"regexp_extract(REPLACE(CAST({column} AS VARCHAR), ',', ''), "
        f"'{NUMERIC_PATTERN}') AS DOUBLE)"
    )


def _value_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _numeric_range(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, list) or len(value) != 2:
        return None, None
    first = parse_number(value[0])
    second = parse_number(value[1])
    if first is None or second is None:
        return None, None
    return min(first, second), max(first, second)


def _normalize_subject(value: Any) -> str:
    text = cell_text(value)
    if "思想政治" in text:
        return "政治"
    if "生物" in text:
        return "生物"
    for subject in ["化学", "政治", "地理"]:
        if subject in text:
            return subject
    return text


def _placeholders(values: list[Any]) -> str:
    return ", ".join(["?"] * len(values))


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
