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
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
RETRYABLE_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}


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
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key or env_value("DEEPSEEK_API_KEY")
        self.model = model or env_value("DEEPSEEK_MODEL") or DEFAULT_MODEL
        self.api_url = api_url
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _int_env("DEEPSEEK_TIMEOUT_SECONDS", default=60)
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else _int_env("DEEPSEEK_MAX_RETRIES", default=3)
        )
        self.retry_backoff_seconds = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else _float_env("DEEPSEEK_RETRY_BACKOFF_SECONDS", default=2.0)
        )

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
        raw = self._urlopen_with_retries(request)

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

    def _urlopen_with_retries(self, request: urllib.request.Request) -> str:
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                ) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if not self._should_retry_http(exc.code) or attempt >= self.max_retries:
                    error_body = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"DeepSeek API error {exc.code}: {error_body}") from exc
                self._sleep_before_retry(attempt)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "DeepSeek network error after "
                        f"{self.max_retries + 1} attempts: {exc.reason}"
                    ) from exc
                self._sleep_before_retry(attempt)
        raise RuntimeError("DeepSeek request failed without a captured exception.")

    def _should_retry_http(self, status_code: int) -> bool:
        return status_code in RETRYABLE_HTTP_STATUS_CODES

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * (2 ** attempt)
        if delay > 0:
            time.sleep(delay)


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
                '"tuition_cap_yuan": number|null, '
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
    tuition_cap = preferences.get("tuition_cap_yuan")
    if tuition_cap is None:
        tuition_cap = _tuition_cap_yuan(original_text)
    if tuition_cap is None and tuition:
        tuition_cap = _tuition_cap_yuan(str(tuition))
    preferences["tuition_cap_yuan"] = tuition_cap
    if tuition_cap is not None and tuition and "贵" not in str(tuition):
        preferences["tuition_preference_raw"] = None

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


def has_deepseek_api_key() -> bool:
    """Return whether DeepSeek credentials are available without exposing them."""

    return bool(env_value("DEEPSEEK_API_KEY"))


def env_value(name: str) -> str | None:
    """Read an env var from the shell first, then from a local `.env` file."""

    value = os.getenv(name)
    if value:
        return value
    for dotenv_path in _dotenv_paths():
        value = _read_dotenv_value(dotenv_path, name)
        if value:
            return value
    return None


def _int_env(name: str, default: int) -> int:
    value = env_value(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = env_value(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _dotenv_paths() -> list[Path]:
    project_root = Path(__file__).resolve().parents[2]
    candidates = [Path.cwd() / ".env", project_root / ".env"]
    unique_paths = []
    seen = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(resolved)
    return unique_paths


def _read_dotenv_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        if not separator or key.strip() != name:
            continue
        return _clean_dotenv_value(value)
    return None


def _clean_dotenv_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        return cleaned[1:-1]
    return cleaned.split(" #", 1)[0].strip()


def _terms_in_text_order(terms: list[str], texts: list[str]) -> list[str]:
    positions: dict[str, tuple[int, int]] = {}
    for term in terms:
        for text_index, text in enumerate(texts):
            char_index = text.find(term)
            if char_index >= 0:
                positions[term] = (text_index, char_index)
                break
    return sorted(positions, key=positions.get)


def _tuition_cap_yuan(text: str) -> int | None:
    import re

    ten_thousand_match = re.search(r"(?:学费|费用|预算)?\s*([一二两三四五六七八九十\d.]+)\s*万\s*以内", text)
    if ten_thousand_match:
        value = _parse_small_number(ten_thousand_match.group(1))
        return int(value * 10000) if value is not None else None

    yuan_match = re.search(r"(?:学费|费用|预算)\D{0,4}(\d{4,6})\s*(?:元)?\s*以内", text)
    if yuan_match:
        return int(yuan_match.group(1))
    return None


def _parse_small_number(value: str) -> float | None:
    import re

    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    mapping = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    return float(mapping[value]) if value in mapping else None
