from __future__ import annotations

import logging
import os
from typing import Any

from .article_detail import article_page_url, parse_article_page_html
from .html_parse import article_needs_enrichment, extract_articles_from_html
from .http_client import (
    BASE,
    LANG,
    category_page_url,
    is_blocked_response,
    navigation_headers,
    proxy_label,
    throttle,
    throttle_after_block,
)
from .proxy_pool import RicardoProxyPool, proxy_pool
from .void_format import article_to_void_item

logger = logging.getLogger(__name__)

MAX_PAGES_PER_CATEGORY = 30
PAGE_SIZE_HINT = 48


def _enrich_enabled() -> bool:
    raw = os.environ.get("RICARDO_ENRICH_DETAILS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _normalize_proxies(
    proxy: str | None,
    proxies: list[str | None] | None,
) -> list[str | None]:
    if proxies:
        return proxies
    if proxy:
        return [proxy]
    return [None]


def _http_error(
    status: int, body: str, proxy: str | None, *, url: str = ""
) -> RuntimeError:
    low = body.lower()
    if status == 403 and (
        "cloudflare" in low or "forbidden" in low or "cf-ray" in low
    ):
        msg = (
            "HTTP 403 Forbidden — Ricardo/Cloudflare. "
            "Используйте несколько residential прокси **Швейцарии (CH)** "
            "(socks5://user:pass@host:port), по одному на строку."
        )
    elif status == 404:
        msg = (
            f"HTTP 404 — категория не найдена на Ricardo"
            + (f": {url}" if url else "")
            + ". Обновите список категорий или выберите другие."
        )
    else:
        snippet = body[:200].replace("\n", " ")
        if "__next_error__" in low:
            snippet = "страница ошибки Ricardo"
        msg = f"HTTP {status}" + (f" ({url})" if url else "") + f": {snippet}"
    if proxy:
        msg += f" Прокси: {proxy_label(proxy)}."
    return RuntimeError(msg)


async def _fetch_html(
    pool: RicardoProxyPool,
    url: str,
    *,
    referer: str,
    enrich: bool = False,
) -> tuple[str, int, str | None]:
    """GET с ротацией прокси при 403/429."""
    last_status = 0
    for proxy in pool.proxies_for_retry():
        await throttle(enrich=enrich)
        try:
            session = await pool.get_session(proxy)
        except Exception:
            continue

        headers = navigation_headers(referer)
        try:
            async with session.get(url, headers=headers) as resp:
                html = await resp.text()
                last_status = resp.status
                if is_blocked_response(resp.status, html):
                    logger.warning(
                        "ricardo blocked %s HTTP %s proxy=%s",
                        url,
                        resp.status,
                        proxy_label(proxy),
                    )
                    pool.mark_blocked(proxy)
                    await throttle_after_block()
                    continue
                if resp.status >= 400:
                    return html, resp.status, proxy
                return html, resp.status, proxy
        except Exception as exc:
            logger.warning(
                "ricardo request error %s proxy=%s: %s",
                url,
                proxy_label(proxy),
                exc,
            )
            pool.mark_blocked(proxy, seconds=60)
    return "", last_status, None


async def _enrich_article(
    pool: RicardoProxyPool,
    article: dict[str, Any],
    *,
    referer: str,
) -> dict[str, Any]:
    article_id = str(article.get("id") or "").strip()
    if not article_id:
        return article

    url = article_page_url(article_id)
    html, status, _used = await _fetch_html(
        pool, url, referer=referer, enrich=True
    )
    if status >= 400 or not html:
        if status:
            logger.warning("ricardo article %s HTTP %s (all proxies)", article_id, status)
        return article

    detail = parse_article_page_html(html, article_id=article_id)
    if not detail:
        return article

    merged = dict(article)
    for key, val in detail.items():
        if val is None or val == "":
            continue
        merged[key] = val
    return merged


async def parse_ricardo_categories(
    category_slugs: list[str],
    *,
    limit: int,
    proxy: str | None = None,
    proxies: list[str | None] | None = None,
    skip_seller_ids: set[int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_slugs:
        raise ValueError("Нужна хотя бы одна категория")

    proxy_list = _normalize_proxies(proxy, proxies)
    skip = set(skip_seller_ids) if skip_seller_ids else set()
    raw_articles: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    skipped_404: list[str] = []
    enrich = _enrich_enabled()
    referer = f"{BASE}/{LANG}/"

    async with proxy_pool(proxy_list) as pool:
        for slug in category_slugs:
            if len(raw_articles) >= limit:
                break

            page = 1
            empty_streak = 0
            category_failed = False
            while len(raw_articles) < limit and page <= MAX_PAGES_PER_CATEGORY:
                url = category_page_url(slug, page)
                html, status, used_proxy = await _fetch_html(
                    pool, url, referer=referer, enrich=False
                )
                referer = url

                if status == 404:
                    logger.warning("ricardo category 404: %s", url)
                    skipped_404.append(slug)
                    category_failed = True
                    break
                if status >= 400:
                    raise _http_error(status, html, used_proxy, url=url)

                articles = extract_articles_from_html(html)
                if not articles:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
                    page += 1
                    continue
                empty_streak = 0

                added = 0
                for article in articles:
                    aid = str(article.get("id") or "")
                    if not aid or aid in seen_items:
                        continue

                    seller_raw = str(article.get("seller_id") or "").strip()
                    seller_id: int | None = None
                    if seller_raw.isdigit():
                        seller_id = int(seller_raw)
                        if seller_id in skip:
                            continue

                    seen_items.add(aid)
                    article["_category_url"] = url
                    raw_articles.append(article)
                    if seller_id is not None:
                        skip.add(seller_id)
                    added += 1
                    if len(raw_articles) >= limit:
                        break

                if added == 0:
                    break
                if len(articles) < PAGE_SIZE_HINT:
                    break
                page += 1

            if category_failed:
                continue

        if enrich:
            logger.info(
                "ricardo enrich %s items, proxies=%s",
                sum(1 for a in raw_articles if article_needs_enrichment(a)),
                len(pool.proxies),
            )
            for idx, article in enumerate(raw_articles):
                if not article_needs_enrichment(article):
                    continue
                cat_ref = str(article.pop("_category_url", None) or referer)
                try:
                    raw_articles[idx] = await _enrich_article(
                        pool, article, referer=cat_ref
                    )
                except Exception as exc:
                    logger.warning(
                        "ricardo enrich %s failed: %s",
                        article.get("id"),
                        exc,
                    )

    if not raw_articles and skipped_404 and len(skipped_404) == len(category_slugs):
        raise RuntimeError(
            "Все выбранные категории Ricardo вернули 404. "
            "Перезапустите бота после деплоя или выберите другие категории."
        )

    items = [article_to_void_item(a) for a in raw_articles[:limit]]
    return {"items": items}
