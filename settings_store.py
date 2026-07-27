"""Persistent user settings for API credentials and local tool paths."""
from __future__ import annotations

import base64
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)
_DPAPI_FAILURE_WARNED = False

# ---------------------------------------------------------------------------
# Windows DPAPI helpers — encrypts values to the current user account so
# API keys are not stored as plaintext in settings.json.
# ---------------------------------------------------------------------------

def _encrypt_value(value: str) -> str:
    if not value:
        return value
    if value.startswith(("dpapi:", "b64:", "b64_unprotected:")):
        return value
    try:
        import win32crypt
        data = win32crypt.CryptProtectData(
            value.encode("utf-8"), None, None, None, None, 0)
        return "dpapi:" + base64.b64encode(data).decode("utf-8")
    except Exception:
        logger.warning(
            "DPAPI encryption failed; storing API key with reversible base64 fallback",
            exc_info=True,
        )
        return "b64_unprotected:" + base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _decrypt_value(value: str) -> str:
    global _DPAPI_FAILURE_WARNED

    if not value:
        return value
    if value.startswith("dpapi:"):
        try:
            import win32crypt
            data = base64.b64decode(value[6:])
            return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1].decode("utf-8")
        except Exception:
            if not _DPAPI_FAILURE_WARNED:
                logger.warning(
                    "A DPAPI-protected setting could not be decrypted for the current "
                    "Windows user; affected API keys will be treated as unconfigured."
                )
                _DPAPI_FAILURE_WARNED = True
            return ""
    if value.startswith("b64_unprotected:"):
        try:
            return base64.b64decode(value[16:]).decode("utf-8")
        except Exception:
            return value
    try:
        import win32crypt
        data = base64.b64decode(value)
        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1].decode("utf-8")
    except Exception:
        pass
    # Fallback: try base64 obfuscation layer
    if value.startswith("b64:"):
        try:
            return base64.b64decode(value[4:]).decode("utf-8")
        except Exception:
            pass
    # Plaintext (backward compatibility with pre-encryption settings)
    return value


def _decrypt_settings(settings: dict[str, Any]) -> None:
    """Decrypt api_key values loaded from disk (mutates *settings* in place)."""
    for provider in settings.get("providers", {}).values():
        if isinstance(provider, dict) and provider.get("api_key"):
            provider["api_key"] = _decrypt_value(provider["api_key"])
    oracle = settings.get("oracle", {})
    if isinstance(oracle, dict) and oracle.get("api_key"):
        oracle["api_key"] = _decrypt_value(oracle["api_key"])
    audio = settings.get("audio", {})
    if isinstance(audio, dict) and audio.get("whisper_api_key"):
        audio["whisper_api_key"] = _decrypt_value(audio["whisper_api_key"])


def _encrypt_settings(settings: dict[str, Any]) -> None:
    """Encrypt api_key values before writing to disk (mutates *settings* in place)."""
    for provider in settings.get("providers", {}).values():
        if isinstance(provider, dict) and provider.get("api_key"):
            provider["api_key"] = _encrypt_value(provider["api_key"])
    oracle = settings.get("oracle", {})
    if isinstance(oracle, dict) and oracle.get("api_key"):
        oracle["api_key"] = _encrypt_value(oracle["api_key"])
    audio = settings.get("audio", {})
    if isinstance(audio, dict) and audio.get("whisper_api_key"):
        audio["whisper_api_key"] = _encrypt_value(audio["whisper_api_key"])


SETTINGS_FILE = Path(getattr(config, "SETTINGS_FILE", config.BASE_DIR / "settings.json"))


