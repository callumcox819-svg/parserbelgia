from __future__ import annotations

import logging
import re
from typing import Any

from bot_app.categories import CATEGORY_BY_KEY
from bot_app.platforms import PLATFORM_RICARDO, normalize_platform
from bot_app.ricardo_categories import RICARDO_CATEGORY_BY_KEY
from bot_app.storage import repo
from settings import normalize_proxy
from twodehands_parser.category_parse import parse_l1_categories
from twodehands_parser.http_client import BROWSER_HEADERS, search_session
from twodehands_parser.url_builder import BASE, extract_l1_category_id
from ricardo_parser.category_parse import parse_ricardo_categories

logger = logging.getLogger(__name__)


async def _resolve_l1_id(category_key: str, proxy: str | None) -> int:
    cached = await repo.get_cached_l1_id("2dehands", category_key)
    if cached:
        return cached

    default = repo.default_l1_id("2dehands", category_key)
    if default:
        await repo.cache_category_l1_id("2dehands", category_key, default)
        return default

    page_url = f"{BASE}/l/{category_key}/"
    async with search_session(proxy) as (session, request_kwargs):
        async with session.get(
            page_url, headers=BROWSER_HEADERS, **request_kwargs
        ) as resp:
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
    await repo.cache_category_l1_id("2dehands", category_key, cat_id)
    return cat_id


def _seller_ids_from_items(items: list[dict[str, Any]]) -> set[int]:
    sellers: set[int] = set()
    for item in items:
        link = item.get("person_link") or ""
        match = re.search(r"/(\d+)/?\s*$", link.rstrip("/"))
        if match:
            sellers.add(int(match.group(1)))
    return sellers


async def _run_2dehands(
    user_id: int,
    keys: list[str],
    limit: int,
    proxies: list[str | None],
    skip_sellers: set[int],
) -> dict[str, Any]:
    l1_ids: list[int] = []
    resolve_proxy = proxies[0]
    for key in keys:
        l1_ids.append(await _resolve_l1_id(key, resolve_proxy))

    last_error: Exception | None = None
    for proxy in proxies:
        try:
            result = await parse_l1_categories(
                l1_ids,
                limit=limit,
                proxy=proxy,
                skip_seller_ids=set(skip_sellers),
            )
            return result
        except RuntimeError as exc:
            last_error = exc
            if "403" not in str(exc) and "Forbidden" not in str(exc):
                raise
            logger.warning("2dehands 403 proxy=%s, try next", proxy)
    if last_error:
        raise last_error
    raise RuntimeError("Не удалось выполнить парсинг 2dehands.")


async def _run_ricardo(
    keys: list[str],
    limit: int,
    proxies: list[str | None],
    skip_sellers: set[int],
) -> dict[str, Any]:
    slugs: list[str] = []
    for key in keys:
        cat = RICARDO_CATEGORY_BY_KEY.get(key)
        if cat:
            slugs.append(cat.slug)

    if not slugs:
        raise ValueError("Нет категорий Ricardo для парсинга.")

    last_error: Exception | None = None
    for proxy in proxies:
        try:
            return await parse_ricardo_categories(
                slugs,
                limit=limit,
                proxy=proxy,
                skip_seller_ids=set(skip_sellers),
            )
        except RuntimeError as exc:
            last_error = exc
            if "403" not in str(exc) and "Forbidden" not in str(exc):
                raise
            logger.warning("ricardo 403 proxy=%s, try next", proxy)
    if last_error:
        raise last_error
    raise RuntimeError("Не удалось выполнить парсинг Ricardo.")


async def run_user_parse(user_id: int, fallback_proxy: str | None) -> dict[str, Any]:
    settings = await repo.get_user_settings(user_id)
    platform = normalize_platform(settings.get("platform"))
    keys = await repo.get_enabled_category_keys(user_id, platform)
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

    skip_sellers = await repo.get_seen_seller_ids(user_id, platform)
    limit = int(settings["json_limit"])

    if platform == PLATFORM_RICARDO:
        result = await _run_ricardo(keys, limit, proxies, skip_sellers)
    else:
        result = await _run_2dehands(user_id, keys, limit, proxies, skip_sellers)

    new_sellers = _seller_ids_from_items(result.get("items", []))
    await repo.add_seen_sellers(user_id, platform, new_sellers)
    await repo.increment_parse_count(user_id)
    return result
