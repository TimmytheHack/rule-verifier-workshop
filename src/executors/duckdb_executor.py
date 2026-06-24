"""基于 DuckDB 执行已验证 hard rules。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from src.adapters.data_warehouse import DEFAULT_TABLE_NAME
from src.domains import DomainConfig
from src.executors.pandas_executor import clean_value, parse_number, cell_text


NUMERIC_PATTERN = r"\d+(?:\.\d+)?"


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
        table_name: str | None = None,
        domain_config: DomainConfig | None = None,
    ) -> None:
        self.domain_config = domain_config or DomainConfig.load()
        self.database_path = Path(database_path)
        self.table_name = table_name or self.domain_config.table_name or DEFAULT_TABLE_NAME

    def execute(
        self,
        executable_rules: list[dict[str, Any]],
        user_rank: int | None = None,
        top_k: int = 5,
        sort_policy_override: list[dict[str, Any]] | None = None,
    ) -> ExecutionResult:
        hard_rules, skipped_soft_rules = hard_filter_rules(executable_rules)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            columns = _table_columns(connection, self.table_name)
            compiled = _compile_select_sql(
                table_name=self.table_name,
                columns=columns,
                hard_rules=hard_rules,
                domain_config=self.domain_config,
                sort_policy_override=sort_policy_override,
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
            _project_row(
                row.to_dict(),
                user_rank=user_rank,
                domain_config=self.domain_config,
            )
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
                sort_key=_sort_key_labels(
                    self.domain_config,
                    columns,
                    sort_policy_override=sort_policy_override,
                ),
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
        if _should_skip_hard_filter(rule):
            skipped_soft_rules.append(rule)
            continue
        hard_rules.append(rule)
    return hard_rules, skipped_soft_rules


def _should_skip_hard_filter(rule: dict[str, Any]) -> bool:
    verified_entity_link = (
        rule.get("verification_origin") == "verified_proposed_rule"
        and rule.get("proposed_by") == "reviewed_value_entity_linker"
    )
    return bool(
        rule.get("hard_filter_allowed") is False
        or (
            rule.get("verification_origin") == "verified_proposed_rule"
            and not verified_entity_link
        )
    )


def _compile_select_sql(
    table_name: str,
    columns: set[str],
    hard_rules: list[dict[str, Any]],
    domain_config: DomainConfig,
    sort_policy_override: list[dict[str, Any]] | None = None,
) -> _CompiledSQL:
    helper_fields = _numeric_helper_fields(domain_config, columns)
    required_helpers = []
    for field_id in domain_config.execution.get("projectable_required_field_ids") or []:
        required = domain_config.source_column(field_id)
        if required not in columns:
            raise ValueError(f"DuckDBExecutor missing required output column: {required}")
        helper_name = _helper_name_for_field(helper_fields, field_id)
        if helper_name:
            required_helpers.append(helper_name)

    params: list[Any] = []
    conditions = []
    for rule in hard_rules:
        condition, condition_params = _compile_rule(rule, columns, domain_config)
        conditions.append(condition)
        params.extend(condition_params)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    table_sql = _quote_identifier(table_name)
    helper_selects = [
        f"    {helper.expression} AS {_quote_identifier(helper.name)}"
        for helper in helper_fields
    ]
    helper_sql = ",\n" + ",\n".join(helper_selects) if helper_selects else ""
    projectable_conditions = [
        f"    AND {_quote_identifier(helper_name)} IS NOT NULL"
        for helper_name in required_helpers
    ]
    projectable_sql = "\n".join(projectable_conditions)
    order_clause = _order_clause(domain_config, columns, sort_policy_override)
    cte = f"""
