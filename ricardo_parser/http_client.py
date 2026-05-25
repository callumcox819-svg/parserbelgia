from __future__ import annotations

import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

BASE = "https://www.ricardo.ch"
LANG = "de"

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "de-CH,de;q=0.9,fr-CH;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
}


def create_connector(proxy: str | None) -> aiohttp.BaseConnector:
    if not proxy:
        return aiohttp.TCPConnector(ssl=True, limit=10)
    from aiohttp_socks import ProxyConnector

    return ProxyConnector.from_url(proxy, rdns=True)


def _delay_env(name: str, fallback: str) -> float:
    raw = os.environ.get(name) or os.environ.get("RICARDO_REQUEST_DELAY") or fallback
    try:
        return max(0.8, float(raw))
    except ValueError:
        return float(fallback)


def category_delay_sec() -> float:
    """Пауза между страницами категорий (как у void — только листание)."""
    return _delay_env("RICARDO_CATEGORY_DELAY", "1.5")


def enrich_delay_sec() -> float:
    """Пауза при открытии /de/a/{id}/ (медленно, Cloudflare)."""
    return _delay_env("RICARDO_ENRICH_DELAY", "2.5")


def blocked_cooldown_sec(*, enrich: bool = False) -> float:
    if not enrich:
        raw = os.environ.get("RICARDO_403_COOLDOWN_CATEGORY", "15")
    else:
        raw = os.environ.get("RICARDO_403_COOLDOWN", "90")
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 15.0 if not enrich else 90.0


def proxy_retry_max(*, enrich: bool = False) -> int:
    raw = os.environ.get(
        "RICARDO_PROXY_RETRY_MAX", "3" if not enrich else "10"
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


async def throttle(*, enrich: bool = False) -> None:
    base = enrich_delay_sec() if enrich else category_delay_sec()
    jitter = random.uniform(0.15, 0.6) if not enrich else random.uniform(0.3, 1.0)
    await asyncio.sleep(base + jitter)


async def throttle_after_block() -> None:
    base = blocked_cooldown_sec()
    await asyncio.sleep(base + random.uniform(0.0, 5.0))


def navigation_headers(
    referer: str | None = None,
    *,
    same_origin: bool = True,
) -> dict[str, str]:
    headers = dict(BROWSER_HEADERS)
    if referer:
        headers["Referer"] = referer
        if same_origin and "ricardo.ch" in referer:
            headers["sec-fetch-site"] = "same-origin"
    return headers


def is_blocked_response(status: int, body: str) -> bool:
    if status in (403, 429, 503):
        return True
    low = (body or "")[:8000].lower()
    return "cloudflare" in low or "cf-ray" in low or "attention required" in low


async def _proxy_exit_geo(session: aiohttp.ClientSession) -> dict[str, Any]:
    url = "http://ip-api.com/json/?fields=status,query,country,countryCode,isp,hosting"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status >= 400:
            return {}
        data = await resp.json(content_type=None)
        return data if isinstance(data, dict) else {}


async def _ensure_ch_proxy(session: aiohttp.ClientSession) -> dict[str, Any]:
    geo = await _proxy_exit_geo(session)
    if geo.get("status") != "success":
        return geo
    cc = (geo.get("countryCode") or "").upper()
    if cc and cc != "CH":
        country = geo.get("country") or cc
        ip = geo.get("query") or "?"
        hosting = geo.get("hosting")
        kind = " (datacenter/hosting)" if hosting else ""
        raise RuntimeError(
            "Прокси для Ricardo выходит не из Швейцарии.\n"
            f"Сайт видит IP **{ip}** → **{country} ({cc})**{kind}.\n"
            "Нужен **residential CH** (не BE/US/NL). "
            "У продавца часто пишут «CH», но реальный exit IP другой — проверьте в личном кабинете."
        )
    return geo


def _strict_geo() -> bool:
    return os.environ.get("RICARDO_STRICT_GEO", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _skip_homepage_warmup() -> bool:
    return os.environ.get("RICARDO_SKIP_WARMUP", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


async def warmup_session(session: aiohttp.ClientSession) -> None:
    try:
        await _ensure_ch_proxy(session)
    except RuntimeError as exc:
        if _strict_geo():
            raise
        logger.warning("ricardo geo (non-strict): %s", exc)

    if _skip_homepage_warmup():
        return

    headers = navigation_headers(f"{BASE}/{LANG}/", same_origin=False)
    async with session.get(f"{BASE}/{LANG}/", headers=headers) as resp:
        body = await resp.text()
        if is_blocked_response(resp.status, body):
            raise RuntimeError(_response_hint(resp.status, body))
        if resp.status >= 400:
            raise RuntimeError(_response_hint(resp.status, body))


def _response_hint(status: int, body: str) -> str:
    low = body.lower()
    if status == 403 and ("cloudflare" in low or "forbidden" in low or "cf-ray" in low):
        return (
            "HTTP 403 — Ricardo/Cloudflare заблокировал запрос. "
            "Нужен residential прокси с exit IP в **Швейцарии (CH)**. "
            "Проверьте страну exit-IP у провайдера (не BE/US/NL)."
        )
    if status == 429:
        return "HTTP 429 — слишком много запросов (Cloudflare rate limit)."
    return f"Ricardo warmup HTTP {status}: {body[:200].replace(chr(10), ' ')}"


def category_page_url(slug: str, page: int = 1) -> str:
    slug = slug.strip("/")
    url = f"{BASE}/{LANG}/c/{slug}/"
    if page > 1:
        url += f"?page={page}"
    return url


def article_page_url(article_id: str) -> str:
    return f"{BASE}/{LANG}/a/{article_id.strip()}/"


def proxy_label(proxy: str | None) -> str:
    """Короткая метка для логов (host + session, без пароля)."""
    if not proxy:
        return "direct"
    try:
        parsed = urlparse(proxy)
        host = parsed.hostname or "?"
        port = parsed.port
        base = f"{host}:{port}" if port else host
        user = parsed.username or ""
        if "session-" in user:
            sess = user.split("session-", 1)[-1].split("_")[0][:12]
            return f"{base}#{sess}"
        if user:
            return f"{base}#{user[:10]}"
        return base
    except Exception:
        return "proxy"


@asynccontextmanager
async def browse_session(
    proxy: str | None,
) -> AsyncIterator[tuple[aiohttp.ClientSession, dict[str, Any]]]:
    timeout = aiohttp.ClientTimeout(total=120)
    connector = create_connector(proxy)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        cookie_jar=jar,
    ) as session:
        await warmup_session(session)
        yield session, {}
