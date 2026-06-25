"""查询前检查短期存储和确认项校验。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


class PreflightValidationError(ValueError):
    """preflight 引用不属于当前查询或确认项不是系统生成。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class StoredPreflight:
    preflight_id: str
    input_signature: str
    dataset_id: str
    domain_name: str
    boundary_confirmations: list[dict[str, Any]]
    created_at: float


class PreflightStore:
    """HTTP 层短期锁住查询前检查结果。"""

    def __init__(self, *, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, StoredPreflight] = {}

    def put(self, response: dict[str, Any]) -> None:
        preflight_id = str(response["preflight_id"])
        self._items[preflight_id] = StoredPreflight(
            preflight_id=preflight_id,
            input_signature=str(response["input_signature"]),
            dataset_id=str(response.get("dataset_id") or ""),
            domain_name=str(response.get("domain_name") or ""),
            boundary_confirmations=list(response.get("boundary_confirmations") or []),
            created_at=time.time(),
        )

    def get(self, preflight_id: str) -> StoredPreflight | None:
        item = self._items.get(preflight_id)
        if item is None:
            return None
        if time.time() - item.created_at > self.ttl_seconds:
            self._items.pop(preflight_id, None)
            return None
        return item

    def validate(
        self,
        *,
        preflight_id: str,
        input_signature: str,
        dataset_id: str,
        domain_name: str,
        confirmed: list[dict[str, Any]],
        disabled: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        item = self.get(preflight_id)
        if item is None:
            raise PreflightValidationError("查询前检查已过期或不存在。")
        if item.input_signature != input_signature:
            raise PreflightValidationError("查询输入已变化，请重新运行查询前检查。")
        if item.dataset_id != dataset_id or item.domain_name != domain_name:
            raise PreflightValidationError("查询前检查不属于当前数据源。")

        boundary_by_id = {
            str(boundary["confirmation_id"]): boundary
            for boundary in item.boundary_confirmations
        }
        selected = [*confirmed, *disabled]
        selected_ids = {
            str(entry.get("confirmation_id"))
            for entry in selected
            if entry.get("confirmation_id")
        }
        unknown = selected_ids - set(boundary_by_id)
        if unknown:
            raise PreflightValidationError("存在不是系统生成的确认项。")
        if set(boundary_by_id) - selected_ids:
            raise PreflightValidationError("请先处理所有需要确认的边界。")
        return [
            _selected_boundary_patch(
                boundary_by_id[str(entry["confirmation_id"])],
                entry,
            )
            for entry in confirmed
        ]

    def clear(self) -> None:
        self._items.clear()


def _selected_boundary_patch(
    boundary: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, Any]:
    option_id = selected.get("option_id") or "do_not_use"
    for option in boundary.get("options") or []:
        if option.get("option_id") == option_id:
            return dict(option.get("query_patch") or {})
    raise PreflightValidationError("确认项选择值不在系统选项中。")


__all__ = [
    "PreflightStore",
    "PreflightValidationError",
    "StoredPreflight",
]
