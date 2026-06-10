import unittest

from bot_app.services.parser_runner import _item_ids_from_void_items


class ItemMemoryTest(unittest.TestCase):
    def test_2dehands_item_link(self) -> None:
        items = [{"item_link": "https://link.2dehands.be/m1234567890"}]
        self.assertEqual(_item_ids_from_void_items(items), {"m1234567890"})

    def test_ricardo_item_link(self) -> None:
        items = [{"item_link": "https://www.ricardo.ch/de/a/1300675318/"}]
        self.assertEqual(_item_ids_from_void_items(items), {"1300675318"})


if __name__ == "__main__":
    unittest.main()
