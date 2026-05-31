import unittest

from twodehands_parser.filters import VEHICLE_CATEGORY_KEYS, listing_is_auction


class TwoDehandsFiltersTest(unittest.TestCase):
    def test_auction_types(self) -> None:
        self.assertTrue(
            listing_is_auction({"priceInfo": {"priceType": "FAST_BID"}})
        )
        self.assertTrue(
            listing_is_auction({"priceInfo": {"priceType": "MIN_BID"}})
        )
        self.assertFalse(
            listing_is_auction({"priceInfo": {"priceType": "FIXED", "priceCents": 1000}})
        )

    def test_vehicle_keys(self) -> None:
        self.assertIn("autos", VEHICLE_CATEGORY_KEYS)
        self.assertIn("fietsen-en-brommers", VEHICLE_CATEGORY_KEYS)


if __name__ == "__main__":
    unittest.main()
