"""Optional DeepSeek extractor.

The DeepSeek path proposes structure only:
- extracts preferences and source spans
- sees a compact field summary, never raw workbook rows
- may propose rule-shaped objects for symbolic verification
- does not verify schema
- does not promote candidate rules
- does not compile or execute filters
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_ALIAS_PATH = DomainConfig.load("admissions").value_aliases_path
SUPPORTED_MODELS = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
}
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
        api_url: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key or env_value("DEEPSEEK_API_KEY")
        self.model = model or env_value("DEEPSEEK_MODEL") or DEFAULT_MODEL
        self.api_url = api_url or env_value("DEEPSEEK_API_URL") or DEEPSEEK_API_URL
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
            raise RuntimeError("未配置 DeepSeek 密钥（环境变量 DEEPSEEK_API_KEY）。")

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
        return DeepSeekJSONResponse(
            payload=json.loads(content),
            usage=deepseek_usage_from_payload(api_payload),
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
                    raise RuntimeError(f"DeepSeek 接口错误 {exc.code}：{error_body}") from exc
                self._sleep_before_retry(attempt)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "DeepSeek 网络请求失败，已重试 "
                        f"{self.max_retries + 1} 次：{exc.reason}"
                    ) from exc
                self._sleep_before_retry(attempt)
        raise RuntimeError("DeepSeek 请求失败，但没有捕获到具体异常。")

    def _should_retry_http(self, status_code: int) -> bool:
        return status_code in RETRYABLE_HTTP_STATUS_CODES

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * (2 ** attempt)
        if delay > 0:
            time.sleep(delay)


class DeepSeekExtractor:
    """Uses DeepSeek for schema-aware extraction and rule proposals.

    The returned slots must still go through RuleClassifier and RuleVerifier.
    """

    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def extract(
        self,
        text: str,
        schema_context: list[dict[str, Any]] | None = None,
        hard_context: dict[str, Any] | None = None,
        boundary_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema_context = schema_context or []
        hard_context = hard_context or {}
        boundary_context = boundary_context or {}
        response = self.client.chat_json(
            system_prompt=(
                "你是高考志愿偏好到规则验证系统的抽取器。"
                "只返回严格 JSON。你可以提出规则形状，但不能判断最终是否可执行；"
                "最终可执行性由后端符号验证器决定。"
                "不要声称任何规则已经执行，不要提升候选规则，不要生成最终筛选条件。"
                "所有解释性文本字段必须使用中文，例如 reason、question、source_text。"
            ),
            user_prompt=(
                "你会收到字段摘要、用户界面传入的结构化硬信息、可选的已确认边界，"
                "以及用户软偏好文本。字段摘要只包含字段元数据，不包含原始表格行。"
                "不要想象或补充原始 Excel 数据。提出规则时只能使用字段摘要中提供的 field_id。"
                "缺失字段、未激活字段或外部信息偏好必须保留为 unmapped_preferences "
                "或 explain-only 类型，不得包装成可执行规则。"
                "“留在广东省/省内/不出省”表示院校所在地偏好，不能写入生源地。"
                "“不想去国外/不出国”缺少专门字段时必须保留为不可执行偏好。"
                "所有自然语言解释必须写中文，不要输出英文说明。"
                "请严格返回以下 JSON 结构："
                '{"input": string, "user_context": {"source_province": string|null, '
                '"subject_type": string|null, "reselected_subjects": [string], "user_rank": number|null}, '
                '"preferences": {"major_keyword": string|null, "major_exact_terms": [string], '
                '"preferred_cities": [string], "preferred_school_provinces": [string], '
                '"risk_preference_raw": string|null, "tuition_preference_raw": string|null, '
                '"tuition_cap_yuan": number|null, '
                '"major_expansion_raw": string|null, "cooperation_preference_raw": string|null, '
                '"overseas_preference_raw": string|null, '
                '"school_ownership_preference_raw": string|null, '
                '"employment_preference_raw": string|null, '
                '"family_resource_raw": string|null, '
                '"career_goal_raw": string|null, '
                '"recommendation_request_raw": string|null, "other_vague_preferences": [string]}, '
                '"proposed_rules": [{"rule_id": string|null, "source_text": string|null, '
                '"category": "deterministic"|"candidate"|"explain_only", '
                '"field_id": string|null, "field": string|null, "operator": string|null, '
                '"value": any, "semantic_type": string|null, "value_source": string|null, '
                '"requires_human_confirmation": boolean, "reason": string|null}], '
                '"unmapped_preferences": [{"source_text": string, "field_id": string|null, '
                '"reason": string}], '
                '"questions_needed": [{"source_text": string, "question": string, '
                '"reason": string}], '
                '"raw_phrases": [string], '
                '"source_spans": [{"path": string, "text": string, "start": number|null, "end": number|null}]}. '
                "枚举值使用约定：明确事实使用 semantic_type=explicit_user_fact；"
                "界面已确认的安全边界或费用边界使用 confirmed_boundary；"
                "模糊偏好使用 vague_preference；专业语义扩展使用 semantic_expansion；"
                "需要外部资料的偏好使用 external_info；当前缺字段的结构化偏好使用 "
                "unsupported_structured_preference。"
                "专业词只有用户明确说出的专业名称或专业关键词才算精确词。"
                f"字段摘要：{json.dumps(schema_context, ensure_ascii=False)}。"
                f"结构化硬信息：{json.dumps(hard_context, ensure_ascii=False)}。"
                f"已确认边界：{json.dumps(boundary_context, ensure_ascii=False)}。"
                f"用户软偏好文本：{text}"
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
        "数学",
    ]

    source_province = user_context.get("source_province")
    if source_province and "广东" in str(source_province):
        user_context["source_province"] = "广东"

    subject_type = user_context.get("subject_type")
    if subject_type and "物理" in str(subject_type):
        user_context["subject_type"] = "物理"
    elif subject_type and "历史" in str(subject_type):
        user_context["subject_type"] = "历史"

    subjects_value = user_context.get("reselected_subjects") or []
    subject_texts = subjects_value if isinstance(subjects_value, list) else [subjects_value]
    subject_texts.append(original_text)
    reselected_subjects = []
    for subject in ["化学", "生物", "政治", "地理"]:
        if any(subject in str(text).replace("思想政治", "政治") for text in subject_texts):
            reselected_subjects.append(subject)
    user_context["reselected_subjects"] = reselected_subjects[:2]

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
    if not normalized_major_terms:
        normalized_major_terms = _explicit_major_terms_from_llm(
            preferences,
            original_text,
        )
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

    school_provinces = preferences.get("preferred_school_provinces") or []
    if isinstance(school_provinces, str):
        school_province_texts = [school_provinces]
    else:
        school_province_texts = [str(province) for province in school_provinces]
    if any("广东" in text for text in school_province_texts) or any(
        term in original_text
        for term in ["留在广东", "广东省内", "省内", "不出省", "不想出省", "留省内"]
    ):
        preferences["preferred_school_provinces"] = ["广东"]
    else:
        preferences["preferred_school_provinces"] = []

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

    overseas = preferences.get("overseas_preference_raw")
    if overseas and ("国外" in str(overseas) or "出国" in str(overseas)):
        preferences["overseas_preference_raw"] = str(overseas)
    elif any(
        term in original_text
        for term in ["不想去国外", "不要国外", "不去国外", "不出国", "不想出国", "想留在国内"]
    ):
        preferences["overseas_preference_raw"] = "不想去国外"
    else:
        preferences["overseas_preference_raw"] = None

    ownership = preferences.get("school_ownership_preference_raw")
    if not ownership:
        for term in ["公办本科", "优先公办", "公办", "民办"]:
            if term in original_text:
                preferences["school_ownership_preference_raw"] = term
                break

    employment = preferences.get("employment_preference_raw")
    if employment:
        preferences["employment_preference_raw"] = str(employment)
    elif any(term in original_text for term in ["就业前景好", "好就业", "好找工作", "就业更好", "将来好就业"]):
        preferences["employment_preference_raw"] = "好就业"
    else:
        preferences["employment_preference_raw"] = None

    family_resource = preferences.get("family_resource_raw")
    if family_resource:
        preferences["family_resource_raw"] = str(family_resource)
    else:
        aliases = _admissions_aliases()
        preferences["family_resource_raw"] = _first_present(
            original_text,
            aliases["no_family_resource_terms"],
        ) or _first_present(
            original_text,
            aliases["family_resource_terms"],
        )

    career_goal = preferences.get("career_goal_raw")
    if career_goal:
        preferences["career_goal_raw"] = str(career_goal)
    else:
        aliases = _admissions_aliases()
        preferences["career_goal_raw"] = _career_goal_raw(
            original_text,
            preferences.get("family_resource_raw"),
            aliases["career_goal_terms"],
        )

    recommendation = preferences.get("recommendation_request_raw")
    if recommendation:
        preferences["recommendation_request_raw"] = str(recommendation)
    elif any(term in original_text for term in ["给出推荐", "请推荐", "推荐一下", "推荐"]):
        preferences["recommendation_request_raw"] = "给出推荐"
    else:
        preferences["recommendation_request_raw"] = None

    output["input"] = output.get("input") or original_text
    output["user_context"] = user_context
    output["preferences"] = preferences
    output["proposed_rules"] = _normalize_proposed_rules(
        output.get("proposed_rules") or []
    )
    output["unmapped_preferences"] = _normalize_records(
        output.get("unmapped_preferences") or []
    )
    output["questions_needed"] = _normalize_records(
        output.get("questions_needed") or []
    )
    output["raw_phrases"] = output.get("raw_phrases") or []
    return output


def _normalize_proposed_rules(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        return []
    normalized = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            continue
        category = str(rule.get("category") or "deterministic")
        if category not in {"deterministic", "candidate", "explain_only"}:
            category = "candidate" if rule.get("requires_human_confirmation") else "deterministic"
        normalized.append(
            {
                "rule_id": rule.get("rule_id") or f"p_llm_{index:03d}",
                "source_text": _optional_text(rule.get("source_text")),
                "category": category,
                "field_id": _optional_text(rule.get("field_id")),
                "field": _optional_text(rule.get("field")),
                "operator": _optional_text(rule.get("operator")),
                "value": rule.get("value"),
                "semantic_type": _optional_text(rule.get("semantic_type")),
                "value_source": _optional_text(rule.get("value_source")),
                "requires_human_confirmation": bool(
                    rule.get("requires_human_confirmation", False)
                ),
                "reason": _optional_text(rule.get("reason")),
                "proposed_by": "llm_extractor",
            }
        )
    return normalized


def _normalize_records(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@lru_cache(maxsize=1)
def _admissions_aliases() -> dict[str, Any]:
    return json.loads(Path(DEFAULT_ALIAS_PATH).read_text(encoding="utf-8"))


def _first_present(text: str, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in text:
            return candidate
    return None


def _career_goal_raw(
    text: str,
    family_resource_raw: Any,
    career_goal_terms: list[str],
) -> str | None:
    search_text = text
    if family_resource_raw:
        search_text = search_text.replace(str(family_resource_raw), "", 1)

    matches = []
    intent_pattern = r"(?:想|希望|打算|考虑|计划|准备|目标(?:是)?|以后|将来)"
    for term in career_goal_terms:
        pattern = re.compile(
            rf"{intent_pattern}[^，。,.；;]{{0,8}}{re.escape(term)}"
        )
        match = pattern.search(search_text)
        if match:
            matches.append((match.start(), term))
    if not matches:
        return None
    return min(matches)[1]


def has_deepseek_api_key() -> bool:
    """Return whether DeepSeek credentials are available without exposing them."""

    return bool(env_value("DEEPSEEK_API_KEY"))


def deepseek_usage_from_payload(api_payload: dict[str, Any]) -> dict[str, int]:
    """Extract token usage fields returned by DeepSeek's chat API."""

    usage = api_payload.get("usage", {})
    keys = [
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "reasoning_tokens",
    ]
    normalized: dict[str, int] = {}
    for key in keys:
        normalized[key] = _int_value(usage.get(key, 0))

    completion_details = usage.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        normalized["reasoning_tokens"] = _int_value(
            completion_details.get(
                "reasoning_tokens",
                normalized.get("reasoning_tokens", 0),
            )
        )
    return normalized


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


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _explicit_major_terms_from_llm(
    preferences: dict[str, Any],
    original_text: str,
) -> list[str]:
    candidates: list[str] = []
    for value in [preferences.get("major_keyword")]:
        if value:
            candidates.append(str(value))
    raw_terms = preferences.get("major_exact_terms") or []
    if isinstance(raw_terms, str):
        candidates.append(raw_terms)
    elif isinstance(raw_terms, list):
        candidates.extend(str(term) for term in raw_terms)

    accepted: list[str] = []
    for candidate in candidates:
        term = candidate.strip()
        if not term or term in accepted:
            continue
        if term in original_text:
            accepted.append(term)
    return accepted


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
