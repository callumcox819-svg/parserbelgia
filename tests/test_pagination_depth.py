import unittest

from twodehands_parser.category_parse import (
    _category_rounds_max,
    _fresh_sweeps_max,
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


if __name__ == "__main__":
    unittest.main()
