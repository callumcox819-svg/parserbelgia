from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

ProgressFn = Callable[[dict[str, Any]], Awaitable[None]] | None

from bot_app.categories import CATEGORY_BY_KEY
from bot_app.platforms import PLATFORM_RICARDO, normalize_platform
from bot_app.ricardo_categories import RICARDO_CATEGORY_BY_KEY
from bot_app.storage import repo
from settings import normalize_proxy, parse_proxy_list
from twodehands_parser.category_parse import parse_l1_categories
from twodehands_parser.filters import VEHICLE_CATEGORY_KEYS
from twodehands_parser.http_client import BROWSER_HEADERS, search_session
from twodehands_parser.url_builder import BASE, extract_l1_category_id
from ricardo_parser.category_parse import parse_ricardo_categories

logger = logging.getLogger(__name__)

_PARSE_LOCK = asyncio.Lock()


def resolve_user_proxies(settings: dict[str, Any]) -> list[str | None]:
    """Прокси пользователя из настроек; если не задан — прямое подключение [None]."""
    proxies = parse_proxy_list(settings.get("proxy"))
    return proxies if proxies else [None]


async def _resolve_l1_id(category_key: str, proxy: str | None) -> int:
    default = repo.default_l1_id("2dehands", category_key)
    cached = await repo.get_cached_l1_id("2dehands", category_key)
    if default:
        if cached and cached != default:
            logger.info(
                "2dehands category %s: cache id %s -> %s",
                category_key,
                cached,
                default,
            )
        await repo.cache_category_l1_id("2dehands", category_key, default)
        return default
    if cached:
        return cached

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
        match = re.search(r"/(\d+)/?\s*$", str(link).rstrip("/"))
        if match:
            sellers.add(int(match.group(1)))
    return sellers


async def _run_2dehands(
    user_id: int,
    keys: list[str],
    limit: int,
    proxies: list[str | None],
    skip_sellers: set[int],
    *,
    skip_auction_listings: bool = False,
    skip_vehicle_categories: bool = False,
    on_progress: ProgressFn = None,
    parse_count: int = 0,
    deadline: float | None = None,
) -> dict[str, Any]:
    if skip_vehicle_categories:
        keys = [k for k in keys if k not in VEHICLE_CATEGORY_KEYS]

    if not keys:
        raise ValueError(
            "Нет категорий для парсинга: включите категории или отключите "
            "фильтр «без авто/броммеров» в настройках → Фильтры."
        )

    l1_ids: list[int] = []
    resolve_proxy = proxies[0]
    for key in keys:
        l1_ids.append(await _resolve_l1_id(key, resolve_proxy))

    try:
        return await parse_l1_categories(
            l1_ids,
            limit=limit,
            proxies=proxies,
            skip_seller_ids=set(skip_sellers),
            skip_auction_listings=skip_auction_listings,
            on_progress=on_progress,
            parse_count=parse_count,
            deadline=deadline,
        )
    except RuntimeError as exc:
        if "403" not in str(exc) and "Forbidden" not in str(exc):
            raise
        logger.error("2dehands failed all proxies: %s", exc)
        raise


async def _run_ricardo(
    keys: list[str],
    limit: int,
    proxies: list[str | None],
    skip_sellers: set[int],
    *,
    deadline: float | None = None,
) -> dict[str, Any]:
    slugs: list[str] = []
    for key in keys:
        cat = RICARDO_CATEGORY_BY_KEY.get(key)
        if cat:
            slugs.append(cat.slug)

    if not slugs:
        raise ValueError("Нет категорий Ricardo для парсинга.")

    try:
        return await parse_ricardo_categories(
            slugs,
            limit=limit,
            proxies=proxies,
            skip_seller_ids=set(skip_sellers),
            deadline=deadline,
        )
    except RuntimeError as exc:
        if "403" not in str(exc) and "Forbidden" not in str(exc) and "Cloudflare" not in str(
            exc
        ):
            raise
        logger.error("ricardo failed all proxies in pool: %s", exc)
        raise


async def run_user_parse(
    user_id: int,
    *,
    on_progress: ProgressFn = None,
    on_waiting: ProgressFn = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    if _PARSE_LOCK.locked():
        logger.info("parse user=%s waiting — another run in progress", user_id)
        if on_waiting:
            await on_waiting({"queued": True})
    async with _PARSE_LOCK:
        return await _run_user_parse_locked(
            user_id,
            on_progress=on_progress,
            deadline=deadline,
        )


async def _run_user_parse_locked(
    user_id: int,
    *,
    on_progress: ProgressFn = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    settings = await repo.get_user_settings(user_id)
    platform = normalize_platform(settings.get("platform"))
    keys = await repo.get_enabled_category_keys(user_id, platform)
    if not keys:
        raise ValueError("Включите хотя бы одну категорию в настройках.")

    proxies = resolve_user_proxies(settings)
    remember_sellers = bool(settings.get("filter_remember_sellers", True))
    limit = int(settings["json_limit"])
    parse_count = int(settings.get("parse_count") or 0)
    seen_in_db = 0
    sellers_trimmed = 0
    skip_sellers: set[int] = set()
    if remember_sellers:
        sellers_trimmed = await repo.trim_seen_sellers(user_id, platform)
        if sellers_trimmed:
            logger.info(
                "parse user=%s trimmed %s old sellers (cap=%s)",
                user_id,
                sellers_trimmed,
                repo.seller_memory_cap(),
            )
        skip_sellers = await repo.get_seen_seller_ids(user_id, platform)
        seen_in_db = len(skip_sellers)

    logger.info(
        "parse user=%s platform=%s limit=%s cats=%s proxies=%s seen_sellers=%s",
        user_id,
        platform,
        limit,
        len(keys),
        len(proxies),
        len(skip_sellers),
    )
    if platform == PLATFORM_RICARDO:
        result = await _run_ricardo(
            keys, limit, proxies, skip_sellers, deadline=deadline
        )
    else:
        result = await _run_2dehands(
            user_id,
            keys,
            limit,
            proxies,
            skip_sellers,
            skip_auction_listings=bool(settings.get("filter_skip_bids", True)),
            skip_vehicle_categories=bool(settings.get("filter_skip_vehicles", True)),
            on_progress=on_progress,
            parse_count=parse_count,
            deadline=deadline,
        )

    stats = result.setdefault("stats", {})
    stats["proxies_used"] = len(proxies)
    stats["seen_sellers_before"] = seen_in_db if remember_sellers else 0
    stats["remember_sellers"] = remember_sellers
    if remember_sellers:
        stats["seller_memory_cap"] = repo.seller_memory_cap()
        stats["sellers_trimmed"] = sellers_trimmed

    if remember_sellers:
        new_sellers = _seller_ids_from_items(result.get("items", []))
        await repo.add_seen_sellers(user_id, platform, new_sellers)
    await repo.increment_parse_count(user_id)
    return result
