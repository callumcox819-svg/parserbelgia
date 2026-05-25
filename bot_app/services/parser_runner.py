from __future__ import annotations

import logging
from typing import Any

from bot_app.categories import CATEGORY_BY_KEY
from bot_app.storage import repo
from settings import normalize_proxy
from twodehands_parser.category_parse import parse_l1_categories
from twodehands_parser.http_client import search_session
from twodehands_parser.url_builder import BASE, extract_l1_category_id

logger = logging.getLogger(__name__)


async def _resolve_l1_id(category_key: str, proxy: str | None) -> int:
    cached = await repo.get_cached_l1_id(category_key)
    if cached:
        return cached

    default = repo.default_l1_id(category_key)
    if default:
        await repo.cache_category_l1_id(category_key, default)
        return default

    page_url = f"{BASE}/l/{category_key}/"
    async with search_session(proxy) as (session, request_kwargs):
        async with session.get(page_url, **request_kwargs) as resp:
            html = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Категория HTTP {resp.status}")

    cat_id = extract_l1_category_id(html, category_key)
    if cat_id is None:
        cat = CATEGORY_BY_KEY.get(category_key)
        if cat and cat.l1_id:
            cat_id = cat.l1_id
    if cat_id is None:
        raise RuntimeError(f"Не найден ID категории: {category_key}")
    await repo.cache_category_l1_id(category_key, cat_id)
    return cat_id


async def _parse_with_proxy(
    l1_ids: list[int],
    limit: int,
    proxy: str | None,
    skip_sellers: set[int],
) -> dict[str, Any]:
    return await parse_l1_categories(
        l1_ids,
        limit=limit,
        proxy=proxy,
        skip_seller_ids=skip_sellers,
    )


async def run_user_parse(user_id: int, fallback_proxy: str | None) -> dict[str, Any]:
    settings = await repo.get_user_settings(user_id)
    keys = await repo.get_enabled_category_keys(user_id)
    if not keys:
        raise ValueError("Включите хотя бы одну категорию в настройках.")

    user_proxy = normalize_proxy(settings.get("proxy"))
    fallback_proxy = normalize_proxy(fallback_proxy)

    proxies: list[str | None] = []
    if user_proxy:
        proxies.append(user_proxy)
    if fallback_proxy and fallback_proxy != user_proxy:
        proxies.append(fallback_proxy)
    if not proxies:
        proxies.append(None)

    l1_ids: list[int] = []
    resolve_proxy = proxies[0]
    for key in keys:
        l1_ids.append(await _resolve_l1_id(key, resolve_proxy))

    skip_sellers = await repo.get_seen_seller_ids(user_id)
    limit = int(settings["json_limit"])

    last_error: Exception | None = None
    for proxy in proxies:
        try:
            result = await _parse_with_proxy(l1_ids, limit, proxy, set(skip_sellers))
            last_error = None
            break
        except RuntimeError as exc:
            last_error = exc
            if "403" not in str(exc) and "Forbidden" not in str(exc):
                raise
            logger.warning("parse 403 with proxy=%s, try next", proxy)
            continue
    else:
        if last_error:
            raise last_error
        raise RuntimeError("Не удалось выполнить парсинг.")

    new_sellers: set[int] = set()
    for item in result.get("items", []):
        link = item.get("person_link") or ""
        parts = link.rstrip("/").split("/")
        if parts and parts[-1].isdigit():
            new_sellers.add(int(parts[-1]))

    await repo.add_seen_sellers(user_id, new_sellers)
    await repo.increment_parse_count(user_id)
    return result
