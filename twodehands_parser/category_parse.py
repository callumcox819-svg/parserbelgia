from __future__ import annotations

import asyncio
import os
import random
from typing import Any

from .http_client import search_session
from .parser import _fetch_search_page
from .url_builder import api_url_from_params
from .filters import listing_is_auction
from .void_format import listing_to_void_item

# POST /lrp/api/search часто даёт 403; пагинация только через GET.
PAGE_SIZE = 100


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


async def parse_l1_categories(
    category_ids: list[int],
    *,
    limit: int,
    proxy: str | None = None,
    skip_seller_ids: set[int] | None = None,
    skip_auction_listings: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_ids:
        raise ValueError("Нужна хотя бы одна категория")

    skip = set(skip_seller_ids) if skip_seller_ids else set()
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    skipped_auctions = 0

    async with search_session(proxy) as (session, request_kwargs):
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
                page_limit = min(limit - len(items), PAGE_SIZE)
                await _throttle()
                api_url = api_url_from_params(
                    base_params, limit=page_limit, offset=offset
                )
                try:
                    data = await _fetch_search_page(
                        session, api_url, request_kwargs=request_kwargs
                    )
                except RuntimeError as exc:
                    if "403" not in str(exc):
                        raise
                    raise _http_error(403, str(exc), proxy) from exc

                listings = data.get("listings") or []
                if not listings:
                    break

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
                        continue

                    if item_id:
                        seen_items.add(item_id)
                    items.append(listing_to_void_item(listing))
                    if seller_id:
                        skip.add(int(seller_id))

                    if len(items) >= limit:
                        break

                if len(items) >= limit:
                    break

                total = int(data.get("totalResultCount") or 0)
                offset += page_limit
                if offset >= total:
                    break

    return {"items": items, "stats": {"skipped_auctions": skipped_auctions}}
