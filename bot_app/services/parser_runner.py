from __future__ import annotations

import logging
from typing import Any

import aiohttp

from bot_app.categories import CATEGORY_BY_KEY
from bot_app.storage import repo
from settings import normalize_proxy
from twodehands_parser.category_parse import parse_l1_categories
from twodehands_parser.url_builder import BASE, extract_l1_category_id

logger = logging.getLogger(__name__)


async def _resolve_l1_id(category_key: str) -> int:
    cached = await repo.get_cached_l1_id(category_key)
    if cached:
        return cached

    default = repo.default_l1_id(category_key)
    if default:
        await repo.cache_category_l1_id(category_key, default)
        return default

    page_url = f"{BASE}/l/{category_key}/"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(page_url) as resp:
            html = await resp.text()
    cat_id = extract_l1_category_id(html, category_key)
    if cat_id is None:
        raise RuntimeError(f"Не найден ID категории: {category_key}")
    await repo.cache_category_l1_id(category_key, cat_id)
    return cat_id


async def run_user_parse(user_id: int, fallback_proxy: str | None) -> dict[str, Any]:
    settings = await repo.get_user_settings(user_id)
    keys = await repo.get_enabled_category_keys(user_id)
    if not keys:
        raise ValueError("Включите хотя бы одну категорию в настройках.")

    l1_ids: list[int] = []
    for key in keys:
        l1_ids.append(await _resolve_l1_id(key))

    proxy = normalize_proxy(settings.get("proxy")) or fallback_proxy
    skip_sellers = await repo.get_seen_seller_ids(user_id)
    limit = int(settings["json_limit"])

    result = await parse_l1_categories(
        l1_ids,
        limit=limit,
        proxy=proxy,
        skip_seller_ids=set(skip_sellers),
    )

    new_sellers: set[int] = set()
    for item in result.get("items", []):
        link = item.get("person_link") or ""
        # person_link: https://www.2dehands.be/u/52333357/
        parts = link.rstrip("/").split("/")
        if parts and parts[-1].isdigit():
            new_sellers.add(int(parts[-1]))

    await repo.add_seen_sellers(user_id, new_sellers)
    await repo.increment_parse_count(user_id)
    return result
