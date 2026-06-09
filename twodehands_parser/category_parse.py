from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import Awaitable, Callable
from typing import Any

ProgressFn = Callable[[dict[str, Any]], Awaitable[None]] | None

from .http_client import search_session
from .parser import _fetch_search_page
from .url_builder import api_url_from_params
from .filters import listing_is_auction, void_item_is_auction_price
from .void_format import listing_to_void_item

# POST /lrp/api/search часто даёт 403; пагинация только через GET.
PAGE_SIZE = 100

logger = logging.getLogger(__name__)


def _request_delay_sec() -> float:
    raw = os.environ.get("PARSE_REQUEST_DELAY", "0.8")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.8


def _max_offset() -> int:
    raw = os.environ.get("TWODEHANDS_MAX_OFFSET", "2000")
    try:
        return max(PAGE_SIZE, int(raw))
    except ValueError:
        return 2000


async def _throttle() -> None:
    delay = _request_delay_sec()
    if delay > 0:
        await asyncio.sleep(delay + random.uniform(0, 0.3))


def _http_error(status: int, raw: str, proxy: str | None) -> RuntimeError:
    if status == 403:
        msg = (
            "HTTP 403 Forbidden — 2dehands отклонил запрос. "
            "Нужен рабочий BE/EU прокси (socks5://user:pass@host:port). "
            "Если прокси новый — подождите 1–2 мин и повторите."
        )
        if proxy:
            msg += " Сейчас используется ваш прокси."
        return RuntimeError(msg)
    return RuntimeError(f"HTTP {status}: {raw[:300]}")


class _ProxySessions:
    """Одна aiohttp-сессия на прокси; ротация только при 403."""

    def __init__(self, proxies: list[str | None]) -> None:
        self.proxies = proxies or [None]
        self._index = 0
        self._session = None
        self._request_kwargs: dict[str, Any] | None = None
        self._ctx = None

    async def _open(self, proxy: str | None) -> None:
        await self.close()
        self._ctx = search_session(proxy)
        self._session, self._request_kwargs = await self._ctx.__aenter__()

    async def close(self) -> None:
        if self._ctx is not None:
            await self._ctx.__aexit__(None, None, None)
        self._ctx = None
        self._session = None
        self._request_kwargs = None

    async def fetch(self, api_url: str) -> dict[str, Any]:
        last_exc: RuntimeError | None = None
        n = len(self.proxies)
        for i in range(n):
            proxy_idx = (self._index + i) % n
            proxy = self.proxies[proxy_idx]
            try:
                if self._session is None:
                    await self._open(proxy)
                return await _fetch_search_page(
                    self._session, api_url, request_kwargs=self._request_kwargs
                )
            except RuntimeError as exc:
                if "403" not in str(exc):
                    raise
                last_exc = exc
                logger.warning("2dehands page 403 proxy=%s, try next", proxy)
                await self.close()
                self._index = (proxy_idx + 1) % n
        if last_exc:
            raise _http_error(403, str(last_exc), self.proxies[0])
        raise RuntimeError("Нет прокси для запроса 2dehands.")


async def parse_l1_categories(
    category_ids: list[int],
    *,
    limit: int,
    proxy: str | None = None,
    proxies: list[str | None] | None = None,
    skip_seller_ids: set[int] | None = None,
    skip_auction_listings: bool = False,
    on_progress: ProgressFn = None,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_ids:
        raise ValueError("Нужна хотя бы одна категория")

    proxy_list: list[str | None] = list(proxies) if proxies else [proxy]
    if not proxy_list:
        proxy_list = [None]

    skip = set(skip_seller_ids) if skip_seller_ids else set()
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    skipped_auctions = 0
    skipped_sellers = 0
    pages_fetched = 0
    listings_scanned = 0
    stopped_early = False
    max_offset = _max_offset()

    async def _report() -> None:
        if not on_progress:
            return
        await on_progress(
            {
                "items": len(items),
                "pages_fetched": pages_fetched,
                "listings_scanned": listings_scanned,
                "skipped_auctions": skipped_auctions,
                "skipped_sellers": skipped_sellers,
            }
        )

    logger.info(
        "2dehands parse start cats=%s limit=%s proxies=%s seen_sellers=%s",
        len(category_ids),
        limit,
        len(proxy_list),
        len(skip),
    )
    pool = _ProxySessions(proxy_list)
    try:
        for cat_id in category_ids:
            if len(items) >= limit:
                break

            base_params: dict[str, str | list[str]] = {
                "l1CategoryId": str(cat_id),
                "viewOptions": "list-view",
                "sortBy": "SORT_INDEX",
                "sortOrder": "DECREASING",
                "attributesByKey[]": ["Language:all-languages"],
            }
            offset = 0

            while len(items) < limit:
                if offset >= max_offset:
                    logger.info(
                        "2dehands cat=%s offset=%s >= max %s, stop pagination",
                        cat_id,
                        offset,
                        max_offset,
                    )
                    stopped_early = True
                    break

                page_limit = min(limit - len(items), PAGE_SIZE)
                await _throttle()
                api_url = api_url_from_params(
                    base_params, limit=page_limit, offset=offset
                )
                logger.info(
                    "2dehands fetch cat=%s offset=%s items=%s",
                    cat_id,
                    offset,
                    len(items),
                )
                try:
                    data = await pool.fetch(api_url)
                except RuntimeError as exc:
                    if items:
                        logger.warning(
                            "2dehands 403 at offset=%s, return %s partial items",
                            offset,
                            len(items),
                        )
                        stopped_early = True
                        break
                    raise

                listings = data.get("listings") or []
                pages_fetched += 1
                await _report()
                if not listings:
                    break

                listings_scanned += len(listings)
                for listing in listings:
                    if skip_auction_listings and listing_is_auction(listing):
                        skipped_auctions += 1
                        continue

                    item_id = listing.get("itemId")
                    if item_id and item_id in seen_items:
                        continue

                    seller = listing.get("sellerInformation") or {}
                    seller_id = seller.get("sellerId")
                    if seller_id and int(seller_id) in skip:
                        skipped_sellers += 1
                        continue

                    if item_id:
                        seen_items.add(item_id)
                    void_item = listing_to_void_item(listing)
                    if skip_auction_listings and void_item_is_auction_price(
                        str(void_item.get("item_price") or "")
                    ):
                        skipped_auctions += 1
                        if item_id:
                            seen_items.discard(item_id)
                        continue
                    items.append(void_item)
                    if seller_id:
                        skip.add(int(seller_id))

                    if len(items) >= limit:
                        break

                if len(items) >= limit or stopped_early:
                    break

                total = int(data.get("totalResultCount") or 0)
                offset += page_limit
                if offset >= total:
                    break

            if stopped_early:
                break
    finally:
        await pool.close()

    stats: dict[str, Any] = {
        "skipped_auctions": skipped_auctions,
        "skipped_sellers": skipped_sellers,
        "pages_fetched": pages_fetched,
        "listings_scanned": listings_scanned,
    }
    if stopped_early:
        stats["partial"] = True
        stats["note"] = (
            "CloudFront 403 или лимит глубины — отданы не все объявления. "
            "Нужен BE-прокси или снизьте лимит / очистите seen sellers."
        )
    return {"items": items, "stats": stats}
