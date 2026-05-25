from __future__ import annotations

import json
import re
from typing import Any

from .html_parse import (
    _NEXT_DATA_RE,
    _first_str,
    _normalize_article,
    _normalize_image_url,
    _pick_price,
)

_ARTICLE_ROOT_KEYS = (
    "article",
    "listing",
    "product",
    "initialArticle",
    "pageData",
    "data",
)


def article_page_url(article_id: str) -> str:
    return f"https://www.ricardo.ch/de/a/{article_id.strip()}/"


def _get_nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _int_field(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        val = data.get(key)
        if val is None or val == "":
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            continue
    stats = data.get("statistics") or data.get("stats")
    if isinstance(stats, dict):
        return _int_field(stats, *keys)
    return None


def _seller_stats(seller: dict[str, Any]) -> dict[str, Any]:
    member_raw = _first_str(
        seller,
        "member_since",
        "memberSince",
        "registered_at",
        "registeredAt",
        "registration_date",
        "registrationDate",
        "user_since",
        "userSince",
        "created_at",
        "createdAt",
    )
    if not member_raw:
        ident = seller.get("identification")
        if isinstance(ident, dict):
            postal = ident.get("postal_address") or ident.get("postalAddress")
            if isinstance(postal, dict):
                member_raw = _first_str(postal, "verified_at", "verifiedAt")

    score_raw = seller.get("score")
    rating: int | None = None
    if score_raw is not None:
        try:
            score = float(score_raw)
            rating = round(score * 100) if score <= 1.0 else round(score)
        except (TypeError, ValueError):
            rating = None

    return {
        "seller_id": _first_str(seller, "id", "sellerId", "seller_id"),
        "seller_name": _first_str(seller, "nickname", "sellerNickname", "name"),
        "ads_number": _int_field(
            seller,
            "article_count",
            "articleCount",
            "open_offers_count",
            "openOffersCount",
        ),
        "ads_number_bought": _int_field(
            seller,
            "purchases_count",
            "purchasesCount",
            "purchase_count",
            "purchaseCount",
            "articles_bought",
            "articlesBought",
            "bought_count",
            "boughtCount",
            "buyer_article_count",
            "buyerArticleCount",
        ),
        "ads_number_sold": _int_field(
            seller,
            "sales_count",
            "salesCount",
            "sale_count",
            "saleCount",
            "articles_sold",
            "articlesSold",
            "sold_count",
            "soldCount",
            "seller_article_count",
            "sellerArticleCount",
        ),
        "rating": rating,
        "person_reg_date": member_raw,
    }


def _find_article_and_seller(page_props: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    for key in _ARTICLE_ROOT_KEYS:
        val = page_props.get(key)
        if isinstance(val, dict):
            seller = val.get("seller")
            if isinstance(seller, dict):
                return val, seller
            outer = page_props.get("seller")
            if isinstance(outer, dict):
                return val, outer
            return val, {}

    seller = page_props.get("seller")
    if isinstance(seller, dict):
        offers = seller.get("open_offers") or seller.get("openOffers") or []
        if isinstance(offers, list) and offers:
            return offers[0], seller

    for val in page_props.values():
        if not isinstance(val, dict):
            continue
        aid = val.get("id") or val.get("articleId") or val.get("article_id")
        if aid is None:
            continue
        if val.get("title") or val.get("buyNowPrice") or val.get("buy_now_price"):
            nested = val.get("seller")
            return val, nested if isinstance(nested, dict) else {}
    return {}, {}


def parse_article_page_html(html: str, *, article_id: str = "") -> dict[str, Any] | None:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    page_props = _get_nested(data, "props", "pageProps")
    if not isinstance(page_props, dict):
        return None

    raw_article, raw_seller = _find_article_and_seller(page_props)
    if not raw_article:
        return None

    article = _normalize_article(raw_article)
    if not article:
        if article_id:
            article = {
                "id": article_id,
                "title": "",
                "href": article_page_url(article_id),
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
        else:
            return None

    if article_id and not article.get("id"):
        article["id"] = article_id

    if raw_seller:
        stats = _seller_stats(raw_seller)
        article.update(stats)

    images = raw_article.get("images") or raw_article.get("imageUrls") or []
    if isinstance(images, list) and images and not article.get("image"):
        first = images[0]
        if isinstance(first, str):
            article["image"] = _normalize_image_url(first)
        elif isinstance(first, dict):
            article["image"] = _normalize_image_url(
                _first_str(first, "url", "src", "image", "href")
            )

    if not article.get("buy_now_price") and not article.get("bid_price"):
        article["buy_now_price"] = _pick_price(raw_article)

    desc = raw_article.get("description")
    if isinstance(desc, str) and desc.strip():
        article["description"] = desc.strip()[:500]

    return article
