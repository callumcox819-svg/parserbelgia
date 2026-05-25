from __future__ import annotations

import logging
import os
from typing import Any

from .article_detail import article_page_url, parse_article_page_html
from .html_parse import article_needs_enrichment, extract_articles_from_html
from .http_client import BROWSER_HEADERS, browse_session, category_page_url, throttle
from .void_format import article_to_void_item

logger = logging.getLogger(__name__)

MAX_PAGES_PER_CATEGORY = 30
PAGE_SIZE_HINT = 48


def _enrich_enabled() -> bool:
    raw = os.environ.get("RICARDO_ENRICH_DETAILS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _http_error(
    status: int, body: str, proxy: str | None, *, url: str = ""
) -> RuntimeError:
    low = body.lower()
    if status == 403 and ("cloudflare" in low or "forbidden" in low):
        msg = (
            "HTTP 403 Forbidden — Ricardo/Cloudflare. "
            "Используйте residential прокси **Швейцарии (CH)** "
            "(socks5://user:pass@host:port)."
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
        msg += " Сейчас используется ваш прокси."
    return RuntimeError(msg)


async def _enrich_article(
    session: Any,
    article: dict[str, Any],
    *,
    proxy: str | None,
) -> dict[str, Any]:
    article_id = str(article.get("id") or "").strip()
    if not article_id:
        return article

    url = article_page_url(article_id)
    await throttle()
    async with session.get(url, headers=BROWSER_HEADERS) as resp:
        html = await resp.text()
        if resp.status >= 400:
            logger.warning("ricardo article %s HTTP %s", article_id, resp.status)
            return article

    detail = parse_article_page_html(html, article_id=article_id)
    if not detail:
        return article

    merged = dict(article)
    for key, val in detail.items():
        if val is None or val == "":
            continue
        if key in ("title",) and merged.get("title") and not article_needs_enrichment(
            article
        ):
            continue
        merged[key] = val
    return merged


async def parse_ricardo_categories(
    category_slugs: list[str],
    *,
    limit: int,
    proxy: str | None = None,
    skip_seller_ids: set[int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not category_slugs:
        raise ValueError("Нужна хотя бы одна категория")

    skip = set(skip_seller_ids) if skip_seller_ids else set()
    raw_articles: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    skipped_404: list[str] = []
    enrich = _enrich_enabled()

    async with browse_session(proxy) as (session, _kw):
        for slug in category_slugs:
            if len(raw_articles) >= limit:
                break

            page = 1
            empty_streak = 0
            category_failed = False
            while len(raw_articles) < limit and page <= MAX_PAGES_PER_CATEGORY:
                await throttle()
                url = category_page_url(slug, page)
                async with session.get(url, headers=BROWSER_HEADERS) as resp:
                    html = await resp.text()
                    if resp.status == 404:
                        logger.warning("ricardo category 404: %s", url)
                        skipped_404.append(slug)
                        category_failed = True
                        break
                    if resp.status >= 400:
                        raise _http_error(resp.status, html, proxy, url=url)

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
            for idx, article in enumerate(raw_articles):
                if not article_needs_enrichment(article):
                    continue
                try:
                    raw_articles[idx] = await _enrich_article(
                        session, article, proxy=proxy
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
