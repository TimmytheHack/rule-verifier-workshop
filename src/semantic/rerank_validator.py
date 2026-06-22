from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_REASON_CODES = {
    "major_keyword_match",
    "province_match",
    "rank_distance",
    "school_tier",
    "deterministic_rank_distance_order",
}


@dataclass(frozen=True)
class RerankValidationResult:
    ok: bool
    result_sections: dict[str, list[dict[str, Any]]]
    issues: list[dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fallback_used": self.fallback_used,
            "issues": self.issues,
            "raw_payload": self.raw_payload,
        }


class RerankValidator:
    """校验 LLM rerank 是否仍被候选集和证据字段约束。"""

    def validate(
        self,
        payload: dict[str, Any],
        *,
        candidates: list[dict[str, Any]],
        quotas: dict[str, int],
    ) -> RerankValidationResult:
        candidate_by_id = {
            str(candidate.get("row_id")): candidate
            for candidate in candidates
            if candidate.get("row_id")
        }
        issues: list[dict[str, Any]] = []
        selected: dict[str, list[dict[str, Any]]] = {
            bucket: [] for bucket in quotas
        }
        seen: set[str] = set()

        for item in _payload_items(payload):
            row_id = str(item.get("row_id") or "")
            bucket = str(item.get("bucket") or "")
            candidate = candidate_by_id.get(row_id)
            if not candidate:
                issues.append(
                    {
                        "code": "unknown_row_id",
                        "row_id": row_id,
                        "message": "LLM rerank 引用了候选集外 row_id。",
                    }
                )
                continue
            if row_id in seen:
                issues.append(
                    {
                        "code": "duplicate_row_id",
                        "row_id": row_id,
                        "message": "LLM rerank 重复引用了同一个 row_id。",
                    }
                )
                continue
            seen.add(row_id)
            if bucket != candidate.get("bucket"):
                issues.append(
                    {
                        "code": "bucket_mismatch",
                        "row_id": row_id,
                        "expected_bucket": candidate.get("bucket"),
                        "actual_bucket": bucket,
                    }
                )
                continue
            if len(selected[bucket]) >= quotas[bucket]:
                issues.append(
                    {
                        "code": "quota_exceeded",
                        "bucket": bucket,
                        "quota": quotas[bucket],
                    }
                )
                continue
            invalid_reasons = [
                code
                for code in item.get("reason_codes") or []
                if code not in ALLOWED_REASON_CODES
            ]
            if invalid_reasons:
                issues.append(
                    {
                        "code": "unsupported_reason_code",
                        "row_id": row_id,
                        "reason_codes": invalid_reasons,
                    }
                )
                continue
            missing_fields = [
                field
                for field in item.get("field_refs") or []
                if field not in candidate
            ]
            if missing_fields:
                issues.append(
                    {
                        "code": "missing_field_ref",
                        "row_id": row_id,
                        "field_refs": missing_fields,
                    }
                )
                continue
            selected[bucket].append(
                {
                    **candidate,
                    "rerank_reason_codes": list(item.get("reason_codes") or []),
                }
            )

        if issues:
            return RerankValidationResult(
                ok=False,
                result_sections=_fallback_sections(candidates, quotas),
                issues=issues,
                fallback_used=True,
                raw_payload=dict(payload),
            )
        return RerankValidationResult(
            ok=True,
            result_sections=selected,
            raw_payload=dict(payload),
        )


def _payload_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _fallback_sections(
    candidates: list[dict[str, Any]],
    quotas: dict[str, int],
) -> dict[str, list[dict[str, Any]]]:
    sections = {bucket: [] for bucket in quotas}
    for candidate in candidates:
        bucket = candidate.get("bucket")
        if bucket not in sections:
            continue
        if len(sections[bucket]) >= quotas[bucket]:
            continue
        sections[bucket].append(dict(candidate))
    return sections


__all__ = [
    "ALLOWED_REASON_CODES",
    "RerankValidationResult",
    "RerankValidator",
]
