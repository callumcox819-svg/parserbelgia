from __future__ import annotations

from typing import Any

from .html_parse import extract_articles_from_html
from .http_client import BROWSER_HEADERS, browse_session, category_page_url, throttle
from .void_format import article_to_void_item

MAX_PAGES_PER_CATEGORY = 30
PAGE_SIZE_HINT = 48


def _http_error(status: int, body: str, proxy: str | None) -> RuntimeError:
    low = body.lower()
    if status == 403 and ("cloudflare" in low or "forbidden" in low):
        msg = (
            "HTTP 403 Forbidden — Ricardo/Cloudflare. "
            "Используйте residential прокси **Швейцарии (CH)** "
            "(socks5://user:pass@host:port)."
        )
    else:
        msg = f"HTTP {status}: {body[:300]}"
    if proxy:
        msg += " Сейчас используется ваш прокси."
    return RuntimeError(msg)


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
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()

    async with browse_session(proxy) as (session, _kw):
        for slug in category_slugs:
            if len(items) >= limit:
                break

            page = 1
            empty_streak = 0
            while len(items) < limit and page <= MAX_PAGES_PER_CATEGORY:
                await throttle()
                url = category_page_url(slug, page)
                async with session.get(url, headers=BROWSER_HEADERS) as resp:
                    html = await resp.text()
                    if resp.status >= 400:
                        raise _http_error(resp.status, html, proxy)

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
                    items.append(article_to_void_item(article))
                    if seller_id is not None:
                        skip.add(seller_id)
                    added += 1
                    if len(items) >= limit:
                        break

                if added == 0:
                    break
                if len(articles) < PAGE_SIZE_HINT:
                    break
                page += 1

    return {"items": items}
