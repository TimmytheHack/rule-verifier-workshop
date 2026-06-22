from __future__ import annotations

import json
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.intent_models import SemanticIntent
from src.semantic.query_ast import _reject_raw_sql_key
from src.semantic.rerank_validator import ALLOWED_REASON_CODES


class JSONChatClient(Protocol):
    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """返回带 payload 和 usage 的 JSON 响应。"""


class EvidenceBoundedReranker:
    """LLM 只能在 bounded candidates 的 row_id 内排序。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def rerank(
        self,
        *,
        intent: SemanticIntent,
        candidates: list[dict[str, Any]],
        quotas: dict[str, int],
    ) -> dict[str, Any]:
        response = self.client.chat_json(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(
                intent=intent,
                candidates=candidates,
                quotas=quotas,
            ),
        )
        payload = getattr(response, "payload", response)
        if not isinstance(payload, dict):
            return {"items": []}
        return _reject_raw_sql_key(payload, "rerank payload")


def _system_prompt() -> str:
    return (
        "你是证据受限的招生推荐 reranker。"
        "只能使用用户意图和 bounded candidates 中已有字段；"
        "只能返回候选 row_id 的排序，不能生成 SQL，不能添加候选集外结果，"
        "不能使用未给出的外部知识。只返回 JSON object。"
    )


def _user_prompt(
    *,
    intent: SemanticIntent,
    candidates: list[dict[str, Any]],
    quotas: dict[str, int],
) -> str:
    payload = {
        "intent": intent.model_dump(),
        "quotas": quotas,
        "allowed_reason_codes": sorted(ALLOWED_REASON_CODES),
        "candidates": [
            _candidate_payload(candidate)
            for candidate in candidates
        ],
        "output_schema": {
            "items": [
                {
                    "row_id": "candidate row_id",
                    "bucket": "reach|match|safety",
                    "reason_codes": sorted(ALLOWED_REASON_CODES),
                    "field_refs": ["只引用 candidate 中存在的字段名"],
                }
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = [
        "row_id",
        "bucket",
        "档位",
        "院校名称",
        "专业组",
        "专业",
        "最低录取排名",
        "排序依据最低位次",
        "相对用户排名",
        "学校所在",
        "城市",
        "学费",
        "专业组最低位次",
        "是否985",
        "是否211",
        "录取人数",
    ]
    return {
        field: candidate.get(field)
        for field in allowed_fields
        if field in candidate
    }


__all__ = ["EvidenceBoundedReranker"]
