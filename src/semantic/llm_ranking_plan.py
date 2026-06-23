from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.intent_models import SemanticIntent
from src.semantic.ranking_plan import ALLOWED_RANKING_OPERATIONS, RankingPlan


class JSONChatClient(Protocol):
    def chat_json(self, *args: Any, **kwargs: Any) -> Any:
        """返回带 payload 和 usage 的 JSON 响应。"""


@dataclass(frozen=True)
class RankingPlanGenerationResult:
    plan: RankingPlan
    provider: str
    raw_payload: dict[str, Any]
    usage: dict[str, int]


class DeepSeekRankingPlanGenerator:
    """DeepSeek 只提出候选 RankingPlan，不执行排序。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def generate(
        self,
        *,
        user_input: str,
        intent: SemanticIntent,
        schema_context: list[dict[str, Any]],
        hard_context: dict[str, Any] | None = None,
    ) -> RankingPlanGenerationResult:
        response = _chat_json(
            self.client,
            _system_prompt(),
            _user_prompt(
                user_input=user_input,
                intent=intent,
                schema_context=schema_context,
                hard_context=hard_context or {},
            ),
        )
        payload, usage = _response_payload_and_usage(response)
        plan = RankingPlan.model_validate(payload)
        return RankingPlanGenerationResult(
            plan=plan,
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
        "你是招生推荐系统的候选 RankingPlan 生成器。"
        "你只能输出可验证 RankingPlan JSON，不能输出 SQL，不能执行排序，"
        "不能新增候选结果，不能引用字段摘要以外的数据。"
    )


def _user_prompt(
    *,
    user_input: str,
    intent: SemanticIntent,
    schema_context: list[dict[str, Any]],
    hard_context: dict[str, Any],
) -> str:
    allowed_operations = sorted(ALLOWED_RANKING_OPERATIONS)
    intent_json = json.dumps(intent.model_dump(), ensure_ascii=False)
    schema_json = json.dumps(schema_context, ensure_ascii=False)
    hard_json = json.dumps(hard_context, ensure_ascii=False)
    return (
        "请为当前 semantic_recommendation 生成 candidate RankingPlan。"
        "只能使用 reviewed 字段摘要里的 active 字段和 allowed_ops。"
        "优先选择可由表格字段直接证明的排序标准。"
        "如果用户给了排位，通常可以使用 major_min_rank 的 "
        "numeric_distance_to_user_value，value 等于用户排位。"
        "该 operation 的 score 越大表示越接近用户值，direction 通常填 desc。"
        "不要使用就业、城市发展、学校氛围、宿舍、办学国家等缺少字段的外部知识。"
        "如没有任何可验证排序标准，返回 {\"criteria\":[]}。"
        "允许 operation："
        f"{json.dumps(allowed_operations, ensure_ascii=False)}。"
        "JSON schema："
        "{"
        "\"criteria\":[{\"criterion_id\":string,\"source_text\":string,"
        "\"required_field\":string,\"operation\":string,\"value\":any,"
        "\"priority\":number,\"direction\":\"asc|desc\",\"rationale\":string}],"
        "\"rationale_summary\":string|null"
        "}。"
        f"字段摘要：{schema_json}。"
        f"硬信息：{hard_json}。"
        f"SemanticIntent：{intent_json}。"
        f"用户输入：{user_input}"
    )


__all__ = ["DeepSeekRankingPlanGenerator", "RankingPlanGenerationResult"]
