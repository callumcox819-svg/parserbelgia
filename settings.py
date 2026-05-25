"""Настройки: config.py и/или переменные окружения (Railway, Docker)."""

from __future__ import annotations

import os
import re
from types import ModuleType
from typing import Any
from urllib.parse import quote


def _from_config(name: str, config: ModuleType | None) -> Any:
    if config is None:
        return None
    return getattr(config, name, None)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_SCHEME_PREFIXES = (
    "http://",
    "https://",
    "socks5://",
    "socks5h://",
    "socks4://",
    "socks4a://",
)


def _quote_userinfo(value: str) -> str:
    return quote(value, safe="")


def _host_port_user_pass_to_url(p: str, *, scheme: str = "socks5") -> str | None:
    """LomaProxy и др.: host:port:username:password"""
    if "@" in p:
        return None
    parts = p.split(":")
    if len(parts) < 4:
        return None
    host = parts[0].strip()
    port = parts[1].strip()
    if not host or not port.isdigit():
        return None
    user = parts[2].strip()
    password = ":".join(parts[3:]).strip()
    if not user or not password:
        return None
    return (
        f"{scheme}://{_quote_userinfo(user)}:{_quote_userinfo(password)}"
        f"@{host}:{port}"
    )


def parse_proxy_list(proxy: str | None) -> list[str]:
    """Несколько прокси: по одному на строку или через запятую/точку с запятой."""
    if not proxy:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[\n\r;,]+", proxy):
        line = chunk.strip()
        if not line:
            continue
        normalized = normalize_proxy(line)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def normalize_proxy(proxy: str | None) -> str | None:
    if not proxy:
        return None
    p = proxy.strip().splitlines()[0].strip()
    if not p:
        return None
    lower = p.lower()
    if lower.startswith(_SCHEME_PREFIXES):
        return p
    if lower.startswith("socks5:"):
        return "socks5://" + p[7:].lstrip("/")
    if lower.startswith("socks4:"):
        return "socks4://" + p[7:].lstrip("/")

    loma = _host_port_user_pass_to_url(p, scheme="socks5")
    if loma:
        return loma

    if "@" in p and re.match(r"^[^:@\s]+:[^@\s]+@[^@\s]+:\d+$", p):
        user, rest = p.split("@", 1)
        return f"socks5://{user}@{rest}"

    if re.match(r"^[^:@\s]+:[^:@\s]+@[^@\s]+:\d+$", p):
        return f"socks5://{p}"

    return "http://" + p


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
    proxies_blob = _str_or_none(os.environ.get("PROXIES")) or _str_or_none(
        _from_config("PROXIES", config_mod)
    )
    proxy_list = parse_proxy_list(proxies_blob)
    single = normalize_proxy(proxy)
    if single and single not in proxy_list:
        proxy_list.insert(0, single)

    admin_ids = _str_or_none(os.environ.get("ADMIN_IDS")) or _str_or_none(
        os.environ.get("ADMIN_ID")
    ) or _str_or_none(_from_config("ADMIN_IDS", config_mod))

    return {
        "bot_token": bot_token,
        "default_limit": default_limit,
        "proxy": single,
        "proxies": proxy_list,
        "admin_ids": admin_ids,
    }
