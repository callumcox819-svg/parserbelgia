from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from bot_app.platforms import PLATFORM_2DEHANDS, PLATFORM_RICARDO, normalize_platform

_CR_COUNTRY = re.compile(r"_cr-([a-z]{2})\b", re.I)


def proxy_geo_hint(proxy: str) -> str | None:
    """Код страны из LomaProxy username (_cr-be, _cr-ch, …)."""
    match = _CR_COUNTRY.search(proxy)
    return match.group(1).lower() if match else None


def proxy_geo_warnings(proxies: list[str], platform: str) -> list[str]:
    platform = normalize_platform(platform)
    warnings: list[str] = []
    for proxy in proxies:
        cc = proxy_geo_hint(proxy)
        if not cc:
            continue
        if platform == PLATFORM_2DEHANDS and cc not in ("be", "nl", "fr", "de", "lu"):
            warnings.append(
                f"Прокси `_cr-{cc}` — для **2dehands** нужен **BE/EU** "
                f"(например `_cr-be`), не Швейцария."
            )
        elif platform == PLATFORM_RICARDO and cc != "ch":
            warnings.append(
                f"Прокси `_cr-{cc}` — для **Ricardo** нужен **CH** (`_cr-ch`)."
            )
    return warnings


def _proxy_log_label(proxy: str) -> str:
    try:
        from urllib.parse import urlparse

        p = urlparse(proxy)
        host = p.hostname or "?"
        user = (p.username or "")[:24]
        return f"{host} user={user}"
    except Exception:
        return "proxy"


async def verify_first_proxy(platform: str, proxy: str) -> None:
    """Быстрая проверка: прокси открывает главную площадки."""
    platform = normalize_platform(platform)
    logger.info("proxy verify start platform=%s %s", platform, _proxy_log_label(proxy))
    if platform == PLATFORM_RICARDO:
        from ricardo_parser.http_client import BROWSER_HEADERS, browse_session

        async with browse_session(proxy) as (session, request_kwargs):
            async with session.get(
                "https://www.ricardo.ch/de/",
                headers=BROWSER_HEADERS,
                allow_redirects=True,
                **request_kwargs,
            ) as resp:
                if resp.status >= 400:
                    body = (await resp.text())[:200]
                    raise RuntimeError(
                        f"Прокси не прошёл проверку Ricardo (HTTP {resp.status}). "
                        f"Нужен CH residential. {body[:80]}"
                    )
    else:
        from twodehands_parser.http_client import search_session, warmup_session

        async with search_session(proxy) as (session, request_kwargs):
            await warmup_session(session, proxy)
    logger.info("proxy verify ok platform=%s", platform)
