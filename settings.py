"""Настройки: config.py и/или переменные окружения (Railway, Docker)."""

from __future__ import annotations

import os
from types import ModuleType
from typing import Any


def _from_config(name: str, config: ModuleType | None) -> Any:
    if config is None:
        return None
    return getattr(config, name, None)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_proxy(proxy: str | None) -> str | None:
    if not proxy:
        return None
    if not proxy.startswith(("http://", "https://", "socks5://", "socks4://")):
        return "http://" + proxy
    return proxy


def load_settings() -> dict[str, Any]:
    config_mod: ModuleType | None = None
    try:
        import config as config_mod
    except ImportError:
        pass
    except Exception:
        # Broken config.py must not block env-based startup (Railway).
        config_mod = None

    bot_token = (
        _str_or_none(os.environ.get("BOT_TOKEN"))
        or _str_or_none(os.environ.get("TELEGRAM_BOT_TOKEN"))
        or _str_or_none(_from_config("BOT_TOKEN", config_mod))
    )

    limit_raw = os.environ.get("DEFAULT_LIMIT") or _from_config(
        "DEFAULT_LIMIT", config_mod
    )
    default_limit = 50
    if limit_raw is not None:
        try:
            default_limit = int(limit_raw)
        except (TypeError, ValueError):
            pass

    proxy = _str_or_none(os.environ.get("PROXY")) or _str_or_none(
        _from_config("PROXY", config_mod)
    )

    return {
        "bot_token": bot_token,
        "default_limit": default_limit,
        "proxy": normalize_proxy(proxy),
    }
