"""本机产品设置，避免把密钥暴露给前端。"""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from typing import Any

from src.llm.openai_compatible import (
    list_provider_templates,
    provider_template,
    validate_provider_api_url,
)


DEFAULT_SETTINGS_PATH = Path("outputs/local_settings/llm.json")
DEFAULT_PROVIDER = "deepseek"
DEFAULT_TEMPLATE = provider_template(DEFAULT_PROVIDER)
SUPPORTED_PROVIDERS = {item["provider"] for item in list_provider_templates()}
DEFAULT_DEEPSEEK_API_URL = DEFAULT_TEMPLATE.api_url


def settings_path() -> Path:
    return Path(os.getenv("LOCAL_SETTINGS_PATH", str(DEFAULT_SETTINGS_PATH)))


def llm_status() -> dict[str, Any]:
    settings = _read_settings()
    template = _settings_template(settings)
    return {
        "enabled": bool(settings.get("enabled")),
        "provider": template.provider,
        "provider_options": list_provider_templates(),
        "model": settings.get("model") or template.default_model,
        "api_url": settings.get("api_url") or template.api_url,
        "api_key_configured": bool(settings.get("api_key")),
    }


def save_llm_settings(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        template = provider_template(str(payload.get("provider") or DEFAULT_PROVIDER))
    except ValueError as exc:
        raise ValueError("不支持的 LLM provider") from exc
    api_url = validate_provider_api_url(
        template.provider,
        str(payload.get("api_url") or template.api_url),
    )
    settings = {
        "enabled": bool(payload.get("enabled")),
        "provider": template.provider,
        "model": str(payload.get("model") or template.default_model),
        "api_url": api_url,
    }
    api_key = str(payload.get("api_key") or "").strip()
    path = settings_path()
    _reject_unsafe_write_path(path)
    existing = _read_settings()
    if api_key:
        settings["api_key"] = api_key
    elif existing.get("api_key"):
        settings["api_key"] = existing["api_key"]
    _write_settings_securely(
        path,
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
    )
    return llm_status()


def local_setting_value(name: str) -> str | None:
    settings = _read_settings()
    if name == "ENABLE_LLM" and "enabled" in settings:
        return "true" if bool(settings.get("enabled")) else "false"
    if not settings.get("enabled"):
        return None
    template = _settings_template(settings)
    if name == "LLM_PROVIDER":
        return template.provider
    if name == "LLM_API_KEY":
        return str(settings.get("api_key")) if settings.get("api_key") else None
    if name == "LLM_MODEL":
        return str(settings.get("model") or template.default_model)
    if name == "LLM_API_URL":
        return str(settings.get("api_url") or template.api_url)
    mapping = {
        template.api_key_env: "api_key",
        template.model_env: "model",
        template.api_url_env: "api_url",
        "ENABLE_LLM": "enabled",
    }
    key = mapping.get(name)
    if not key:
        return None
    value = settings.get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if value else None


def _settings_template(settings: dict[str, Any]) -> Any:
    try:
        return provider_template(str(settings.get("provider") or DEFAULT_PROVIDER))
    except ValueError:
        return DEFAULT_TEMPLATE


def _write_settings_securely(path: Path, content: str) -> None:
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "posix":
        path.write_text(content, encoding="utf-8")
        return

    if not parent_existed:
        os.chmod(path.parent, 0o700)
    existing_mode = _reject_unsafe_write_path(path)
    if existing_mode is not None:
        os.chmod(path, 0o600)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("本机 LLM 设置路径不安全") from exc
        raise
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    finally:
        os.chmod(path, 0o600)


def _reject_unsafe_write_path(path: Path) -> int | None:
    if os.name != "posix":
        return None
    try:
        existing_mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(existing_mode):
        raise ValueError("本机 LLM 设置路径不安全")
    return existing_mode


def _read_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
