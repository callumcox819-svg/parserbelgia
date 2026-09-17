from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

BASE = "https://www.laendleanzeiger.at"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
}


def category_url(slug: str, page: int = 1) -> str:
    slug = slug.strip("/")
    base = f"{BASE}/anzeigen/{slug}/"
    if page <= 1:
        return base
    return f"{base}?pag={page}"


from contextlib import asynccontextmanager


@asynccontextmanager
async def browse_session(proxy: str | None = None):
    """Async context: yields (session, request_kwargs)."""
    timeout = aiohttp.ClientTimeout(total=45, connect=20)
    kwargs: dict[str, Any] = {}
    if proxy:
        kwargs["proxy"] = proxy
    session = aiohttp.ClientSession(timeout=timeout)
    try:
        yield session, kwargs
    finally:
        await session.close()


async def fetch_html(
    session: aiohttp.ClientSession,
    url: str,
    *,
    request_kwargs: dict[str, Any] | None = None,
) -> str:
    kw = request_kwargs or {}
    async with session.get(url, headers=BROWSER_HEADERS, **kw) as resp:
        body = await resp.text()
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} для {url}: {body[:200]}")
        return body
