from __future__ import annotations

import json
import re
from typing import Any

_ARTICLE_ID_KEYS = ("id", "articleId", "article_id", "listingId")
_LINK_RE = re.compile(
    r'href="(/de/a/[^"?#]+)"',
    re.IGNORECASE,
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _first_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _normalize_article(raw: dict[str, Any]) -> dict[str, Any] | None:
    article_id = ""
    for key in _ARTICLE_ID_KEYS:
        val = raw.get(key)
        if val is not None and str(val).strip():
            article_id = str(val).strip()
            break
    title = _first_str(raw, "title", "name")
    if not article_id or not title:
        return None

    slug = _first_str(raw, "slug", "urlSlug", "seoSlug")
    href = _first_str(raw, "href", "url", "link")
    if href and not href.startswith("http"):
        href = f"https://www.ricardo.ch{href}" if href.startswith("/") else href
    if not href and slug:
        href = f"https://www.ricardo.ch/de/a/{slug}-{article_id}/"
    elif not href:
        href = f"https://www.ricardo.ch/de/a/-{article_id}/"

    seller_id = _first_str(raw, "sellerId", "seller_id", "sellerID")
    seller_name = _first_str(raw, "sellerName", "seller_name", "sellerNickname")

    image = _first_str(raw, "image", "imageUrl", "thumbnail")
    if not image:
        images = raw.get("images") or raw.get("imageUrls") or []
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                image = first
            elif isinstance(first, dict):
                image = _first_str(first, "url", "src", "image")

    buy_now = raw.get("buy_now_price", raw.get("buyNowPrice"))
    bid = raw.get("bid_price", raw.get("bidPrice", raw.get("currentPrice")))
    bids_count = raw.get("bids_count", raw.get("bidsCount", raw.get("bidCount")))

    location = ""
    shipping = raw.get("shipping")
    if isinstance(shipping, list) and shipping:
        sh = shipping[0]
        if isinstance(sh, dict):
            location = _first_str(sh, "city", "zip_code", "zipCode")
    if not location:
        location = _first_str(raw, "city", "location")

    return {
        "id": article_id,
        "title": title,
        "href": href,
        "image": image,
        "buy_now_price": buy_now,
        "bid_price": bid,
        "bids_count": bids_count,
        "seller_id": seller_id,
        "seller_name": seller_name,
        "condition_key": _first_str(raw, "condition_key", "conditionKey"),
        "creation_date": _first_str(
            raw, "creation_date", "creationDate", "start_date", "startDate"
        ),
        "description": _first_str(raw, "description", "subtitle"),
        "location": location,
    }


def _walk_json(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        norm = _normalize_article(node)
        if norm:
            out.append(norm)
        for val in node.values():
            _walk_json(val, out)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, out)


def _dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for art in articles:
        aid = art.get("id") or ""
        if not aid or aid in seen:
            continue
        seen.add(aid)
        unique.append(art)
    return unique


def extract_articles_from_html(html: str) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    match = _NEXT_DATA_RE.search(html)
    if match:
        try:
            data = json.loads(match.group(1))
            _walk_json(data, articles)
        except json.JSONDecodeError:
            pass

    if not articles:
        for rel in _LINK_RE.findall(html):
            tail = rel.rstrip("/").split("-")[-1]
            if tail.isdigit():
                articles.append(
                    {
                        "id": tail,
                        "title": rel.split("/")[-2].replace("-", " ")[:80],
                        "href": f"https://www.ricardo.ch{rel}",
                        "image": "",
                        "buy_now_price": None,
                        "bid_price": None,
                        "bids_count": None,
                        "seller_id": "",
                        "seller_name": "",
                        "condition_key": "",
                        "creation_date": "",
                        "description": "",
                        "location": "",
                    }
                )

    return _dedupe_articles(articles)
