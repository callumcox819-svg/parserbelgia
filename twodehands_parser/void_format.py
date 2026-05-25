from __future__ import annotations

from typing import Any


def _normalize_image_url(url: str | None) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return url


def _pick_photo(listing: dict[str, Any]) -> str:
    pictures = listing.get("pictures") or []
    if pictures:
        pic = pictures[0]
        for key in ("extraExtraLargeUrl", "largeUrl", "mediumUrl", "url"):
            val = pic.get(key)
            if val and isinstance(val, str) and "http" in val:
                return _normalize_image_url(val)
    image_urls = listing.get("imageUrls") or []
    if image_urls:
        return _normalize_image_url(str(image_urls[0]))
    return ""


def _format_price(price_info: dict[str, Any] | None) -> str:
    if not price_info:
        return ""
    price_type = (price_info.get("priceType") or "").upper()
    cents = price_info.get("priceCents")
    labels = {
        "FREE": "Gratis",
        "FAST_BID": "Bieden",
        "MIN_BID": "Bieden",
        "SEE_DESCRIPTION": "Zie omschrijving",
        "NOTK": "o.t.k.",
        "ON_REQUEST": "Op aanvraag",
        "RESERVED": "Gereserveerd",
        "EXCHANGE": "Ruilen",
    }
    if price_type in labels:
        return labels[price_type]
    if cents is None:
        return ""
    amount = cents / 100
    whole, frac = divmod(int(round(amount * 100)), 100)
    euros = f"{whole:,}".replace(",", ".")
    return f"€\u00a0{euros},{frac:02d}"


def listing_to_void_item(listing: dict[str, Any]) -> dict[str, Any]:
    seller = listing.get("sellerInformation") or {}
    location = listing.get("location") or {}
    item_id = listing.get("itemId") or ""
    seller_id = seller.get("sellerId")
    person_link = ""
    if seller_id:
        person_link = f"https://www.2dehands.be/u/{seller_id}/"

    return {
        "item_title": listing.get("title") or "",
        "item_photo": _pick_photo(listing),
        "ads_number": None,
        "parser_views": 0,
        "ads_number_bought": None,
        "ads_number_sold": None,
        "gender": "",
        "email": "",
        "person_reg_date": listing.get("_person_reg_date") or "",
        "item_price": _format_price(listing.get("priceInfo")),
        "views": None,
        "rating": listing.get("_rating"),
        "created_date": listing.get("date") or "",
        "created_real_date": listing.get("_created_real_date") or "",
        "phone": "<code></code>",
        "item_desc": listing.get("description") or "",
        "location": location.get("cityName") or location.get("countryName") or "",
        "item_link": f"https://link.2dehands.be/{item_id}" if item_id else "",
        "person_link": person_link,
        "item_person_name": seller.get("sellerName") or "",
    }
