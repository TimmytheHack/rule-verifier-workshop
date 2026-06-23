from __future__ import annotations

import inspect
import json
import re
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.intent_models import IntentExtractionResult, SemanticIntent


RESELECTED_SUBJECTS = ["化学", "生物", "政治", "地理"]
SUBJECT_BUNDLES = {
    "物化生": ("物理", ["化学", "生物"]),
    "物化地": ("物理", ["化学", "地理"]),
    "物政地": ("物理", ["政治", "地理"]),
    "物生地": ("物理", ["生物", "地理"]),
    "史政地": ("历史", ["政治", "地理"]),
    "史化生": ("历史", ["化学", "生物"]),
}


class JSONChatClient(Protocol):
    def chat_json(self, *args: Any, **kwargs: Any) -> Any:
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
        system_prompt = _system_prompt()
        user_prompt = _user_prompt(
            text=text,
            schema_context=schema_context,
            hard_context=hard_context or {},
        )
        response = _chat_json(self.client, system_prompt, user_prompt)
        response_payload, usage = _response_payload_and_usage(response)
        payload = _normalize_payload(response_payload, original_text=text)
        return IntentExtractionResult(
            intent=SemanticIntent.model_validate(payload),
            provider="deepseek",
            raw_payload=payload,
            usage=usage,
        )


def _chat_json(client: JSONChatClient, system_prompt: str, user_prompt: str) -> Any:
    signature = inspect.signature(client.chat_json)
    if (
        "messages" in signature.parameters
        and "system_prompt" not in signature.parameters
    ):
        return client.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
    return client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)


def _response_payload_and_usage(response: Any) -> tuple[dict[str, Any], dict[str, int]]:
    if isinstance(response, dict):
        usage = dict(response.get("usage") or {})
        payload = {
            str(key): value
            for key, value in response.items()
            if key != "usage"
        }
        return payload, usage
    payload = dict(getattr(response, "payload", {}) or {})
    usage = dict(getattr(response, "usage", {}) or {})
    return payload, usage


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
        "如果用户要求“冲稳保”并列出“最低录取排名/最低录取位次/专业最低位次”，"
        "query_type=admissions_major_rank；抽取 user_rank、subject_type "
        "和 reselected_subjects，例如“广东物化生，10000名”表示 "
        "source_province=广东, subject_type=物理, user_rank=10000, "
        "reselected_subjects=[\"化学\",\"生物\"]。"
        "如果用户说想读人工智能、计算机，生成 semantic=major_name, "
        "op=contains_any。"
        "如果用户说留在广东省、省内、不出省，生成 semantic=school_province, "
        "op=in, value=[\"广东\"]。"
        "如果用户说不想去国外、不出国，生成 semantic=school_country_or_region, "
        "op=not_in, value=[\"国外\",\"境外\",\"海外\"]。"
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
    if user_context.get("user_rank") is None:
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
    else:
        subject_type = _parse_subject_type_text(original_text)
        if subject_type is not None:
            user_context["subject_type"] = subject_type
    if not user_context.get("reselected_subjects"):
        subjects = _parse_reselected_subjects_text(original_text)
        if subjects:
            user_context["reselected_subjects"] = subjects
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
    if not match and _allows_bare_rank_text(text):
        match = re.search(
            r"(\d{1,3}(?:[,，]\d{3})+|\d{3,}(?:\.\d+)?)\s*(万|w|W|名)",
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


def _allows_bare_rank_text(text: str) -> bool:
    return "冲稳保" in text or any(
        token in text
        for token in ["最低录取排名", "最低录取位次", "专业最低位次", "省排"]
    )


def _parse_subject_type_text(text: str) -> str | None:
    normalized = _normalize_subject_text(text)
    for bundle, (subject_type, _) in SUBJECT_BUNDLES.items():
        if bundle in normalized:
            return subject_type
    if "物理" in normalized or "物理类" in normalized or "首选物理" in normalized:
        return "物理"
    if "历史" in normalized or "历史类" in normalized or "首选历史" in normalized:
        return "历史"
    return None


def _parse_reselected_subjects_text(text: str) -> list[str]:
    normalized = _normalize_subject_text(text)
    selected: list[str] = []
    for bundle, (_, subjects) in SUBJECT_BUNDLES.items():
        if bundle in normalized:
            selected.extend(subjects)
    if not selected:
        selected.extend(
            subject for subject in RESELECTED_SUBJECTS if subject in normalized
        )
    output: list[str] = []
    for subject in selected:
        if subject not in output:
            output.append(subject)
    return output[:2]


def _normalize_subject_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text.replace("思想政治", "政治").replace("生物学", "生物")
