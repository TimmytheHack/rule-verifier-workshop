"""本机产品设置，避免把密钥暴露给前端。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_SETTINGS_PATH = Path("outputs/local_settings/llm.json")
SUPPORTED_PROVIDERS = {"deepseek"}
DEFAULT_DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


def settings_path() -> Path:
    return Path(os.getenv("LOCAL_SETTINGS_PATH", str(DEFAULT_SETTINGS_PATH)))


def llm_status() -> dict[str, Any]:
    settings = _read_settings()
    provider = settings.get("provider") or "deepseek"
    return {
        "enabled": bool(settings.get("enabled")),
        "provider": provider,
        "model": settings.get("model") or "deepseek-chat",
        "api_url": settings.get("api_url") or DEFAULT_DEEPSEEK_API_URL,
        "api_key_configured": bool(settings.get("api_key")),
    }


def save_llm_settings(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "deepseek")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("不支持的 LLM provider")
    api_url = str(payload.get("api_url") or DEFAULT_DEEPSEEK_API_URL)
    if not _valid_deepseek_api_url(api_url):
        raise ValueError("不支持的 LLM api_url")
    settings = {
        "enabled": bool(payload.get("enabled")),
        "provider": provider,
        "model": str(payload.get("model") or "deepseek-chat"),
        "api_url": api_url,
    }
    api_key = str(payload.get("api_key") or "").strip()
    existing = _read_settings()
    if api_key:
        settings["api_key"] = api_key
    elif existing.get("api_key"):
        settings["api_key"] = existing["api_key"]
    _write_settings_securely(
        settings_path(),
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
    )
    return llm_status()


def local_setting_value(name: str) -> str | None:
    settings = _read_settings()
    if name == "ENABLE_LLM" and "enabled" in settings:
        return "true" if bool(settings.get("enabled")) else "false"
    if not settings.get("enabled"):
        return None
    mapping = {
        "DEEPSEEK_API_KEY": "api_key",
        "DEEPSEEK_MODEL": "model",
        "DEEPSEEK_API_URL": "api_url",
        "ENABLE_LLM": "enabled",
    }
    key = mapping.get(name)
    if not key:
        return None
    value = settings.get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if value else None


def _valid_deepseek_api_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == "api.deepseek.com"


def _write_settings_securely(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "posix":
        path.write_text(content, encoding="utf-8")
        return

    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    finally:
        os.chmod(path, 0o600)


def _read_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
