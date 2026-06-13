"""Extractor orchestration with deterministic-first fallback behavior."""

from __future__ import annotations

from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekExtractor, has_deepseek_api_key
from src.extractors.regex_extractor import RegexExtractor


class SlotExtractor(Protocol):
    """只负责从文本中提出 slots，不判断可执行性。"""

    def extract(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Return extracted slot payload."""


class ExtractorFallbackPipeline:
    """Run deterministic extraction first, then optionally fill missing slots."""

    def __init__(
        self,
        deterministic_extractor: SlotExtractor | None = None,
        fallback_extractor: SlotExtractor | None = None,
        fallback_enabled: bool | None = None,
    ) -> None:
        self.deterministic_extractor = deterministic_extractor or RegexExtractor()
        self.fallback_extractor = fallback_extractor
        self.fallback_enabled = (
            has_deepseek_api_key() if fallback_enabled is None else fallback_enabled
        )

    def extract(
        self,
        text: str,
        schema_context: list[dict[str, Any]] | None = None,
        hard_context: dict[str, Any] | None = None,
        boundary_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        deterministic = self.deterministic_extractor.extract(text)
        missing_paths = missing_slot_paths(deterministic, text)
        if not self.fallback_enabled or not missing_paths:
            deterministic["fallback_extraction"] = {
                "used": False,
                "reason": (
                    "没有需要 LLM 补槽的明显缺口。"
                    if not missing_paths
                    else "未启用 LLM 补槽或缺少可用密钥。"
                ),
                "missing_paths": missing_paths,
            }
            return deterministic

        fallback = (self.fallback_extractor or DeepSeekExtractor()).extract(
            text,
            schema_context=schema_context or [],
            hard_context=hard_context or {},
            boundary_context=boundary_context or {},
        )
        merged = merge_slot_payloads(deterministic, fallback)
        merged["fallback_extraction"] = {
            "used": True,
            "reason": "deterministic extractor 存在明显缺槽，LLM 仅补充 slot。",
            "missing_paths": missing_paths,
            "filled_paths": _filled_paths(deterministic, merged, missing_paths),
        }
        if fallback.get("deepseek_usage"):
            merged["deepseek_usage"] = fallback["deepseek_usage"]
        return merged


def missing_slot_paths(slots: dict[str, Any], text: str) -> list[str]:
    """Detect likely false negatives that justify optional fallback extraction."""

    user_context = slots.get("user_context") or {}
    preferences = slots.get("preferences") or {}
    missing = []
    if not _present(user_context.get("user_rank")) and any(
        token in text for token in ["排位", "位次", "排名", "省排", "省排名", "全省"]
    ):
        missing.append("user_context.user_rank")
    if not _present(user_context.get("subject_type")) and any(
        token in text for token in ["物理", "历史", "物化", "史政", "物生", "史化"]
    ):
        missing.append("user_context.subject_type")
    if not _present(preferences.get("major_exact_terms")) and any(
        token in text for token in ["想学", "想读", "专业", "方向", "相关"]
    ):
        missing.append("preferences.major_exact_terms")
    if not _present(preferences.get("preferred_cities")) and any(
        token in text for token in ["城市", "周边", "附近", "珠三角", "广深"]
    ):
        missing.append("preferences.preferred_cities")
    return missing


def merge_slot_payloads(
    deterministic: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Merge fallback slots without letting LLM override deterministic values."""

    merged = dict(deterministic)
    merged["user_context"] = _merge_section(
        deterministic.get("user_context") or {},
        fallback.get("user_context") or {},
    )
    merged["preferences"] = _merge_section(
        deterministic.get("preferences") or {},
        fallback.get("preferences") or {},
    )
    merged["raw_phrases"] = _unique(
        list(deterministic.get("raw_phrases") or [])
        + list(fallback.get("raw_phrases") or [])
    )
    if fallback.get("source_spans"):
        merged["source_spans"] = fallback["source_spans"]
    merged["proposed_rules"] = []
    return merged


def _merge_section(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    output = dict(primary)
    for key, value in fallback.items():
        if isinstance(value, list):
            output[key] = _unique(list(output.get(key) or []) + value)
        elif not _present(output.get(key)) and _present(value):
            output[key] = value
    return output


def _filled_paths(
    before: dict[str, Any],
    after: dict[str, Any],
    missing_paths: list[str],
) -> list[str]:
    return [
        path
        for path in missing_paths
        if not _present(_value_at(before, path)) and _present(_value_at(after, path))
    ]


def _value_at(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for key in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


def _unique(values: list[Any]) -> list[Any]:
    output = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
