import unittest

from settings import parse_proxy_list


class ProxyListTest(unittest.TestCase):
    def test_multiline(self) -> None:
        text = (
            "socks5://u1:p1@host1:1080\n"
            "proxy.lomaproxy.com:48174:user2:pass2\n"
        )
        out = parse_proxy_list(text)
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].startswith("socks5://"))
        self.assertIn("@proxy.lomaproxy.com:48174", out[1])

    def test_comma_separated(self) -> None:
        text = "socks5://a:b@h1:1, socks5://c:d@h2:2"
        self.assertEqual(len(parse_proxy_list(text)), 2)


if __name__ == "__main__":
    unittest.main()
