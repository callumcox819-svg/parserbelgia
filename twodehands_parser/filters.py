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

_AUCTION_PRICE_TYPES = frozenset({"FAST_BID", "MIN_BID"})


def listing_is_auction(listing: dict[str, Any]) -> bool:
    price_info = listing.get("priceInfo")
    if not isinstance(price_info, dict):
        return False
    price_type = (price_info.get("priceType") or "").upper()
    return price_type in _AUCTION_PRICE_TYPES
