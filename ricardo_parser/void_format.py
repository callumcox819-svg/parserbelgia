from __future__ import annotations

from typing import Any

from .date_format import format_member_since_ru, format_relative_ru


def _format_void_price(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if amount == int(amount):
        return f"{int(amount)} .-"
    return f"{amount:.2f} .-"


def _void_rating(article: dict[str, Any]) -> int | None:
    rating = article.get("rating")
    if rating is not None:
        try:
            return int(rating)
        except (TypeError, ValueError):
            pass
    score = article.get("seller_score")
    if score is None:
        return None
    try:
        val = float(score)
        return round(val * 100) if val <= 1.0 else round(val)
    except (TypeError, ValueError):
        return None


def article_to_void_item(article: dict[str, Any]) -> dict[str, Any]:
    article_id = str(article.get("id") or "").strip()
    href = article.get("href") or ""
    if article_id:
        href = f"https://www.ricardo.ch/de/a/{article_id}/"

    seller_id = str(article.get("seller_id") or "").strip()
    person_link = ""
    if seller_id.isdigit():
        person_link = f"https://www.ricardo.ch/de/u/{seller_id}/"

    price = _format_void_price(article.get("buy_now_price"))
    if not price:
        price = _format_void_price(article.get("bid_price"))

    created_raw = str(article.get("creation_date") or "").strip()
    created_date = format_relative_ru(created_raw) if created_raw else ""

    reg_raw = str(article.get("person_reg_date") or "").strip()
    person_reg_date = (
        format_member_since_ru(reg_raw) if reg_raw and "T" in reg_raw else reg_raw
    )

    return {
        "item_title": article.get("title") or "",
        "item_photo": article.get("image") or "",
        "ads_number": article.get("ads_number"),
        "parser_views": 0,
        "ads_number_bought": article.get("ads_number_bought"),
        "ads_number_sold": article.get("ads_number_sold"),
        "gender": "",
        "email": "",
        "person_reg_date": person_reg_date,
        "item_price": price,
        "views": None,
        "rating": _void_rating(article),
        "created_date": created_date,
        "created_real_date": created_raw if created_raw else "",
        "phone": "",
        "item_desc": article.get("description") or "",
        "location": article.get("location") or "",
        "item_link": href,
        "person_link": person_link,
        "item_person_name": article.get("seller_name") or "",
    }
