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
_LISTING_ARRAY_KEYS = (
    "articles",
    "listings",
    "searchResults",
    "results",
    "items",
    "offers",
    "openOffers",
    "open_offers",
)
_CARD_MARKERS = (
    "buyNowPrice",
    "buy_now_price",
    "bidPrice",
    "bid_price",
    "image",
    "imageUrl",
    "hasBuyNow",
    "has_buy_now",
)


def _first_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _article_id(raw: dict[str, Any]) -> str:
    for key in _ARTICLE_ID_KEYS:
        val = raw.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _normalize_image_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if "ricardostatic.ch" in url and "/t_" in url:
        return re.sub(r"/t_[^/]+", "/t_1000x750", url)
    return url


def _offer_date(raw: dict[str, Any]) -> str:
    offer = raw.get("offer")
    if isinstance(offer, dict):
        return _first_str(offer, "start_date", "startDate", "creation_date", "creationDate")
    return ""


def _pick_price(raw: dict[str, Any]) -> Any:
    for key in (
        "buy_now_price",
        "buyNowPrice",
        "price",
        "fixedPrice",
        "fixed_price",
    ):
        val = raw.get(key)
        if val is not None and val != "":
            return val
    offer = raw.get("offer")
    if isinstance(offer, dict):
        val = offer.get("price") or offer.get("buy_now_price") or offer.get("buyNowPrice")
        if val is not None and val != "":
            return val
    pricing = raw.get("pricing")
    if isinstance(pricing, dict):
        return pricing.get("amount") or pricing.get("price")
    return raw.get("bid_price", raw.get("bidPrice", raw.get("currentPrice")))


def _looks_like_listing_card(raw: dict[str, Any]) -> bool:
    aid = _article_id(raw)
    if not aid.isdigit():
        return False
    if _first_str(raw, "title", "name"):
        return True
    return any(raw.get(k) is not None for k in _CARD_MARKERS)


def _normalize_article(raw: dict[str, Any]) -> dict[str, Any] | None:
    article_id = _article_id(raw)
    if not article_id:
        return None

    title = _first_str(raw, "title", "name", "displayTitle")
    if not title:
        desc = raw.get("description")
        if isinstance(desc, dict):
            html_desc = desc.get("html") or ""
            if isinstance(html_desc, str) and html_desc.strip():
                title = re.sub(r"<[^>]+>", " ", html_desc).strip()[:120]
    slug = _first_str(raw, "slug", "urlSlug", "seoSlug")
    href = _first_str(raw, "href", "url", "link")
    if href and not href.startswith("http"):
        href = f"https://www.ricardo.ch{href}" if href.startswith("/") else href
    if not href:
        href = f"https://www.ricardo.ch/de/a/{article_id}/"

    seller_id = _first_str(raw, "sellerId", "seller_id", "sellerID")
    seller_name = _first_str(raw, "sellerName", "seller_name", "sellerNickname")
    seller = raw.get("seller")
    if isinstance(seller, dict):
        if not seller_id:
            seller_id = _first_str(seller, "id", "sellerId")
        if not seller_name:
            seller_name = _first_str(seller, "nickname", "name")

    image = _normalize_image_url(_first_str(raw, "image", "imageUrl", "thumbnail"))
    if not image:
        images = raw.get("images") or raw.get("imageUrls") or []
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                image = _normalize_image_url(first)
            elif isinstance(first, dict):
                image = _normalize_image_url(
                    _first_str(first, "url", "src", "image", "href")
                )

    buy_now = _pick_price(raw)
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

    if not title and slug:
        title = slug.replace("-", " ").strip()

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
        )
        or _offer_date(raw),
        "description": _first_str(raw, "description", "subtitle"),
        "location": location,
    }


def _collect_listing_arrays(node: Any, depth: int = 0, max_depth: int = 8) -> list[list[dict[str, Any]]]:
    found: list[list[dict[str, Any]]] = []
    if depth > max_depth:
        return found
    if isinstance(node, dict):
        for key, val in node.items():
            if key in _LISTING_ARRAY_KEYS and isinstance(val, list) and val:
                cards = [x for x in val if isinstance(x, dict) and _looks_like_listing_card(x)]
                if cards:
                    found.append(cards)
            found.extend(_collect_listing_arrays(val, depth + 1, max_depth))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_listing_arrays(item, depth + 1, max_depth))
    return found


def _pick_best_listing_batch(arrays: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    best: list[dict[str, Any]] = []
    for batch in arrays:
        if len(batch) > len(best):
            best = batch
    return best


def _walk_listing_cards(node: Any, out: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 14:
        return
    if isinstance(node, dict):
        if _looks_like_listing_card(node):
            norm = _normalize_article(node)
            if norm:
                out.append(norm)
        for val in node.values():
            _walk_listing_cards(val, out, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _walk_listing_cards(item, out, depth + 1)


def _extract_from_next_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    page_props = data.get("props", {}).get("pageProps", {})
    if not isinstance(page_props, dict):
        page_props = {}

    articles: list[dict[str, Any]] = []
    for key in _LISTING_ARRAY_KEYS:
        val = page_props.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    norm = _normalize_article(item)
                    if norm:
                        articles.append(norm)

    nested = page_props.get("data") or page_props.get("search") or page_props.get("category")
    if isinstance(nested, dict):
        for key in _LISTING_ARRAY_KEYS:
            val = nested.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        norm = _normalize_article(item)
                        if norm:
                            articles.append(norm)

    if not articles:
        batch = _pick_best_listing_batch(_collect_listing_arrays(page_props))
        for item in batch:
            norm = _normalize_article(item)
            if norm:
                articles.append(norm)

    if not articles:
        _walk_listing_cards(data, articles)

    return articles


def _articles_from_links(html: str) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for rel in _LINK_RE.findall(html):
        tail = rel.rstrip("/").split("-")[-1]
        if not tail.isdigit():
            continue
        slug_part = rel.split("/")[-2] if rel.endswith("/") else rel.split("/")[-1]
        title = slug_part.replace("-", " ")[:120] if slug_part else ""
        articles.append(
            {
                "id": tail,
                "title": title,
                "href": f"https://www.ricardo.ch/de/a/{tail}/",
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
    return articles


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


def article_needs_enrichment(article: dict[str, Any]) -> bool:
    if not article.get("image"):
        return True
    if article.get("buy_now_price") in (None, "") and article.get("bid_price") in (
        None,
        "",
    ):
        return True
    if not str(article.get("seller_name") or "").strip():
        return True
    title = str(article.get("title") or "")
    if title and title == title.lower() and len(title) > 20:
        return True
    return False


def extract_articles_from_html(html: str) -> tuple[list[dict[str, Any]], str]:
    articles: list[dict[str, Any]] = []
    source = "links"
    match = _NEXT_DATA_RE.search(html)
    if match:
        try:
            data = json.loads(match.group(1))
            articles = _extract_from_next_data(data)
            if articles:
                with_photo = sum(1 for a in articles if a.get("image"))
                with_price = sum(
                    1
                    for a in articles
                    if a.get("buy_now_price") is not None or a.get("bid_price")
                )
                source = "next_data"
                if with_photo or with_price:
                    source = "next_data_rich"
        except json.JSONDecodeError:
            pass

    if not articles:
        articles = _articles_from_links(html)
        source = "links"

    return _dedupe_articles(articles), source
