from __future__ import annotations

from typing import Any

# L1-категории 2dehands: авто, запчасти, велосипеды и броммеры (мопеды).
VEHICLE_CATEGORY_KEYS = frozenset(
    {
        "autos",
        "auto-onderdelen",
        "fietsen-en-brommers",
    }
)

# Типы цены 2dehands API: аукцион / «Bieden» в ленте.
_AUCTION_PRICE_TYPES = frozenset(
    {
        "FAST_BID",
        "MIN_BID",
        "BID",
        "AUCTION",
    }
)


def listing_is_auction(listing: dict[str, Any]) -> bool:
    price_info = listing.get("priceInfo")
    if not isinstance(price_info, dict):
        return False
    price_type = (price_info.get("priceType") or "").upper()
    return price_type in _AUCTION_PRICE_TYPES


def void_item_is_auction_price(item_price: str) -> bool:
    """Запасная проверка уже отформатированной цены."""
    low = (item_price or "").strip().lower()
    return low in ("bieden", "bidding", "gebod")
