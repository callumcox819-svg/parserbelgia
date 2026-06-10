from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

ProgressFn = Callable[[dict[str, Any]], Awaitable[None]] | None

from .http_client import search_session
from .parser import _fetch_search_page
from .url_builder import api_url_from_params
from .filters import listing_is_auction, void_item_is_auction_price
from .void_format import listing_to_void_item

from .pagination import PAGE_SIZE, page_request_limit

# POST /lrp/api/search часто даёт 403; пагинация только через GET.

logger = logging.getLogger(__name__)


def _request_delay_sec() -> float:
    raw = os.environ.get("PARSE_REQUEST_DELAY", "0.8")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.8


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


def _sort_for_run(parse_count: int, cat_index: int) -> tuple[str, str]:
    variants = [
        ("SORT_INDEX", "DECREASING"),
        ("SORT_INDEX", "INCREASING"),
    ]
    return variants[(parse_count + cat_index) % len(variants)]


def _start_offset(parse_count: int, cat_index: int, skip_count: int) -> int:
    """С большой памятью объявлений не начинаем с offset=0 — там только «старые»."""
    if skip_count < 500:
        return 0
    depth = min(skip_count // 20, 4000)
    rot = (parse_count * 200 + cat_index * 350) % 2500
    off = depth + rot
    return (off // 30) * 30


class _ProxySessions:
    """Одна aiohttp-сессия на прокси; ротация при 403, в конце — direct."""

    def __init__(self, proxies: list[str | None]) -> None:
        base = list(proxies) if proxies else [None]
        if base != [None] and None not in base:
            base = base + [None]
        self.proxies = base or [None]
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
    skip_item_ids: set[str] | None = None,
    skip_auction_listings: bool = False,
    on_progress: ProgressFn = None,
    parse_count: int = 0,
    deadline: float | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_ids:
        raise ValueError("Нужна хотя бы одна категория")

    proxy_list: list[str | None] = list(proxies) if proxies else [proxy]
    if not proxy_list:
        proxy_list = [None]

    skip = set(skip_item_ids) if skip_item_ids else set()
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    skipped_auctions = 0
    skipped_items = 0
    pages_fetched = 0
    listings_scanned = 0
    partial_reason: str | None = None
    had_403 = False
    had_400 = False
    timed_out = False

    def _past_deadline() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    async def _report() -> None:
        if not on_progress:
            return
        await on_progress(
            {
                "items": len(items),
                "pages_fetched": pages_fetched,
                "listings_scanned": listings_scanned,
                "skipped_auctions": skipped_auctions,
                "skipped_items": skipped_items,
            }
        )

    logger.info(
        "2dehands parse start cats=%s limit=%s proxies=%s seen=%s",
        len(category_ids),
        limit,
        len(proxy_list),
        len(skip),
    )
    pool = _ProxySessions(proxy_list)
    skip_at_start = len(skip)
    try:
        for cat_index, cat_id in enumerate(category_ids):
            if timed_out or len(items) >= limit:
                break
            if _past_deadline():
                timed_out = True
                logger.info(
                    "2dehands deadline cat=%s items=%s, stop",
                    cat_id,
                    len(items),
                )
                break

            sort_by, sort_order = _sort_for_run(parse_count, cat_index)
            base_params: dict[str, str | list[str]] = {
                "l1CategoryId": str(cat_id),
                "viewOptions": "list-view",
                "sortBy": sort_by,
                "sortOrder": sort_order,
                "attributesByKey[]": ["Language:all-languages"],
            }
            offset = _start_offset(parse_count, cat_index, skip_at_start)
            stale_pages = 0
            retried_from_zero = offset == 0
            retried_after_403 = False
            if offset > 0:
                logger.info(
                    "2dehands cat=%s start offset=%s sort=%s/%s seen=%s",
                    cat_id,
                    offset,
                    sort_by,
                    sort_order,
                    skip_at_start,
                )

            while len(items) < limit:
                if _past_deadline():
                    timed_out = True
                    logger.info(
                        "2dehands deadline mid-cat=%s items=%s, stop",
                        cat_id,
                        len(items),
                    )
                    break
                items_before_page = len(items)
                page_limit = page_request_limit(limit - len(items))
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
                    err = str(exc)
                    if "403" in err:
                        had_403 = True
                        if offset > 0 and not retried_after_403:
                            logger.info(
                                "2dehands 403 cat=%s offset=%s, retry from 0",
                                cat_id,
                                offset,
                            )
                            offset = 0
                            retried_after_403 = True
                            retried_from_zero = True
                            stale_pages = 0
                            await asyncio.sleep(2.0)
                            continue
                        logger.warning(
                            "2dehands 403 cat=%s offset=%s items=%s, next category",
                            cat_id,
                            offset,
                            len(items),
                        )
                        break
                    if "400" in err:
                        had_400 = True
                        logger.warning(
                            "2dehands 400 cat=%s offset=%s limit=%s items=%s, next category",
                            cat_id,
                            offset,
                            page_limit,
                            len(items),
                        )
                        break
                    raise

                listings = data.get("listings") or []
                pages_fetched += 1
                await _report()
                if not listings:
                    if offset > 0 and not retried_from_zero:
                        logger.info(
                            "2dehands cat=%s offset=%s empty, retry from 0",
                            cat_id,
                            offset,
                        )
                        offset = 0
                        retried_from_zero = True
                        stale_pages = 0
                        continue
                    break

                listings_scanned += len(listings)
                page_non_auction = 0
                page_item_skips = 0
                for listing in listings:
                    if skip_auction_listings and listing_is_auction(listing):
                        skipped_auctions += 1
                        continue

                    page_non_auction += 1
                    item_id = str(listing.get("itemId") or "")
                    if not item_id:
                        continue
                    if item_id in seen_items:
                        continue
                    if item_id in skip:
                        skipped_items += 1
                        page_item_skips += 1
                        continue

                    seen_items.add(item_id)
                    void_item = listing_to_void_item(listing)
                    if skip_auction_listings and void_item_is_auction_price(
                        str(void_item.get("item_price") or "")
                    ):
                        skipped_auctions += 1
                        seen_items.discard(item_id)
                        continue
                    items.append(void_item)
                    skip.add(item_id)

                    if len(items) >= limit:
                        break

                if len(items) >= limit:
                    break

                added = len(items) - items_before_page
                if added > 0:
                    stale_pages = 0
                elif page_non_auction == 0:
                    # Страница только Bieden — листаем дальше.
                    pass
                elif page_item_skips > 0:
                    # Память объявлений — листаем глубже, не уходим из категории.
                    pass
                else:
                    stale_pages += 1
                stale_limit = 40 if skip_at_start > limit * 5 else 12
                if stale_pages >= stale_limit:
                    logger.info(
                        "2dehands cat=%s no new items for %s pages at offset=%s, next category",
                        cat_id,
                        stale_pages,
                        offset,
                    )
                    break

                total = int(data.get("totalResultCount") or 0)
                offset += page_limit
                if offset >= total:
                    break

            if timed_out or len(items) >= limit:
                break
    finally:
        await pool.close()

    if timed_out and len(items) < limit:
        partial_reason = "timeout"
    elif had_403 and len(items) < limit:
        partial_reason = "403"
    elif had_400 and len(items) < limit:
        partial_reason = "400"

    stats: dict[str, Any] = {
        "skipped_auctions": skipped_auctions,
        "skipped_items": skipped_items,
        "skipped_sellers": skipped_items,
        "pages_fetched": pages_fetched,
        "listings_scanned": listings_scanned,
    }
    if len(items) < limit and items:
        stats["shortfall"] = True
    if partial_reason in ("403", "400", "timeout") and items:
        stats["partial"] = True
        stats["partial_reason"] = partial_reason
        if partial_reason == "timeout":
            stats["timed_out"] = True
            stats["note"] = (
                f"Собрано **{len(items)}** из **{limit}** — **лимит времени**. "
                "Отдан частичный JSON."
            )
        elif partial_reason == "403":
            stats["note"] = (
                f"Собрано **{len(items)}** из **{limit}**. CloudFront **403** — "
                "поставьте **Прокси → off**, подождите 2–3 мин и повторите."
            )
        else:
            stats["note"] = (
                f"Собрано **{len(items)}** из **{limit}**. API **400** на части "
                "категорий — попробуйте снова; если повторяется, отключите категорию в настройках."
            )
    elif len(items) < limit and skip_at_start > limit * 5 and items:
        stats["note"] = (
            f"Собрано **{len(items)}** из **{limit}**. "
            f"Память **{skip_at_start}** объявлений — бот листал глубже, но новых мало. "
            "**Фильтры → Сбросить память** если нужен полный лимит снова."
        )
    elif len(items) < limit and not items:
        stats["note"] = (
            "Пусто — сбросьте память объявлений (Фильтры) или отключите фильтр Bieden."
        )
    if not items and listings_scanned > 0:
        filtered = skipped_auctions + skipped_items
        if filtered >= int(listings_scanned * 0.85):
            stats["all_filtered"] = True
    if not items and had_403 and pages_fetched < 5:
        stats["blocked_403"] = True
    return {"items": items, "stats": stats}
