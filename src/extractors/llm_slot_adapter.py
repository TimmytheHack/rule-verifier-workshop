"""可选 LLM slot adapter，生产路径只允许补槽和候选解释。"""

from __future__ import annotations

from typing import Any, Protocol

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - 依赖安装前的降级路径。
    Draft202012Validator = None  # type: ignore[assignment]

from src.extractors.deepseek_extractor import (
    DeepSeekClient,
    DeepSeekExtractor,
    env_value,
    has_deepseek_api_key,
)


FORBIDDEN_LLM_OUTPUT_KEYS = {
    "raw_sql",
    "sql",
    "executable_rules",
    "executable_rule",
    "hard_rules",
    "hard_rule",
    "approved_ops",
    "domain_pack_status",
}

SLOT_ADAPTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "input": {"type": "string"},
        "user_context": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source_province": {"type": ["string", "null"]},
                "subject_type": {"type": ["string", "null"]},
                "reselected_subjects": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "user_rank": {"type": ["number", "null"]},
            },
        },
        "preferences": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "major_keyword": {"type": ["string", "null"]},
                "major_exact_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "preferred_cities": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "preferred_school_provinces": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "risk_preference_raw": {"type": ["string", "null"]},
                "tuition_preference_raw": {"type": ["string", "null"]},
                "tuition_cap_yuan": {"type": ["number", "null"]},
                "major_expansion_raw": {"type": ["string", "null"]},
                "cooperation_preference_raw": {"type": ["string", "null"]},
                "overseas_preference_raw": {"type": ["string", "null"]},
                "school_ownership_preference_raw": {"type": ["string", "null"]},
                "recommendation_request_raw": {"type": ["string", "null"]},
                "other_vague_preferences": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "unmapped_preferences": {
            "type": "array",
            "items": {"type": "object"},
        },
        "questions_needed": {
            "type": "array",
            "items": {"type": "object"},
        },
        "raw_phrases": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source_spans": {
            "type": "array",
            "items": {"type": "object"},
        },
        "deepseek_usage": {"type": "object"},
        "fallback_extraction": {"type": "object"},
        "llm_slot_adapter": {"type": "object"},
        "proposed_rules": {
            "type": "array",
            "maxItems": 0,
        },
    },
    "required": ["input", "user_context", "preferences", "proposed_rules"],
}


class SlotExtractor(Protocol):
    """只负责抽取 slots 的底层 LLM extractor。"""

    def extract(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """返回 LLM 抽取结果。"""


class DeepSeekSlotAdapter:
    """DeepSeek 生产适配层：校验输出，只保留可补槽信息。"""

    def __init__(self, extractor: SlotExtractor | None = None) -> None:
        self.extractor = extractor or DeepSeekExtractor()

    @classmethod
    def from_client(cls, client: DeepSeekClient) -> "DeepSeekSlotAdapter":
        return cls(extractor=DeepSeekExtractor(client=client))

    def extract(
        self,
        text: str,
        schema_context: list[dict[str, Any]] | None = None,
        hard_context: dict[str, Any] | None = None,
        boundary_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw_slots = self.extractor.extract(
            text,
            schema_context=schema_context or [],
            hard_context=hard_context or {},
            boundary_context=boundary_context or {},
        )
        _reject_forbidden_keys(raw_slots)
        slots = _slot_only_payload(raw_slots)
        _validate_slot_payload(slots)
        slots["llm_slot_adapter"] = {
            "provider": "deepseek",
            "validated": True,
            "mode": "slot_completion_only",
            "safety_policy": (
                "LLM 输出不允许携带 SQL、hard rules 或 executable rules；"
                "Workbench 只合并 deterministic extractor 缺失的 slots。"
            ),
        }
        return slots


def llm_runtime_enabled() -> bool:
    """统一判断是否允许任何可选 LLM 调用。"""

    return _truthy(env_value("ENABLE_LLM"))


def deepseek_slot_adapter_enabled() -> bool:
    """DeepSeek slot adapter 只有显式开启且有 key 时才可用。"""

    return llm_runtime_enabled() and has_deepseek_api_key()


def _slot_only_payload(raw_slots: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "input": str(raw_slots.get("input") or ""),
        "user_context": _user_context(raw_slots.get("user_context")),
        "preferences": _preferences(raw_slots.get("preferences")),
        "unmapped_preferences": _records(raw_slots.get("unmapped_preferences")),
        "questions_needed": _records(raw_slots.get("questions_needed")),
        "raw_phrases": _strings(raw_slots.get("raw_phrases")),
        "source_spans": _records(raw_slots.get("source_spans")),
        "proposed_rules": [],
    }
    if isinstance(raw_slots.get("deepseek_usage"), dict):
        payload["deepseek_usage"] = dict(raw_slots["deepseek_usage"])
    return payload


def _validate_slot_payload(slots: dict[str, Any]) -> None:
    if Draft202012Validator is None:
        return
    validator = Draft202012Validator(SLOT_ADAPTER_SCHEMA)
    errors = sorted(validator.iter_errors(slots), key=lambda error: error.path)
    if errors:
        message = "; ".join(error.message for error in errors[:3])
        raise ValueError(f"LLM slot adapter 输出未通过 schema 校验：{message}")


def _reject_forbidden_keys(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_LLM_OUTPUT_KEYS:
                raise ValueError(f"LLM 输出包含禁止字段：{child_path}")
            _reject_forbidden_keys(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, f"{path}[{index}]")


def _user_context(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "source_province": _optional_text(source.get("source_province")),
        "subject_type": _optional_text(source.get("subject_type")),
        "reselected_subjects": _strings(source.get("reselected_subjects")),
        "user_rank": _optional_number(source.get("user_rank")),
    }


def _preferences(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "major_keyword": _optional_text(source.get("major_keyword")),
        "major_exact_terms": _strings(source.get("major_exact_terms")),
        "preferred_cities": _strings(source.get("preferred_cities")),
        "preferred_school_provinces": _strings(
            source.get("preferred_school_provinces")
        ),
        "risk_preference_raw": _optional_text(source.get("risk_preference_raw")),
        "tuition_preference_raw": _optional_text(
            source.get("tuition_preference_raw")
        ),
        "tuition_cap_yuan": _optional_number(source.get("tuition_cap_yuan")),
        "major_expansion_raw": _optional_text(source.get("major_expansion_raw")),
        "cooperation_preference_raw": _optional_text(
            source.get("cooperation_preference_raw")
        ),
        "overseas_preference_raw": _optional_text(
            source.get("overseas_preference_raw")
        ),
        "school_ownership_preference_raw": _optional_text(
            source.get("school_ownership_preference_raw")
        ),
        "recommendation_request_raw": _optional_text(
            source.get("recommendation_request_raw")
        ),
        "other_vague_preferences": _strings(
            source.get("other_vague_preferences")
        ),
    }


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value))
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
