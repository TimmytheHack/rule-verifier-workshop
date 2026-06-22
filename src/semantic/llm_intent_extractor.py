from __future__ import annotations

import json
import re
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.intent_models import IntentExtractionResult, SemanticIntent


class JSONChatClient(Protocol):
    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """返回带 payload 和 usage 的 JSON 响应。"""


class DeepSeekSemanticIntentExtractor:
    """DeepSeek 只提出语义意图候选，不判断可执行性。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def extract(
        self,
        text: str,
        *,
        schema_context: list[dict[str, Any]],
        hard_context: dict[str, Any] | None = None,
    ) -> IntentExtractionResult:
        response = self.client.chat_json(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(
                text=text,
                schema_context=schema_context,
                hard_context=hard_context or {},
            ),
        )
        payload = _normalize_payload(response.payload, original_text=text)
        return IntentExtractionResult(
            intent=SemanticIntent.model_validate(payload),
            provider="deepseek",
            raw_payload=payload,
            usage=dict(getattr(response, "usage", {}) or {}),
        )


def _system_prompt() -> str:
    return (
        "你是招生数据系统的语义意图抽取器。"
        "你只能提出候选 SemanticIntent，不能生成 SQL，不能声称已执行，"
        "不能根据常识补表格数据。只返回 JSON object。"
    )


def _user_prompt(
    *,
    text: str,
    schema_context: list[dict[str, Any]],
    hard_context: dict[str, Any],
) -> str:
    schema_json = json.dumps(schema_context, ensure_ascii=False)
    hard_json = json.dumps(hard_context, ensure_ascii=False)
    return (
        "请把用户输入转换为 SemanticIntent JSON。"
        "字段摘要只包含 reviewed semantic field、source_column、allowed_ops "
        "和 unsupported_reason。"
        "如果用户说“排位是15000”“位次是15000”“省排15000”，"
        "user_context.user_rank=15000。"
        "如果用户只有分数没有位次，保留 user_score，user_rank=null。"
        "如果用户说想读人工智能、计算机，生成 semantic=major_name, "
        "op=contains_any。"
        "如果用户说留在广东省、省内、不出省，生成 semantic=school_province, "
        "op=in, value=[\"广东\"]。"
        "如果用户说不想去国外、不出国，生成 semantic=school_country_or_region, "
        "op=not_in。"
        "不要把 unsupported preference 改写成别的字段。"
        "JSON schema："
        "{"
        "\"query_type\":\"semantic_recommendation|admissions_major_rank|group_detail_report|unknown\","
        "\"user_context\":{\"user_rank\":number|null,\"user_score\":number|null,"
        "\"source_province\":string|null,\"subject_type\":string|null,"
        "\"reselected_subjects\":[string]},"
        "\"preferences\":[{\"source_text\":string,\"semantic\":string,"
        "\"op\":string,\"value\":any,\"reason\":string|null}],"
        "\"requested_output\":[string]"
        "}。"
        f"字段摘要：{schema_json}。"
        f"硬信息：{hard_json}。"
        f"用户输入：{text}"
    )


def _normalize_payload(payload: dict[str, Any], *, original_text: str) -> dict[str, Any]:
    user_context = dict(payload.get("user_context") or {})
    if _has_rank_text(original_text) and user_context.get("user_rank") is None:
        parsed = _parse_rank_text(original_text)
        if parsed is not None:
            user_context["user_rank"] = parsed
    if user_context.get("source_province") and "广东" in str(
        user_context["source_province"]
    ):
        user_context["source_province"] = "广东"
    if user_context.get("subject_type") and "物理" in str(
        user_context["subject_type"]
    ):
        user_context["subject_type"] = "物理"
    elif user_context.get("subject_type") and "历史" in str(
        user_context["subject_type"]
    ):
        user_context["subject_type"] = "历史"
    return {
        "query_type": payload.get("query_type") or "unknown",
        "user_context": user_context,
        "preferences": list(payload.get("preferences") or []),
        "requested_output": list(payload.get("requested_output") or []),
        "source_language": "zh-CN",
    }


def _has_rank_text(text: str) -> bool:
    return any(token in text for token in ["排位", "位次", "排名", "省排", "全省"])


def _parse_rank_text(text: str) -> int | None:
    match = re.search(
        r"(?:排位|位次|排名|省排|省排名|全省)\s*"
        r"(?:是|为|约|大概|大约|差不多)?\s*"
        r"(\d{1,3}(?:[,，]\d{3})+|\d+(?:\.\d+)?)\s*(万|w|W|名|左右)?",
        text,
    )
    if not match:
        return None
    number = match.group(1).replace(",", "").replace("，", "")
    value = float(number)
    unit = match.group(2)
    if unit in {"万", "w", "W"}:
        value *= 10000
    return int(value)
