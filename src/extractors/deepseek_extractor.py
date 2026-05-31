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
                '"preferences": {"major_keyword": string|null, "major_exact_terms": [string], '
                '"preferred_cities": [string], '
                '"risk_preference_raw": string|null, "tuition_preference_raw": string|null, '
                '"major_expansion_raw": string|null, "cooperation_preference_raw": string|null, '
                '"school_ownership_preference_raw": string|null}, '
                '"raw_phrases": [string], '
                '"source_spans": [{"path": string, "text": string, "start": number|null, "end": number|null}]}. '
                "For this task, exact major terms are explicit major names only. "
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
    known_cities = ["广州", "深圳", "佛山", "东莞", "珠海", "惠州", "汕头", "中山"]
    known_majors = [
        "计算机",
        "软件工程",
        "人工智能",
        "网络安全",
        "自动化",
        "新闻传播",
        "数据科学",
        "网络空间安全",
        "电子信息",
        "法学",
        "会计",
        "金融",
        "临床医学",
        "汉语言文学",
    ]

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

    major_texts: list[str] = [original_text]
    major_keyword = preferences.get("major_keyword")
    if major_keyword:
        major_texts.append(str(major_keyword))
    major_terms = preferences.get("major_exact_terms") or []
    if isinstance(major_terms, str):
        major_texts.append(major_terms)
    else:
        major_texts.extend(str(term) for term in major_terms)
    major_expansion = preferences.get("major_expansion_raw")
    if major_expansion:
        major_texts.append(str(major_expansion))
    normalized_major_terms = _terms_in_text_order(known_majors, major_texts)
    preferences["major_exact_terms"] = normalized_major_terms
    preferences["major_keyword"] = normalized_major_terms[0] if normalized_major_terms else None

    cities = preferences.get("preferred_cities") or []
    if isinstance(cities, str):
        cities_text = cities
        cities = [city for city in known_cities if city in cities_text]
    else:
        city_texts = [str(city) for city in cities]
        cities = [city for city in known_cities if any(city in text for text in city_texts)]
    if not cities:
        cities = [city for city in known_cities if city in original_text]
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
    elif cooperation and "公办" in str(cooperation):
        preferences["school_ownership_preference_raw"] = str(cooperation)
        preferences["cooperation_preference_raw"] = None

    ownership = preferences.get("school_ownership_preference_raw")
    if not ownership:
        for term in ["公办本科", "优先公办", "公办", "民办"]:
            if term in original_text:
                preferences["school_ownership_preference_raw"] = term
                break

    output["input"] = output.get("input") or original_text
    output["user_context"] = user_context
    output["preferences"] = preferences
    output["raw_phrases"] = output.get("raw_phrases") or []
    return output


def _terms_in_text_order(terms: list[str], texts: list[str]) -> list[str]:
    positions: dict[str, tuple[int, int]] = {}
    for term in terms:
        for text_index, text in enumerate(texts):
            char_index = text.find(term)
            if char_index >= 0:
                positions[term] = (text_index, char_index)
                break
    return sorted(positions, key=positions.get)
