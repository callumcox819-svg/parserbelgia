from __future__ import annotations

import asyncio
import os
import random
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiohttp

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


def request_delay_sec() -> float:
    raw = os.environ.get("RICARDO_REQUEST_DELAY", "2.5")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 2.5


async def throttle() -> None:
    base = request_delay_sec()
    await asyncio.sleep(base + random.uniform(0.2, 0.8))


async def warmup_session(session: aiohttp.ClientSession) -> None:
    async with session.get(f"{BASE}/{LANG}/", headers=BROWSER_HEADERS) as resp:
        body = await resp.text()
        if resp.status >= 400:
            hint = _response_hint(resp.status, body)
            raise RuntimeError(hint)


def _response_hint(status: int, body: str) -> str:
    low = body.lower()
    if status == 403 and ("cloudflare" in low or "forbidden" in low):
        return (
            "HTTP 403 — Ricardo/Cloudflare заблокировал запрос. "
            "Нужен residential прокси **Швейцарии (CH)**, BE-прокси не подходят."
        )
    return f"Ricardo warmup HTTP {status}: {body[:200].replace(chr(10), ' ')}"


def category_page_url(slug: str, page: int = 1) -> str:
    slug = slug.strip("/")
    url = f"{BASE}/{LANG}/c/{slug}/"
    if page > 1:
        url += f"?page={page}"
    return url


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
