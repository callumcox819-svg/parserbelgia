import json
import unittest

from ricardo_parser.article_detail import parse_article_page_html
from ricardo_parser.html_parse import article_needs_enrichment, extract_articles_from_html
from ricardo_parser.void_format import article_to_void_item


class RicardoParserTest(unittest.TestCase):
    def test_category_articles_from_next_data(self) -> None:
        cards = [
            {
                "id": "1300675318",
                "title": "Thonet Freischwinger",
                "has_buy_now": True,
                "image": "https://img.ricardostatic.ch/images/e48/t_265x200/thonet",
                "buy_now_price": 500,
                "creation_date": "2025-10-13T10:12:00Z",
                "seller_id": "407457441",
            }
        ]
        payload = {"props": {"pageProps": {"articles": cards}}}
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        arts = extract_articles_from_html(html)
        self.assertEqual(len(arts), 1)
        self.assertEqual(arts[0]["buy_now_price"], 500)
        self.assertIn("t_1000x750", arts[0]["image"])

    def test_article_page_detail(self) -> None:
        article = {
            "id": "1300675318",
            "title": "Thonet Freischwinger mit Netz",
            "buy_now_price": 500,
            "creation_date": "2025-10-13T10:12:00Z",
            "images": [
                {"url": "https://img.ricardostatic.ch/images/e48/t_265x200/x"}
            ],
            "seller": {
                "id": "407457441",
                "nickname": "Fabdc",
                "article_count": 3,
                "purchases_count": 8,
                "sales_count": 94,
                "score": 1,
                "identification": {
                    "postal_address": {"verified_at": "2017-11-28T00:00:00Z"}
                },
            },
        }
        payload = {"props": {"pageProps": {"article": article}}}
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        det = parse_article_page_html(html, article_id="1300675318")
        self.assertIsNotNone(det)
        assert det is not None
        self.assertEqual(det["seller_name"], "Fabdc")
        self.assertEqual(det["ads_number_bought"], 8)
        item = article_to_void_item(det)
        self.assertEqual(item["item_price"], "500 .-")
        self.assertEqual(item["item_link"], "https://www.ricardo.ch/de/a/1300675318/")
        self.assertEqual(item["phone"], "")

    def test_link_stub_needs_enrichment(self) -> None:
        html = '<a href="/de/a/foo-bar-1319274576/">x</a>'
        arts = extract_articles_from_html(html)
        self.assertEqual(arts[0]["id"], "1319274576")
        self.assertTrue(article_needs_enrichment(arts[0]))


if __name__ == "__main__":
    unittest.main()
