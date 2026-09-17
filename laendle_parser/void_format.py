from __future__ import annotations

from typing import Any


def listing_to_void_item(listing: dict[str, Any]) -> dict[str, Any]:
    seller_id = listing.get("seller_id")
    return {
        "item_title": listing.get("title") or "",
        "item_photo": listing.get("photo") or "",
        "ads_number": None,
        "parser_views": 0,
        "ads_number_bought": None,
        "ads_number_sold": None,
        "gender": "",
        "email": "",
        "person_reg_date": "",
        "item_price": listing.get("price") or "",
        "views": None,
        "rating": None,
        "created_date": listing.get("created_date") or "",
        "created_real_date": "",
        "phone": "",
        "item_desc": listing.get("description") or "",
        "location": listing.get("location") or "",
        "item_link": listing.get("url") or "",
        "person_link": listing.get("person_link") or "",
        "seller_id": str(seller_id) if seller_id else "",
        "item_person_name": listing.get("seller_name") or "",
    }