DEFAULT_SETTINGS: dict[str, Any] = {
    "providers": {
        "openai": {
            "api_key": config.OPENAI_API_KEY,
            "api_base": config.OPENAI_API_BASE,
            "model": "gpt-5.5",
        },
        "anthropic": {
            "api_key": config.ANTHROPIC_API_KEY,
            "model": "claude-3-5-sonnet-20241022",
        },
        "zhipu": {
            "api_key": config.ZHIPU_API_KEY,
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4.6v-flashx",
        },
        "qwen_vl": {
            "api_key": config.DASHSCOPE_API_KEY,
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3-vl-plus",
        },
        "volcengine": {
            "api_key": config.VOLCENGINE_API_KEY,
            "api_base": config.VOLCENGINE_API_BASE,
            "model": config.VOLCENGINE_MODEL,
        },
        "custom": {
            "api_key": config.CUSTOM_API_KEY,
            "api_base": config.CUSTOM_API_BASE,
            "model": config.CUSTOM_MODEL,
        },
        "vlm_coords": {
            "api_key": config.CUSTOM_API_KEY,
            "api_base": config.CUSTOM_API_BASE,
            "model": config.CUSTOM_MODEL or "gpt-4o",
        },
        "deepseek_vision": {
            "api_key": "",
            "api_base": "https://api.deepseek.com/v1",
            "model": "deepseek-vl2",
        },
        "autoglm_phone": {
            "api_key": config.ZHIPU_API_KEY,
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "model": "autoglm-phone",
        },
    },
    "adb": {
        "path": "adb",
        "last_device_id": "",
    },
    "panel_state": {},
    "oracle": {
        "enabled": False,
        "provider": "zhipu",
        "api_key": config.ZHIPU_API_KEY,
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.6v-flashx",
        "timeout": 120,
    },
    "audio": {
        "enabled": False,
        "sensevoice_model": "iic/SenseVoiceSmall",
        "duration_s": 3,
    },
    "ui": {
        "language": "zh-CN",
        "font_size": 10,
    },
    "forbidden_zones": {
        "selected": "",
        "presets": {},
    },
    "skills": {
        "forced": ["cida-type4.md"],
    },
}


def load_settings() -> dict[str, Any]:
    settings = deepcopy(DEFAULT_SETTINGS)
    if not SETTINGS_FILE.exists():
        return settings
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return settings
    if isinstance(data, dict):
        _merge(settings, data)
        _decrypt_settings(settings)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    to_save = deepcopy(settings)
    _encrypt_settings(to_save)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(to_save, handle, indent=2, ensure_ascii=False)


def get_provider_settings(provider: str) -> dict[str, Any]:
    settings = load_settings()
    providers = settings.get("providers", {})
    value = providers.get(provider, {})
    return value if isinstance(value, dict) else {}


def get_adb_settings() -> dict[str, Any]:
    settings = load_settings()
    value = settings.get("adb", {})
    return value if isinstance(value, dict) else {}


def get_oracle_settings() -> dict[str, Any]:
    settings = load_settings()
    value = settings.get("oracle", {})
    return value if isinstance(value, dict) else {}


def get_audio_settings() -> dict[str, Any]:
    settings = load_settings()
    value = settings.get("audio", {})
    return value if isinstance(value, dict) else {}


def get_ui_settings() -> dict[str, Any]:
    settings = load_settings()
    value = settings.get("ui", {})
    return value if isinstance(value, dict) else {}


def get_forbidden_zone_settings() -> dict[str, Any]:
    settings = load_settings()
    value = settings.get("forbidden_zones", {})
    return value if isinstance(value, dict) else {}


def get_skill_settings() -> dict[str, Any]:
    settings = load_settings()
    value = settings.get("skills", {})
    return value if isinstance(value, dict) else {}


def update_forced_skills(names: list[str]) -> None:
    settings = load_settings()
    skills = settings.setdefault("skills", {})
    skills["forced"] = sorted({name for name in names if name})
    save_settings(settings)


def update_ui_settings(**values: Any) -> None:
    settings = load_settings()
    ui = settings.setdefault("ui", {})
    ui.update(values)
    save_settings(settings)


def update_adb_device(device_id: str) -> None:
    settings = load_settings()
    settings.setdefault("adb", {})["last_device_id"] = device_id
    save_settings(settings)


def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
