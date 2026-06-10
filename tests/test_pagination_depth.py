import unittest

from twodehands_parser.category_parse import _sort_for_run, _start_offset


class PaginationDepthTest(unittest.TestCase):
    def test_start_offset_zero_without_memory(self) -> None:
        self.assertEqual(_start_offset(0, 0, 0), 0)
        self.assertEqual(_start_offset(5, 2, 400), 0)

    def test_start_offset_grows_with_memory(self) -> None:
        off = _start_offset(3, 1, 32389)
        self.assertGreaterEqual(off, 1500)
        self.assertEqual(off % 30, 0)

    def test_start_offset_rotates_by_parse_count(self) -> None:
        a = _start_offset(1, 0, 20000)
        b = _start_offset(9, 0, 20000)
        self.assertNotEqual(a, b)

    def test_sort_rotates(self) -> None:
        a = _sort_for_run(0, 0)
        b = _sort_for_run(1, 0)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
