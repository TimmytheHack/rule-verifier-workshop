"""OpenAI-compatible LLM provider 模板和客户端。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse


RETRYABLE_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LLMProviderTemplate:
    provider: str
    display_name: str
    api_url: str
    default_model: str
    api_key_env: str
    model_env: str
    api_url_env: str
    aliases: tuple[str, ...] = ()
    supports_json_response: bool = True


@dataclass(frozen=True)
class OpenAICompatibleJSONResponse:
    payload: dict[str, Any]
    usage: dict[str, int]


PROVIDER_TEMPLATES: tuple[LLMProviderTemplate, ...] = (
    LLMProviderTemplate(
        provider="deepseek",
        display_name="DeepSeek",
        api_url="https://api.deepseek.com/chat/completions",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        model_env="DEEPSEEK_MODEL",
        api_url_env="DEEPSEEK_API_URL",
    ),
    LLMProviderTemplate(
        provider="qwen",
        display_name="通义千问 / DashScope",
        api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        default_model="qwen-plus",
        api_key_env="DASHSCOPE_API_KEY",
        model_env="DASHSCOPE_MODEL",
        api_url_env="DASHSCOPE_API_URL",
        aliases=("dashscope", "aliyun", "tongyi"),
    ),
    LLMProviderTemplate(
        provider="kimi",
        display_name="Kimi / Moonshot",
        api_url="https://api.moonshot.cn/v1/chat/completions",
        default_model="moonshot-v1-8k",
        api_key_env="MOONSHOT_API_KEY",
        model_env="MOONSHOT_MODEL",
        api_url_env="MOONSHOT_API_URL",
        aliases=("moonshot",),
    ),
    LLMProviderTemplate(
        provider="zhipu",
        display_name="智谱 GLM",
        api_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        default_model="glm-4-flash",
        api_key_env="ZHIPUAI_API_KEY",
        model_env="ZHIPUAI_MODEL",
        api_url_env="ZHIPUAI_API_URL",
        aliases=("glm", "bigmodel", "zhipuai"),
    ),
    LLMProviderTemplate(
        provider="qianfan",
        display_name="百度千帆",
        api_url="https://qianfan.baidubce.com/v2/chat/completions",
        default_model="ernie-4.0-turbo-8k",
        api_key_env="QIANFAN_API_KEY",
        model_env="QIANFAN_MODEL",
        api_url_env="QIANFAN_API_URL",
        aliases=("baidu", "ernie"),
    ),
    LLMProviderTemplate(
        provider="hunyuan",
        display_name="腾讯混元",
        api_url="https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
        default_model="hunyuan-lite",
        api_key_env="HUNYUAN_API_KEY",
        model_env="HUNYUAN_MODEL",
        api_url_env="HUNYUAN_API_URL",
        aliases=("tencent", "tencent-hunyuan"),
    ),
)


class OpenAICompatibleClient:
    """基于标准库的 OpenAI-compatible chat 客户端。"""

    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
        env_reader: Callable[[str], str | None] | None = None,
    ) -> None:
        self._env_reader = env_reader or _default_env_value
        explicit_provider = provider is not None
        template = provider_template(provider or self._env("LLM_PROVIDER") or "deepseek")
        self.provider = template.provider
        self.provider_template = template
        self.api_key = (
            api_key
            or (None if explicit_provider else self._env("LLM_API_KEY"))
            or self._env(template.api_key_env)
            or _legacy_deepseek_key(template, self._env_reader)
        )
        self.model = (
            model
            or (None if explicit_provider else self._env("LLM_MODEL"))
            or self._env(template.model_env)
            or template.default_model
        )
        configured_api_url = (
            api_url
            or (None if explicit_provider else self._env("LLM_API_URL"))
            or self._env(template.api_url_env)
            or template.api_url
        )
        self.api_url = validate_openai_compatible_api_url(configured_api_url)
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _int_env(self._env_reader, "LLM_TIMEOUT_SECONDS", default=None)
            or _int_env(self._env_reader, template.provider.upper() + "_TIMEOUT_SECONDS", default=None)
            or _int_env(self._env_reader, "DEEPSEEK_TIMEOUT_SECONDS", default=60)
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else _int_env(self._env_reader, "LLM_MAX_RETRIES", default=None)
            or _int_env(self._env_reader, template.provider.upper() + "_MAX_RETRIES", default=None)
            or _int_env(self._env_reader, "DEEPSEEK_MAX_RETRIES", default=3)
        )
        self.retry_backoff_seconds = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else _float_env(self._env_reader, "LLM_RETRY_BACKOFF_SECONDS", default=None)
            or _float_env(
                self._env_reader,
                template.provider.upper() + "_RETRY_BACKOFF_SECONDS",
                default=None,
            )
            or _float_env(self._env_reader, "DEEPSEEK_RETRY_BACKOFF_SECONDS", default=2.0)
        )

    def chat_json(self, system_prompt: str, user_prompt: str) -> OpenAICompatibleJSONResponse:
        if not self.api_key:
            raise RuntimeError(f"未配置 {self.provider_template.display_name} 密钥。")

        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        if self.provider_template.supports_json_response:
            body["response_format"] = {"type": "json_object"}
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
        return OpenAICompatibleJSONResponse(
            payload=json.loads(content),
            usage=llm_usage_from_payload(api_payload),
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
                    raise RuntimeError(
                        f"{self.provider_template.display_name} 接口错误 {exc.code}：{error_body}"
                    ) from exc
                self._sleep_before_retry(attempt)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"{self.provider_template.display_name} 网络请求失败，已重试 "
                        f"{self.max_retries + 1} 次：{exc.reason}"
                    ) from exc
                self._sleep_before_retry(attempt)
        raise RuntimeError(f"{self.provider_template.display_name} 请求失败，但没有捕获到具体异常。")

    def _should_retry_http(self, status_code: int) -> bool:
        return status_code in RETRYABLE_HTTP_STATUS_CODES

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * (2 ** attempt)
        if delay > 0:
            time.sleep(delay)

    def _env(self, name: str) -> str | None:
        return self._env_reader(name)


def provider_template(provider: str | None) -> LLMProviderTemplate:
    normalized = _normalize_provider(provider or "deepseek")
    for template in PROVIDER_TEMPLATES:
        aliases = {_normalize_provider(alias) for alias in template.aliases}
        if normalized == template.provider or normalized in aliases:
            return template
    raise ValueError(f"不支持的 LLM provider：{provider}")


def list_provider_templates() -> list[dict[str, str]]:
    return [
        {
            "provider": template.provider,
            "display_name": template.display_name,
            "api_url": template.api_url,
            "default_model": template.default_model,
        }
        for template in PROVIDER_TEMPLATES
    ]


def validate_provider_api_url(provider: str, api_url: str) -> str:
    template = provider_template(provider)
    parsed = urlparse(str(api_url or "").strip())
    expected = urlparse(template.api_url)
    if not _safe_https_url(parsed):
        raise ValueError("不支持的 LLM api_url")
    if parsed.hostname != expected.hostname:
        raise ValueError("LLM api_url 与 provider 不匹配")
    if parsed.path.rstrip("/") != expected.path.rstrip("/"):
        raise ValueError("LLM api_url path 与 provider 模板不匹配")
    return parsed.geturl()


def validate_openai_compatible_api_url(api_url: str) -> str:
    parsed = urlparse(str(api_url or "").strip())
    if not _safe_https_url(parsed):
        raise ValueError("不支持的 LLM api_url")
    if parsed.path.rstrip("/").split("/")[-2:] != ["chat", "completions"]:
        raise ValueError("LLM api_url path 必须指向 chat/completions")
    return parsed.geturl()


def configured_api_key_available(
    *,
    provider: str | None = None,
    env_reader: Callable[[str], str | None] | None = None,
) -> bool:
    reader = env_reader or _default_env_value
    try:
        template = provider_template(provider or reader("LLM_PROVIDER") or "deepseek")
    except ValueError:
        return False
    return bool(
        reader("LLM_API_KEY")
        or reader(template.api_key_env)
        or _legacy_deepseek_key(template, reader)
    )


def llm_usage_from_payload(api_payload: dict[str, Any]) -> dict[str, int]:
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


def _safe_https_url(parsed: Any) -> bool:
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.query == ""
        and parsed.fragment == ""
        and port in {None, 443}
    )


def _normalize_provider(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _legacy_deepseek_key(
    template: LLMProviderTemplate,
    env_reader: Callable[[str], str | None],
) -> str | None:
    if template.provider != "deepseek":
        return None
    return env_reader("DEEPSEEK_API_KEY")


def _default_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        from src.extractors.deepseek_extractor import env_value

        return env_value(name)
    except Exception:  # noqa: BLE001 - 运行早期避免 settings/dotenv 循环。
        return None


def _int_env(
    env_reader: Callable[[str], str | None],
    name: str,
    default: int | None,
) -> int | None:
    value = env_reader(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(
    env_reader: Callable[[str], str | None],
    name: str,
    default: float | None,
) -> float | None:
    value = env_reader(name)
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
