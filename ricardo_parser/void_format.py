from __future__ import annotations

from typing import Any


def _format_chf_price(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if amount == int(amount):
        return f"CHF {int(amount):,}".replace(",", "'")
    return f"CHF {amount:,.2f}".replace(",", "'")


def article_to_void_item(article: dict[str, Any]) -> dict[str, Any]:
    article_id = str(article.get("id") or "")
    href = article.get("href") or ""
    if not href and article_id:
        href = f"https://www.ricardo.ch/de/a/-{article_id}/"

    seller_id = str(article.get("seller_id") or "").strip()
    person_link = ""
    if seller_id.isdigit():
        person_link = f"https://www.ricardo.ch/de/u/{seller_id}/"

    price = _format_chf_price(article.get("buy_now_price"))
    if not price:
        price = _format_chf_price(article.get("bid_price"))
    if not price and article.get("bids_count"):
        price = f"Gebote: {article.get('bids_count')}"

    return {
        "item_title": article.get("title") or "",
        "item_photo": article.get("image") or "",
        "ads_number": None,
        "parser_views": 0,
        "ads_number_bought": None,
        "ads_number_sold": None,
        "gender": "",
        "email": "",
        "person_reg_date": "",
        "item_price": price,
        "views": None,
        "rating": None,
        "created_date": article.get("creation_date") or "",
        "created_real_date": "",
        "phone": "<code></code>",
        "item_desc": article.get("description") or "",
        "location": article.get("location") or "",
        "item_link": href,
        "person_link": person_link,
        "item_person_name": article.get("seller_name") or "",
    }
