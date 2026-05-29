"""Optional DeepSeek extractor.

The DeepSeek path is deliberately narrow:
- extracts preferences and source spans only
- returns strict JSON
- does not verify schema
- does not promote candidate rules
- does not compile or execute filters
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class DeepSeekJSONResponse:
    payload: dict[str, Any]
    usage: dict[str, int]


class DeepSeekClient:
    """Small standard-library client for DeepSeek's OpenAI-compatible chat API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str = DEEPSEEK_API_URL,
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds

    def chat_json(self, system_prompt: str, user_prompt: str) -> DeepSeekJSONResponse:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API error {exc.code}: {error_body}") from exc

        api_payload = json.loads(raw)
        content = api_payload["choices"][0]["message"]["content"]
        usage = api_payload.get("usage", {})
        return DeepSeekJSONResponse(
            payload=json.loads(content),
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
            },
        )


class DeepSeekExtractor:
    """Uses DeepSeek only for preference extraction.

    The returned slots must still go through RuleClassifier and RuleVerifier.
    """

    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def extract(self, text: str) -> dict[str, Any]:
        response = self.client.chat_json(
            system_prompt=(
                "You extract user preferences for a rule-verification system. "
                "Return strict JSON only. Do not decide final executability. "
                "Do not promote candidate rules. Do not create final filters."
            ),
            user_prompt=(
                "Extract slots from this Chinese college application preference. "
                "Return exactly this JSON shape: "
                '{"input": string, "user_context": {"source_province": string|null, '
                '"subject_type": string|null, "user_rank": number|null}, '
                '"preferences": {"major_keyword": string|null, "preferred_cities": [string], '
                '"risk_preference_raw": string|null, "tuition_preference_raw": string|null, '
                '"major_expansion_raw": string|null, "cooperation_preference_raw": string|null}, '
                '"raw_phrases": [string], '
                '"source_spans": [{"path": string, "text": string, "start": number|null, "end": number|null}]}. '
                "For this task, exact major keyword is only the explicit keyword. "
                f"Input: {text}"
            ),
        )
        slots = normalize_slots(response.payload, text)
        slots["deepseek_usage"] = response.usage
        return slots


def normalize_slots(slots: dict[str, Any], original_text: str) -> dict[str, Any]:
    """Normalize LLM-extracted values into the schema vocabulary.

    The LLM is allowed to extract text, but the symbolic pipeline expects stable
    values such as `物理` rather than `物理类`.
    """

    output = dict(slots)
    user_context = dict(output.get("user_context") or {})
    preferences = dict(output.get("preferences") or {})

    source_province = user_context.get("source_province")
    if source_province and "广东" in str(source_province):
        user_context["source_province"] = "广东"

    subject_type = user_context.get("subject_type")
    if subject_type and "物理" in str(subject_type):
        user_context["subject_type"] = "物理"
    elif subject_type and "历史" in str(subject_type):
        user_context["subject_type"] = "历史"

    user_rank = user_context.get("user_rank")
    if isinstance(user_rank, str):
        digits = "".join(char for char in user_rank if char.isdigit())
        user_context["user_rank"] = int(digits) if digits else None

    major_keyword = preferences.get("major_keyword")
    if major_keyword and "计算机" in str(major_keyword):
        preferences["major_keyword"] = "计算机"

    cities = preferences.get("preferred_cities") or []
    if isinstance(cities, str):
        cities_text = cities
        cities = [city for city in ["广州", "深圳"] if city in cities_text]
    else:
        city_texts = [str(city) for city in cities]
        cities = [city for city in ["广州", "深圳"] if any(city in text for text in city_texts)]
    if not cities:
        cities = [city for city in ["广州", "深圳"] if city in original_text]
    preferences["preferred_cities"] = cities

    risk = preferences.get("risk_preference_raw")
    if risk and "稳" in str(risk):
        preferences["risk_preference_raw"] = "稳一点"

    tuition = preferences.get("tuition_preference_raw")
    if tuition and "贵" in str(tuition):
        preferences["tuition_preference_raw"] = "太贵"

    cooperation = preferences.get("cooperation_preference_raw")
    if cooperation and "中外合作" in str(cooperation):
        preferences["cooperation_preference_raw"] = "不想去太贵的中外合作"

    output["input"] = output.get("input") or original_text
    output["user_context"] = user_context
    output["preferences"] = preferences
    output["raw_phrases"] = output.get("raw_phrases") or []
    return output
