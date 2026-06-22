from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.semantic.query_ast import (
    QueryAST,
    QueryVerificationIssue,
    VerifiedQueryPlan,
)
from src.semantic.reviewed_mapping import ReviewedMappingRegistry


@dataclass(frozen=True)
class SemanticQueryVerificationResult:
    ok: bool
    plan: VerifiedQueryPlan
    issues: list[QueryVerificationIssue]
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]


class SemanticQueryVerifier:
    def __init__(
        self,
        registry: ReviewedMappingRegistry,
        *,
        table_name: str,
    ) -> None:
        self._registry = registry
        self._table_name = table_name

    def verify(self, ast: QueryAST) -> SemanticQueryVerificationResult:
        issues: list[QueryVerificationIssue] = []
        answerable_intents: list[dict[str, Any]] = []
        unanswerable_intents: list[dict[str, Any]] = []
        select_columns: list[dict[str, str]] = []
        filters: list[dict[str, Any]] = []
        sort: list[dict[str, str]] = []

        for field_id in ast.select:
            source_column = self._source_column_or_issue(
                field_id,
                issues,
                unanswerable_intents,
            )
            if not source_column:
                continue
            select_columns.append(
                {
                    "field_id": field_id,
                    "source_column": source_column,
                }
            )
            answerable_intents.append(
                {
                    "field_id": field_id,
                    "reason": "field_available",
                    "capability": "select",
                }
            )

        for query_filter in ast.filters:
            source_column = self._source_column_or_issue(
                query_filter.field_id,
                issues,
                unanswerable_intents,
            )
            if not source_column:
                continue
            if not self._registry.has_op(query_filter.field_id, query_filter.op):
                self._add_unanswerable_op_issue(
                    query_filter.field_id,
                    query_filter.op,
                    "filter",
                    issues,
                    unanswerable_intents,
                )
                continue
            invalid_value_message = self._invalid_filter_value_message(
                query_filter.op,
                query_filter.value,
            )
            if invalid_value_message:
                issues.append(
                    QueryVerificationIssue(
                        code="invalid_value",
                        severity="error",
                        message=invalid_value_message,
                        field_id=query_filter.field_id,
                        details={"op": query_filter.op},
                    )
                )
                unanswerable_intents.append(
                    {
                        "field_id": query_filter.field_id,
                        "op": query_filter.op,
                        "reason": "invalid_value",
                        "message": invalid_value_message,
                    }
                )
                continue
            filters.append(
                {
                    "field_id": query_filter.field_id,
                    "source_column": source_column,
                    "op": query_filter.op,
                    "value": query_filter.value,
                }
            )
            answerable_intents.append(
                {
                    "field_id": query_filter.field_id,
                    "op": query_filter.op,
                    "reason": "verified_filter",
                    "capability": "filter",
                }
            )

        for query_sort in ast.sort:
            source_column = self._source_column_or_issue(
                query_sort.field_id,
                issues,
                unanswerable_intents,
            )
            if not source_column:
                continue
            if not self._registry.has_op(query_sort.field_id, "sort"):
                self._add_unanswerable_op_issue(
                    query_sort.field_id,
                    "sort",
                    "sort",
                    issues,
                    unanswerable_intents,
                )
                continue
            sort.append(
                {
                    "field_id": query_sort.field_id,
                    "source_column": source_column,
                    "direction": query_sort.direction,
                }
            )
            answerable_intents.append(
                {
                    "field_id": query_sort.field_id,
                    "op": "sort",
                    "reason": "verified_sort",
                    "capability": "sort",
                }
            )

        plan = VerifiedQueryPlan(
            intent=ast.intent,
            table_name=self._table_name,
            select_columns=select_columns,
            filters=filters,
            sort=sort,
            limit=ast.limit,
            answerable_intents=answerable_intents,
            unanswerable_intents=unanswerable_intents,
        )
        ok = not any(issue.severity == "error" for issue in issues)
        return SemanticQueryVerificationResult(
            ok=ok,
            plan=plan,
            issues=issues,
            answerable_intents=answerable_intents,
            unanswerable_intents=unanswerable_intents,
        )

    def _source_column_or_issue(
        self,
        field_id: str,
        issues: list[QueryVerificationIssue],
        unanswerable_intents: list[dict[str, Any]],
    ) -> str | None:
        source_column = self._registry.source_column_or_none(field_id)
        if source_column:
            return source_column
        message = (
            self._registry.unsupported_reason(field_id)
            or f"字段 {field_id} 不在已审查语义映射中，不能执行。"
        )
        issues.append(
            QueryVerificationIssue(
                code="missing_field",
                severity="error",
                message=message,
                field_id=field_id,
            )
        )
        unanswerable_intents.append(
            {
                "field_id": field_id,
                "reason": "missing_field",
                "message": message,
            }
        )
        return None

    def _add_unanswerable_op_issue(
        self,
        field_id: str,
        op: str,
        capability: str,
        issues: list[QueryVerificationIssue],
        unanswerable_intents: list[dict[str, Any]],
    ) -> None:
        message = f"字段 {field_id} 不支持操作 {op}。"
        issues.append(
            QueryVerificationIssue(
                code="unsupported_op",
                severity="error",
                message=message,
                field_id=field_id,
                details={"op": op, "capability": capability},
            )
        )
        unanswerable_intents.append(
            {
                "field_id": field_id,
                "op": op,
                "reason": "unsupported_op",
                "capability": capability,
                "message": message,
            }
        )

    @staticmethod
    def _invalid_filter_value_message(op: str, value: Any) -> str | None:
        if op == "between" and not (isinstance(value, list) and len(value) == 2):
            return "between 操作的 value 必须是长度为 2 的列表。"
        if op in {"in", "not_in", "contains_any"} and not isinstance(value, list):
            return f"{op} 操作的 value 必须是列表。"
        return None


__all__ = [
    "SemanticQueryVerificationResult",
    "SemanticQueryVerifier",
]
