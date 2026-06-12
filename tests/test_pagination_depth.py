import unittest

from twodehands_parser.category_parse import (
    _category_rounds_max,
    _fresh_sweeps_max,
    _max_offset_per_cat,
    _max_zero_add_pages,
    _sort_for_run,
)


class PaginationDepthTest(unittest.TestCase):
    def test_sort_always_date_descending(self) -> None:
        sb, so = _sort_for_run(0, 0)
        self.assertEqual((sb, so), ("DATE", "DECREASING"))
        sb2, so2 = _sort_for_run(99, 5)
        self.assertEqual((sb2, so2), ("DATE", "DECREASING"))

    def test_fresh_sweep_defaults(self) -> None:
        self.assertGreaterEqual(_fresh_sweeps_max(), 1)
        self.assertGreaterEqual(_category_rounds_max(), 1)

    def test_tighter_caps_with_huge_memory(self) -> None:
        self.assertGreater(_max_zero_add_pages(0, 500), _max_zero_add_pages(40000, 500))
        self.assertGreater(_max_offset_per_cat(0, 500), _max_offset_per_cat(40000, 500))


if __name__ == "__main__":
    unittest.main()
