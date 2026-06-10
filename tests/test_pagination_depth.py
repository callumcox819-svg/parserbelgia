import unittest

from twodehands_parser.category_parse import _sort_for_run


class PaginationDepthTest(unittest.TestCase):
    def test_sort_prefers_date_for_new_listings(self) -> None:
        sb, so = _sort_for_run(0, 0)
        self.assertEqual(sb, "DATE")
        self.assertEqual(so, "DECREASING")

    def test_sort_rotates_occasionally(self) -> None:
        sb, _ = _sort_for_run(3, 0)
        self.assertEqual(sb, "SORT_INDEX")


if __name__ == "__main__":
    unittest.main()
