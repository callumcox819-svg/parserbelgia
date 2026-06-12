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
    """Всегда свежие объявления первыми."""
    del parse_count, cat_index
    return ("DATE", "DECREASING")


def _fresh_sweeps_max() -> int:
    raw = os.environ.get("PARSE_FRESH_SWEEPS", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _category_rounds_max() -> int:
    raw = os.environ.get("PARSE_CATEGORY_ROUNDS", "2")
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def _max_zero_add_pages(seen: int, limit: int) -> int:
    """Подряд страниц без новых объявлений — затем следующая категория."""
    if seen <= limit * 3:
        return 120
    if seen <= limit * 20:
        return 50
    if seen <= limit * 50:
        return 30
    return 20


def _max_offset_per_cat(seen: int, limit: int) -> int:
    """Не копать одну категорию на десятки тысяч offset при огромной памяти."""
    if seen <= limit * 5:
        return 100_000
    if seen <= limit * 20:
        return 1200
    if seen <= limit * 50:
        return 600
    return 450


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
        for pass_i in range(2):
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
                    logger.warning(
                        "2dehands page 403 proxy=%s pass=%s, try next",
                        proxy,
                        pass_i + 1,
                    )
                    await self.close()
                    self._index = (proxy_idx + 1) % n
            if pass_i == 0:
                await asyncio.sleep(4.0 + random.uniform(0, 2.0))
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

    skip = set(skip_seller_ids) if skip_seller_ids else set()
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    skipped_auctions = 0
    skipped_sellers = 0
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
                "skipped_sellers": skipped_sellers,
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
    fresh_rescans = 0
    sweeps_max = _fresh_sweeps_max()
    rounds_max = _category_rounds_max()
    zero_cap = _max_zero_add_pages(skip_at_start, limit)
    offset_cap = _max_offset_per_cat(skip_at_start, limit)
    logger.info(
        "2dehands paging round-robin zero_cap=%s offset_cap=%s",
        zero_cap,
        offset_cap,
    )

    def _reset_cat_paging() -> tuple[dict[int, int], dict[int, int], dict[int, bool], dict[int, bool]]:
        return (
            {c: 0 for c in category_ids},
            {c: 0 for c in category_ids},
            {c: False for c in category_ids},
            {c: False for c in category_ids},
        )

    try:
        for cat_round in range(rounds_max):
            if timed_out or len(items) >= limit:
                break
            if cat_round > 0:
                logger.info(
                    "2dehands category round %s/%s items=%s",
                    cat_round + 1,
                    rounds_max,
                    len(items),
                )

            offsets, zero_add, exhausted, retried_403 = _reset_cat_paging()
            for cat_index, cat_id in enumerate(category_ids):
                sort_by, sort_order = _sort_for_run(parse_count, cat_index)
                logger.info(
                    "2dehands cat=%s sort=%s/%s seen_sellers=%s",
                    cat_id,
                    sort_by,
                    sort_order,
                    skip_at_start,
                )

            for fresh_sweep in range(sweeps_max):
                if timed_out or len(items) >= limit:
                    break
                if fresh_sweep > 0:
                    fresh_rescans += 1
                    offsets, zero_add, exhausted, retried_403 = _reset_cat_paging()
                    logger.info(
                        "2dehands rescan fresh sweep=%s/%s items=%s",
                        fresh_sweep + 1,
                        sweeps_max,
                        len(items),
                    )
                    await asyncio.sleep(1.0)

                while len(items) < limit and not timed_out:
                    if _past_deadline():
                        timed_out = True
                        logger.info(
                            "2dehands deadline items=%s, stop",
                            len(items),
                        )
                        break

                    active = [c for c in category_ids if not exhausted[c]]
                    if not active:
                        break

                    fetched_any = False
                    for cat_index, cat_id in enumerate(category_ids):
                        if timed_out or len(items) >= limit:
                            break
                        if exhausted[cat_id]:
                            continue
                        if _past_deadline():
                            timed_out = True
                            break

                        sort_by, sort_order = _sort_for_run(parse_count, cat_index)
                        base_params: dict[str, str | list[str]] = {
                            "l1CategoryId": str(cat_id),
                            "viewOptions": "list-view",
                            "sortBy": sort_by,
                            "sortOrder": sort_order,
                            "attributesByKey[]": ["Language:all-languages"],
                        }
                        offset = offsets[cat_id]
                        items_before_page = len(items)
                        page_limit = page_request_limit(limit - len(items))
                        await _throttle()
                        api_url = api_url_from_params(
                            base_params, limit=page_limit, offset=offset
                        )
                        logger.info(
                            "2dehands fetch cat=%s offset=%s items=%s sweep=%s",
                            cat_id,
                            offset,
                            len(items),
                            fresh_sweep + 1,
                        )
                        try:
                            data = await pool.fetch(api_url)
                        except RuntimeError as exc:
                            err = str(exc)
                            if "403" in err:
                                had_403 = True
                                if offset > 0 and not retried_403[cat_id]:
                                    logger.info(
                                        "2dehands 403 cat=%s offset=%s, retry from 0",
                                        cat_id,
                                        offset,
                                    )
                                    offsets[cat_id] = 0
                                    retried_403[cat_id] = True
                                    zero_add[cat_id] = 0
                                    await asyncio.sleep(2.0)
                                    fetched_any = True
                                    continue
                                logger.warning(
                                    "2dehands 403 cat=%s offset=%s items=%s, skip cat",
                                    cat_id,
                                    offset,
                                    len(items),
                                )
                                exhausted[cat_id] = True
                                fetched_any = True
                                continue
                            if "400" in err:
                                had_400 = True
                                logger.warning(
                                    "2dehands 400 cat=%s offset=%s limit=%s items=%s, skip cat",
                                    cat_id,
                                    offset,
                                    page_limit,
                                    len(items),
                                )
                                exhausted[cat_id] = True
                                fetched_any = True
                                continue
                            raise

                        listings = data.get("listings") or []
                        pages_fetched += 1
                        fetched_any = True
                        await _report()
                        if not listings:
                            exhausted[cat_id] = True
                            continue

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

                        if len(items) >= limit:
                            break

                        added = len(items) - items_before_page
                        if added > 0:
                            zero_add[cat_id] = 0
                        else:
                            zero_add[cat_id] += 1

                        total = int(data.get("totalResultCount") or 0)
                        next_offset = offset + page_limit
                        if zero_add[cat_id] >= zero_cap:
                            logger.info(
                                "2dehands cat=%s dry pages=%s offset=%s, pause cat",
                                cat_id,
                                zero_add[cat_id],
                                offset,
                            )
                            exhausted[cat_id] = True
                        elif next_offset >= total:
                            logger.info(
                                "2dehands cat=%s end of catalog offset=%s total=%s",
                                cat_id,
                                next_offset,
                                total,
                            )
                            exhausted[cat_id] = True
                        elif next_offset >= offset_cap:
                            logger.info(
                                "2dehands cat=%s offset cap=%s seen=%s",
                                cat_id,
                                offset_cap,
                                skip_at_start,
                            )
                            exhausted[cat_id] = True
                        else:
                            offsets[cat_id] = next_offset

                    if not fetched_any:
                        break
    finally:
        await pool.close()

    if timed_out and len(items) < limit:
        partial_reason = "timeout"
    elif had_400 and len(items) < limit:
        partial_reason = "400"
    elif had_403 and len(items) < limit and (not items or pages_fetched < 12):
        partial_reason = "403"

    stats: dict[str, Any] = {
        "skipped_auctions": skipped_auctions,
        "skipped_sellers": skipped_sellers,
        "pages_fetched": pages_fetched,
        "listings_scanned": listings_scanned,
        "fresh_rescans": fresh_rescans,
    }
    if had_403:
        stats["had_403"] = True
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
    elif len(items) < limit and items:
        mem_note = (
            f"Собрано **{len(items)}** из **{limit}**."
        )
        if skip_at_start > limit * 5:
            mem_note += (
                f" Память **{skip_at_start}** продавцов — новых мало."
            )
            stats["memory_exhausted"] = skip_at_start > limit * 30
        if had_403:
            mem_note += (
                " Часть категорий оборвалась по **403** — не запускайте "
                "два парсинга сразу, подождите 2–3 мин."
            )
        stats["note"] = mem_note
        stats["partial"] = True
    elif len(items) < limit and not items:
        stats["note"] = (
            "Пусто — сбросьте память продавцов (Фильтры) или отключите фильтр Bieden."
        )
    if not items and listings_scanned > 0:
        filtered = skipped_auctions + skipped_sellers
        if filtered >= int(listings_scanned * 0.85):
            stats["all_filtered"] = True
    if not items and had_403 and pages_fetched < 5:
        stats["blocked_403"] = True
    return {"items": items, "stats": stats}
