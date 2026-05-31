import unittest

from twodehands_parser.filters import (
    VEHICLE_CATEGORY_KEYS,
    listing_is_auction,
    void_item_is_auction_price,
)
from twodehands_parser.void_format import listing_to_void_item


class TwoDehandsFiltersTest(unittest.TestCase):
    def test_auction_types(self) -> None:
        self.assertTrue(
            listing_is_auction({"priceInfo": {"priceType": "FAST_BID"}})
        )
        self.assertTrue(
            listing_is_auction({"priceInfo": {"priceType": "MIN_BID"}})
        )
        self.assertFalse(
            listing_is_auction(
                {"priceInfo": {"priceType": "FIXED", "priceCents": 1000}}
            )
        )

    def test_void_format_bieden_is_auction(self) -> None:
        item = listing_to_void_item(
            {"priceInfo": {"priceType": "FAST_BID"}, "title": "x"}
        )
        self.assertEqual(item["item_price"], "Bieden")
        self.assertTrue(void_item_is_auction_price(item["item_price"]))

    def test_fixed_price_not_auction(self) -> None:
        item = listing_to_void_item(
            {
                "priceInfo": {"priceType": "FIXED", "priceCents": 15000},
                "title": "x",
            }
        )
        self.assertIn("150", item["item_price"])
        self.assertFalse(void_item_is_auction_price(item["item_price"]))

    def test_vehicle_keys(self) -> None:
        self.assertIn("autos", VEHICLE_CATEGORY_KEYS)
        self.assertIn("fietsen-en-brommers", VEHICLE_CATEGORY_KEYS)


if __name__ == "__main__":
    unittest.main()
