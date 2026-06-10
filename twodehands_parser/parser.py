from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .url_builder import (
    BASE,
    api_url_from_params,
    build_api_params_from_browser_url,
    extract_l1_category_id,
    normalize_browser_url,
)
from .http_client import API_HEADERS, search_session
from .pagination import page_request_limit
from .void_format import listing_to_void_item

logger = logging.getLogger(__name__)


async def _fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    *,
    expect_json: bool = True,
    request_kwargs: dict[str, Any] | None = None,
) -> str:
    kw = request_kwargs or {}
    async with session.get(url, headers=API_HEADERS, **kw) as resp:
        body = await resp.text()
        if resp.status == 204:
            return ""
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} для {url}: {body[:300]}")
        if expect_json and body.strip() and not body.lstrip().startswith(("{", "[")):
            raise RuntimeError(f"Ожидался JSON, получен HTML ({resp.status}): {body[:200]}")
        return body


async def _resolve_category_id(
    session: aiohttp.ClientSession,
    params: dict[str, str | list[str]],
    *,
    request_kwargs: dict[str, Any] | None = None,
) -> dict[str, str | list[str]]:
    slug = params.pop("_category_slug", None)
    if not slug or params.get("l1CategoryId"):
        return params
    page_url = f"{BASE}/l/{slug}/"
    html = await _fetch_text(
        session, page_url, expect_json=False, request_kwargs=request_kwargs
    )
    cat_id = extract_l1_category_id(html, slug)
    if cat_id is None:
        raise RuntimeError(
            f"Не удалось определить l1CategoryId для категории «{slug}». "
            "Укажите l1CategoryId в URL API вручную."
        )
    params["l1CategoryId"] = str(cat_id)
    params.setdefault("attributesByKey[]", ["Language:all-languages"])
    return params


async def _fetch_search_page(
    session: aiohttp.ClientSession,
    api_url: str,
    *,
    request_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = await _fetch_text(session, api_url, request_kwargs=request_kwargs)
    if not raw.strip():
        return {"listings": [], "totalResultCount": 0}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Некорректный ответ API: ожидался объект JSON")
    return data


async def parse_2dehands(
    source_url: str,
    *,
    limit: int = 100,
    max_pages: int | None = None,
    proxy: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Собирает объявления с 2dehands.be в формате void-parser.

    source_url — URL страницы поиска/категории на сайте или прямой lrp/api/search.
    """
    if limit < 1:
        raise ValueError("limit должен быть >= 1")

    browser_url = normalize_browser_url(source_url)
    base_params = build_api_params_from_browser_url(browser_url)

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    offset = int(base_params.get("offset", 0) or 0)
    pages = 0

    async with search_session(proxy) as (session, req_kw):
        base_params = await _resolve_category_id(
            session, base_params, request_kwargs=req_kw
        )

        while len(items) < limit:
            if max_pages is not None and pages >= max_pages:
                break
            pages += 1
            page_limit = page_request_limit(limit - len(items), page_size=100)

            api_url = api_url_from_params(
                base_params, limit=page_limit, offset=offset
            )
            data = await _fetch_search_page(
                session, api_url, request_kwargs=req_kw
            )

            listings = data.get("listings") or []
            if not listings:
                break

            for listing in listings:
                item_id = listing.get("itemId")
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                items.append(listing_to_void_item(listing))
                if len(items) >= limit:
                    break

            if len(items) >= limit:
                break

            total = int(data.get("totalResultCount") or 0)
            offset += page_limit
            if offset >= total:
                break

    return {"items": items}


def parse_2dehands_sync(
    source_url: str,
    *,
    limit: int = 100,
    max_pages: int | None = None,
    proxy: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return asyncio.run(
        parse_2dehands(
            source_url,
            limit=limit,
            max_pages=max_pages,
            proxy=proxy,
        )
    )