WITH source AS (
  SELECT row_number() OVER () AS "__source_row_number", *
  FROM {table_sql}
),
filtered AS (
  SELECT
    source.*{helper_sql}
  FROM source
  WHERE {where_clause}
),
projectable AS (
  SELECT *
  FROM filtered
  WHERE TRUE
{projectable_sql}
)
""".strip()
    select_sql = f"""
{cte}
SELECT *
FROM projectable
{order_clause}
""".strip()
    count_sql = f"{cte}\nSELECT count(*) FROM projectable"
    return _CompiledSQL(select_sql=select_sql, count_sql=count_sql, params=params)


def _compile_rule(
    rule: dict[str, Any],
    columns: set[str],
    domain_config: DomainConfig,
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
        return _compile_subject_requirement(column, value, domain_config)
    raise ValueError(f"DuckDBExecutor cannot compile operator: {operator}")


def _compile_subject_requirement(
    column: str,
    selected_subjects: Any,
    domain_config: DomainConfig,
) -> tuple[str, list[Any]]:
    policy = domain_config.subject_policy
    subjects = policy.get("subjects") or []
    replacements = policy.get("normalization") or {}
    selected = {
        _normalize_subject(subject, domain_config)
        for subject in _value_list(selected_subjects)
        if _normalize_subject(subject, domain_config)
    }
    if not selected:
        text_expr = f"CAST({column} AS VARCHAR)"
        return _no_subject_requirement_condition(text_expr, domain_config), []

    unselected = [subject for subject in subjects if subject not in selected]
    text_expr = f"CAST({column} AS VARCHAR)"
    for source, target in replacements.items():
        text_expr = f"REPLACE({text_expr}, {_sql_string(source)}, {_sql_string(target)})"
    no_requirement = _no_subject_requirement_condition(text_expr, domain_config)
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


def _no_subject_requirement_condition(
    text_expr: str,
    domain_config: DomainConfig,
) -> str:
    values = domain_config.subject_policy.get("no_requirement_values") or []
    exact_checks = [
        f"{text_expr} = {_sql_string(value)}"
        for value in values
        if str(value) and str(value) != "不限"
    ]
    contains_checks = [
        f"STRPOS({text_expr}, {_sql_string(value)}) > 0"
        for value in values
        if str(value) == "不限"
    ]
    checks = [f"{text_expr} IS NULL", f"TRIM({text_expr}) = ''"]
    checks.extend(exact_checks)
    checks.extend(contains_checks)
    return "(" + " OR ".join(checks) + ")"


def _project_row(
    row: dict[str, Any],
    user_rank: int | None,
    domain_config: DomainConfig,
) -> dict[str, Any] | None:
    source_row_number = parse_number(row.get("__source_row_number"))
    output: dict[str, Any] = {}
    row_number_key = domain_config.execution.get("row_number_output_key")
    if row_number_key:
        offset = int(domain_config.execution.get("row_number_offset") or 0)
        output[row_number_key] = (
            int(source_row_number) + offset if source_row_number else None
        )

    for spec in domain_config.execution.get("output_fields") or []:
        output_key = spec["output_key"]
        field_id = spec["field_id"]
        source_column = domain_config.source_column(field_id)
        helper = spec.get("helper")
        raw_value = row.get(helper) if helper else row.get(source_column)
        output[output_key] = _project_value(raw_value, spec.get("transform"))

    ranking = domain_config.execution.get("ranking") or {}
    rank_field_id = ranking.get("source_field_id")
    if rank_field_id:
        rank_value = _projected_field_value(output, domain_config, rank_field_id)
        parsed_rank = parse_number(rank_value)
        if parsed_rank is None:
            return None
        ranking_key = int(parsed_rank - user_rank) if user_rank else None
        safety_margin_pct = (
            round((parsed_rank - user_rank) / user_rank, 4)
            if user_rank
            else None
        )
        if ranking.get("ranking_key"):
            output[str(ranking["ranking_key"])] = ranking_key
        if ranking.get("safety_margin_pct"):
            output[str(ranking["safety_margin_pct"])] = safety_margin_pct

    output.update(domain_config.execution.get("static_output_fields") or {})
    return output


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


def _normalize_subject(value: Any, domain_config: DomainConfig) -> str:
    text = cell_text(value)
    for source, target in (domain_config.subject_policy.get("normalization") or {}).items():
        text = text.replace(source, target)
    for subject in domain_config.subject_policy.get("subjects") or []:
        if subject in text:
            return subject
    return text


def _placeholders(values: list[Any]) -> str:
    return ", ".join(["?"] * len(values))


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@dataclass(frozen=True)
class _NumericHelperField:
    name: str
    field_id: str
    expression: str


def _numeric_helper_fields(
    domain_config: DomainConfig,
    columns: set[str],
) -> list[_NumericHelperField]:
    helpers = []
    for spec in domain_config.execution.get("numeric_helper_fields") or []:
        field_id = spec["field_id"]
        source_column = domain_config.source_column(field_id)
        if source_column in columns:
            expression = _numeric_expression(source_column)
        elif spec.get("optional"):
            expression = "NULL"
        else:
            raise ValueError(
                f"DuckDBExecutor missing required output column: {source_column}"
            )
        helpers.append(
            _NumericHelperField(
                name=str(spec["name"]),
                field_id=str(field_id),
                expression=expression,
            )
        )
    return helpers


def _helper_name_for_field(
    helper_fields: list[_NumericHelperField],
    field_id: str,
) -> str | None:
    for helper in helper_fields:
        if helper.field_id == field_id:
            return helper.name
    return None


def _sort_policy(
    domain_config: DomainConfig,
    sort_policy_override: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return list(sort_policy_override or domain_config.execution.get("sort_policy") or [])


def _order_clause(
    domain_config: DomainConfig,
    columns: set[str],
    sort_policy_override: list[dict[str, Any]] | None = None,
) -> str:
    parts = []
    helper_names = {
        str(item["name"])
        for item in domain_config.execution.get("numeric_helper_fields") or []
    }
    for item in _sort_policy(domain_config, sort_policy_override):
        field_id = item.get("label_field_id")
        if field_id:
            source_column = domain_config.source_column(field_id)
            if item.get("optional") and source_column not in columns:
                continue
        helper = str(item["helper"])
        if helper not in helper_names:
            raise ValueError(f"DuckDBExecutor cannot sort by unknown helper: {helper}")
        direction = str(item.get("direction") or "ASC").upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"DuckDBExecutor cannot sort direction: {direction}")
        nulls = str(item.get("nulls") or "LAST").upper()
        if nulls not in {"FIRST", "LAST"}:
            raise ValueError(f"DuckDBExecutor cannot sort nulls: {nulls}")
        parts.append(f"  {_quote_identifier(helper)} {direction} NULLS {nulls}")
    if not parts:
        return ""
    return "ORDER BY\n" + ",\n".join(parts)


def _sort_key_labels(
    domain_config: DomainConfig,
    columns: set[str],
    sort_policy_override: list[dict[str, Any]] | None = None,
) -> list[str]:
    labels = []
    helper_names = {
        str(item["name"])
        for item in domain_config.execution.get("numeric_helper_fields") or []
    }
    for item in _sort_policy(domain_config, sort_policy_override):
        field_id = item.get("label_field_id")
        if field_id:
            source_column = domain_config.source_column(field_id)
            if item.get("optional") and source_column not in columns:
                continue
            label = source_column
        else:
            label = str(item.get("helper"))
        helper = str(item["helper"])
        if helper not in helper_names:
            raise ValueError(f"DuckDBExecutor cannot sort by unknown helper: {helper}")
        direction = str(item.get("direction") or "ASC").upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"DuckDBExecutor cannot sort direction: {direction}")
        nulls = str(item.get("nulls") or "LAST").upper()
        if nulls not in {"FIRST", "LAST"}:
            raise ValueError(f"DuckDBExecutor cannot sort nulls: {nulls}")
        labels.append(f"{label} {direction} NULLS {nulls}")
    return labels


def _project_value(value: Any, transform: Any) -> Any:
    if transform == "text":
        return cell_text(value)
    if transform == "clean":
        return clean_value(value)
    if transform == "number":
        return parse_number(value)
    if transform == "int":
        parsed = parse_number(value)
        return int(parsed) if parsed is not None else None
    return clean_value(value)


def _projected_field_value(
    output: dict[str, Any],
    domain_config: DomainConfig,
    field_id: str,
) -> Any:
    for spec in domain_config.execution.get("output_fields") or []:
        if spec.get("field_id") == field_id:
            return output.get(spec.get("output_key"))
    source_column = domain_config.source_column(field_id)
    return output.get(source_column)


def _sql_string(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"
