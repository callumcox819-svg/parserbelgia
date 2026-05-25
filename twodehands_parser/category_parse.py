from __future__ import annotations

import json
from typing import Any

from .http_client import API_HEADERS, search_session
from .parser import _fetch_search_page, _search_request_from_response
from .url_builder import API_SEARCH, api_url_from_params
from .void_format import listing_to_void_item


def _http_error(status: int, raw: str, proxy: str | None) -> RuntimeError:
    if status == 403:
        msg = (
            "HTTP 403 Forbidden — 2dehands отклонил запрос. "
            "Проверьте BE/EU прокси в настройках (формат http://user:pass@host:port)."
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
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_ids:
        raise ValueError("Нужна хотя бы одна категория")

    skip = set(skip_seller_ids) if skip_seller_ids else set()
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()

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
            search_request: dict[str, Any] | None = None
            use_post = False

            while len(items) < limit:
                page_limit = min(limit - len(items), 100)

                if use_post and search_request:
                    req_copy = json.loads(json.dumps(search_request))
                    req_copy.setdefault("pagination", {})
                    req_copy["pagination"]["limit"] = page_limit
                    req_copy["pagination"]["offset"] = offset
                    async with session.post(
                        API_SEARCH,
                        json=req_copy,
                        headers={
                            **API_HEADERS,
                            "Content-Type": "application/json",
                        },
                        **request_kwargs,
                    ) as resp:
                        raw = await resp.text()
                        if resp.status == 204 or not raw.strip():
                            break
                        if resp.status >= 400:
                            raise _http_error(resp.status, raw, proxy)
                        data = json.loads(raw)
                else:
                    api_url = api_url_from_params(
                        base_params, limit=page_limit, offset=offset
                    )
                    data = await _fetch_search_page(
                        session, api_url, request_kwargs=request_kwargs
                    )

                listings = data.get("listings") or []
                if not listings:
                    break

                if search_request is None:
                    search_request = _search_request_from_response(data)
                    if search_request:
                        use_post = True

                for listing in listings:
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

                total = int(data.get("totalResultCount") or 0)
                offset += page_limit
                if offset >= total:
                    break

    return {"items": items}
