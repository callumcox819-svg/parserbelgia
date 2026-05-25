from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
import aiohttp

from .http_client import create_connector, proxy_label, warmup_session

logger = logging.getLogger(__name__)


class RicardoProxyPool:
    """Пул SOCKS/HTTP-прокси: отдельная cookie-сессия на каждый, ротация при 403."""

    def __init__(self, proxies: list[str | None]) -> None:
        uniq: list[str | None] = []
        seen: set[str] = set()
        for p in proxies or [None]:
            key = p or ""
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        self.proxies = uniq or [None]
        self._sessions: dict[str, aiohttp.ClientSession] = {}
        self._connectors: dict[str, aiohttp.BaseConnector] = {}
        self._failed_warmup: set[str] = set()
        self._cooldown_until: dict[str, float] = {}
        self._rr_index = 0

    def _key(self, proxy: str | None) -> str:
        return proxy or ""

    def _is_available(self, proxy: str | None) -> bool:
        key = self._key(proxy)
        if key in self._failed_warmup:
            return False
        until = self._cooldown_until.get(key, 0.0)
        return time.monotonic() >= until

    def mark_blocked(self, proxy: str | None, *, seconds: float = 120.0) -> None:
        key = self._key(proxy)
        self._cooldown_until[key] = time.monotonic() + seconds
        logger.info(
            "ricardo proxy cooldown %s (%ds)",
            proxy_label(proxy),
            int(seconds),
        )

    def next_proxy(self) -> str | None:
        n = len(self.proxies)
        for _ in range(n):
            proxy = self.proxies[self._rr_index % n]
            self._rr_index += 1
            if self._is_available(proxy):
                return proxy
        return self.proxies[0]

    def proxies_for_retry(self, max_attempts: int | None = None) -> list[str | None]:
        available = [p for p in self.proxies if self._is_available(p)]
        if not available:
            available = list(self.proxies)
        if max_attempts is None:
            return available
        return available[: max(1, min(max_attempts, len(available)))]

    async def get_session(self, proxy: str | None) -> aiohttp.ClientSession:
        key = self._key(proxy)
        existing = self._sessions.get(key)
        if existing and not existing.closed:
            return existing

        connector = create_connector(proxy)
        self._connectors[key] = connector
        jar = aiohttp.CookieJar(unsafe=True)
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120),
            connector=connector,
            cookie_jar=jar,
        )
        try:
            await warmup_session(session)
        except Exception as exc:
            await session.close()
            self._failed_warmup.add(key)
            logger.warning(
                "ricardo proxy warmup failed %s: %s",
                proxy_label(proxy),
                exc,
            )
            raise
        self._sessions[key] = session
        return session

    async def close(self) -> None:
        for session in self._sessions.values():
            if not session.closed:
                await session.close()
        self._sessions.clear()
        for connector in self._connectors.values():
            await connector.close()
        self._connectors.clear()


@asynccontextmanager
async def proxy_pool(
    proxies: list[str | None],
) -> AsyncIterator[RicardoProxyPool]:
    pool = RicardoProxyPool(proxies)
    try:
        yield pool
    finally:
        await pool.close()
