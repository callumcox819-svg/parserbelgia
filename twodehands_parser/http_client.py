from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiohttp

from .url_builder import BASE

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept-Language": "nl-BE,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

API_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "nl-BE,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

DEFAULT_HEADERS = API_HEADERS

def create_connector(proxy: str | None) -> aiohttp.BaseConnector:
    if not proxy:
        return aiohttp.TCPConnector(ssl=True, limit=20)
    from aiohttp_socks import ProxyConnector

    return ProxyConnector.from_url(proxy, rdns=True)


def request_kwargs(proxy: str | None) -> dict[str, Any]:
    """Прокси задаётся через connector (HTTP и SOCKS5)."""
    return {}


async def warmup_session(session: aiohttp.ClientSession, proxy: str | None) -> None:
    kw = request_kwargs(proxy)
    async with session.get(
        f"{BASE}/",
        headers=BROWSER_HEADERS,
        allow_redirects=True,
        **kw,
    ) as resp:
        body = await resp.text()
        if resp.status >= 400:
            hint = body[:200].replace("\n", " ")
            raise RuntimeError(
                f"2dehands warmup HTTP {resp.status}: {hint or resp.reason}"
            )


@asynccontextmanager
async def search_session(
    proxy: str | None,
) -> AsyncIterator[tuple[aiohttp.ClientSession, dict[str, Any]]]:
    timeout = aiohttp.ClientTimeout(total=90)
    connector = create_connector(proxy)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        cookie_jar=jar,
    ) as session:
        await warmup_session(session, proxy)
        yield session, request_kwargs(proxy)
