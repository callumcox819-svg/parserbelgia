from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .html_parse import extract_listing_urls, max_page_from_html, parse_detail_html
from .http_client import browse_session, category_url, fetch_html
from .void_format import listing_to_void_item

logger = logging.getLogger(__name__)

ProgressFn = Callable[[dict[str, Any]], Awaitable[None]] | None


def _request_delay() -> float:
    raw = os.environ.get("LAENDLE_REQUEST_DELAY", "0.35")
    try:
        return max(0.05, float(raw))
    except ValueError:
        return 0.35


def _max_pages() -> int:
    raw = os.environ.get("LAENDLE_MAX_PAGES", "40")
    try:
        return max(1, int(raw))
    except ValueError:
        return 40


async def parse_laendle_categories(
    category_slugs: list[str],
    *,
    limit: int,
    proxy: str | None = None,
    proxies: list[str | None] | None = None,
    skip_seller_ids: set[int] | None = None,
    on_progress: ProgressFn = None,
    deadline: float | None = None,
    soft_deadline: float | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_slugs:
        raise ValueError("Нужна хотя бы одна категория")

    proxy_list: list[str | None] = list(proxies) if proxies else [proxy]
    if not proxy_list:
        proxy_list = [None]
    proxy_used = proxy_list[0]

    skip = set(skip_seller_ids) if skip_seller_ids else set()
    items: list[dict[str, Any]] = []
    seen_ads: set[str] = set()
    pages_fetched = 0
    listings_scanned = 0
    skipped_sellers = 0
    skipped_no_seller = 0
    timed_out = False
    cancelled = False
    soft_stopped = False
    delay = _request_delay()
    max_pages = _max_pages()

    def _past_deadline() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def _past_soft() -> bool:
        return (
            soft_deadline is not None
            and time.monotonic() >= soft_deadline
            and len(items) > 0
        )

    def _stop() -> bool:
        return should_stop is not None and should_stop()

    def _abort() -> bool:
        nonlocal timed_out, cancelled, soft_stopped
        if _stop():
            cancelled = True
            return True
        if _past_deadline():
            timed_out = True
            return True
        if _past_soft() and len(items) < limit:
            soft_stopped = True
            return True
        return False

    async def _report() -> None:
        if not on_progress:
            return
        await on_progress(
            {
                "items": len(items),
                "pages_fetched": pages_fetched,
                "listings_scanned": listings_scanned,
                "skipped_sellers": skipped_sellers,
                "skipped_no_seller": skipped_no_seller,
            }
        )

    async def _throttle() -> None:
        await asyncio.sleep(delay + random.uniform(0, 0.1))

    logger.info(
        "laendle parse start cats=%s limit=%s proxy=%s seen=%s",
        len(category_slugs),
        limit,
        bool(proxy_used),
        len(skip),
    )

    async with browse_session(proxy_used) as (session, req_kw):
        for slug in category_slugs:
            if len(items) >= limit or _abort():
                break

            page = 1
            site_max = max_pages
            empty_pages = 0
            while page <= site_max and len(items) < limit:
                if _abort():
                    break

                await _throttle()
                url = category_url(slug, page)
                logger.info(
                    "laendle cat=%s page=%s items=%s", slug, page, len(items)
                )
                try:
                    html = await fetch_html(session, url, request_kwargs=req_kw)
                except RuntimeError as exc:
                    err = str(exc)
                    if "403" in err or "429" in err or "500" in err:
                        logger.warning("laendle cat page error: %s", err[:160])
                        await asyncio.sleep(2.0)
                        break
                    raise

                pages_fetched += 1
                if page == 1:
                    site_max = min(max_pages, max_page_from_html(html) or max_pages)

                ad_urls = extract_listing_urls(html)
                if not ad_urls:
                    empty_pages += 1
                    if empty_pages >= 2:
                        break
                    page += 1
                    continue
                empty_pages = 0

                for ad_url in ad_urls:
                    if len(items) >= limit or _abort():
                        break
                    await _throttle()
                    try:
                        detail_html = await fetch_html(
                            session, ad_url, request_kwargs=req_kw
                        )
                    except RuntimeError as exc:
                        logger.warning("laendle detail skip: %s", str(exc)[:140])
                        continue

                    pages_fetched += 1
                    listings_scanned += 1
                    parsed = parse_detail_html(detail_html, ad_url)
                    if not parsed:
                        skipped_no_seller += 1
                        continue

                    ad_id = str(parsed.get("id") or ad_url)
                    if ad_id in seen_ads:
                        continue
                    seen_ads.add(ad_id)

                    seller_id = parsed.get("seller_id")
                    if seller_id and int(seller_id) in skip:
                        skipped_sellers += 1
                        continue

                    items.append(listing_to_void_item(parsed))
                    if seller_id:
                        skip.add(int(seller_id))
                    await _report()

                page += 1

    stats: dict[str, Any] = {
        "pages_fetched": pages_fetched,
        "listings_scanned": listings_scanned,
        "skipped_sellers": skipped_sellers,
        "skipped_no_seller": skipped_no_seller,
        "proxies": 1 if proxy_used else 0,
    }
    if cancelled:
        stats["cancelled"] = True
        stats["partial"] = True
        stats["note"] = (
            f"Собрано **{len(items)}** из **{limit}** — **остановлено (СТОП)**."
        )
    elif soft_stopped and len(items) < limit:
        stats["soft_stopped"] = True
        stats["partial"] = True
        stats["note"] = (
            f"Собрано **{len(items)}** из **{limit}** — **авто-стоп**. "
            "Отдан частичный JSON."
        )
    elif timed_out and len(items) < limit:
        stats["timed_out"] = True
        stats["partial"] = True
        stats["note"] = (
            f"Собрано **{len(items)}** из **{limit}** — **лимит времени**. "
            "Отдан частичный JSON."
        )
    elif len(items) < limit and items:
        stats["partial"] = True
        stats["note"] = (
            f"Собрано **{len(items)}** из **{limit}**. "
            "Категории закончились или продавцы уже в памяти."
        )
    return {"items": items, "stats": stats}
