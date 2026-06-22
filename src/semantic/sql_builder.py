from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.semantic.query_ast import VerifiedQueryPlan


@dataclass(frozen=True)
class BuiltSQL:
    sql: str
    params: list[Any]


class SemanticSQLBuilder:
    def build(self, plan: VerifiedQueryPlan) -> BuiltSQL:
        if not isinstance(plan, VerifiedQueryPlan):
            raise TypeError("plan must be a VerifiedQueryPlan.")

        params: list[Any] = []
        clauses = [
            self._build_select_clause(plan),
            f"FROM {_quote_identifier(plan.table_name)}",
        ]

        where_clause = self._build_where_clause(plan, params)
        if where_clause:
            clauses.append(where_clause)

        order_clause = self._build_order_clause(plan)
        if order_clause:
            clauses.append(order_clause)

        clauses.append("LIMIT ?")
        params.append(plan.limit)
        return BuiltSQL(sql=" ".join(clauses), params=params)

    def _build_select_clause(self, plan: VerifiedQueryPlan) -> str:
        if not plan.select_columns:
            return "SELECT *"

        select_items = [
            (
                f"{_quote_identifier(record['source_column'])} "
                f"AS {_quote_identifier(record['field_id'])}"
            )
            for record in plan.select_columns
        ]
        return f"SELECT {', '.join(select_items)}"

    def _build_where_clause(
        self, plan: VerifiedQueryPlan, params: list[Any]
    ) -> str | None:
        if not plan.filters:
            return None

        expressions = [
            self._build_filter_expression(record, params) for record in plan.filters
        ]
        return f"WHERE {' AND '.join(expressions)}"

    def _build_filter_expression(
        self, record: dict[str, Any], params: list[Any]
    ) -> str:
        column = _quote_identifier(record["source_column"])
        op = record["op"]
        value = record["value"]

        if op == "eq":
            params.append(value)
            return f"{column} = ?"
        if op == "contains":
            params.append(value)
            return f"STRPOS(CAST({column} AS VARCHAR), ?) > 0"
        if op == "contains_any":
            values = _require_non_empty_values(value, op)
            expressions = []
            for item in values:
                params.append(item)
                expressions.append(f"STRPOS(CAST({column} AS VARCHAR), ?) > 0")
            return "(" + " OR ".join(expressions) + ")"
        if op == "between":
            lower, upper = _require_pair(value, op)
            params.extend([lower, upper])
            return f"{column} BETWEEN ? AND ?"
        if op in {"<=", ">="}:
            params.append(value)
            return f"{column} {op} ?"
        if op in {"in", "not_in"}:
            values = _require_non_empty_values(value, op)
            placeholders = ", ".join("?" for _ in values)
            params.extend(values)
            sql_op = "IN" if op == "in" else "NOT IN"
            return f"{column} {sql_op} ({placeholders})"

        raise ValueError(f"Unsupported verified SQL op: {op}")

    def _build_order_clause(self, plan: VerifiedQueryPlan) -> str | None:
        if not plan.sort:
            return None

        sort_items = [
            (
                f"{_quote_identifier(record['source_column'])} "
                f"{record['direction'].upper()} NULLS LAST"
            )
            for record in plan.sort
        ]
        return f"ORDER BY {', '.join(sort_items)}"


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _require_pair(value: Any, op: str) -> tuple[Any, Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{op} filter value must contain exactly two values.")
    if len(value) != 2:
        raise ValueError(f"{op} filter value must contain exactly two values.")
    return value[0], value[1]


def _require_non_empty_values(value: Any, op: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{op} filter value must be a non-empty list.")
    values = list(value)
    if not values:
        raise ValueError(f"{op} filter value must be a non-empty list.")
    return values
