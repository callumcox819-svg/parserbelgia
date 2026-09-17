from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from .http_client import BASE

_AD_LINK_RE = re.compile(
    r'href="((?:https://www\.laendleanzeiger\.at)?/anzeigen/[^"]+/anzeige/[^"]+\.html)"',
    re.I,
)
_USER_ID_RE = re.compile(r"userEncryptedId=(\d+)|/user-profile-(\d+)", re.I)
_NAME_RE = re.compile(
    r'<h2[^>]*class="[^"]*user-profile-name[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>',
    re.I | re.S,
)
_DESC_RE = re.compile(
    r'<div[^>]*class="[^"]*(?:ad-description|description|detail-text)[^"]*"[^>]*>(.*?)</div>',
    re.I | re.S,
)
_LOC_RE = re.compile(
    r'<[^>]+class="[^"]*(?:location|ad-location|city)[^"]*"[^>]*>([^<]{2,80})',
    re.I,
)
_DATE_RE = re.compile(
    r'<[^>]+class="[^"]*(?:date|ad-date|created)[^"]*"[^>]*>([^<]{2,60})',
    re.I,
)


def _strip(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text).strip())


def extract_listing_urls(category_html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _AD_LINK_RE.finditer(category_html):
        href = match.group(1)
        full = urljoin(BASE + "/", href)
        if full in seen:
            continue
        seen.add(full)
        urls.append(full)
    return urls


def max_page_from_html(category_html: str) -> int:
    pages = [int(x) for x in re.findall(r"[?&]pag=(\d+)", category_html)]
    return max(pages) if pages else 1


def _parse_ld_json(html: str) -> dict[str, Any] | None:
    match = re.search(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    )
    if not match:
        return None
    raw = unescape(match.group(1).strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _first_image(ld: dict[str, Any] | None) -> str:
    if not ld:
        return ""
    images = ld.get("image")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return str(first.get("contentUrl") or first.get("url") or "")
        return str(first)
    if isinstance(images, str):
        return images
    if isinstance(images, dict):
        return str(images.get("contentUrl") or images.get("url") or "")
    return ""


def _price_from_ld(ld: dict[str, Any] | None) -> str:
    if not ld:
        return ""
    offers = ld.get("offers") or {}
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if not isinstance(offers, dict):
        return ""
    price = offers.get("price")
    currency = offers.get("priceCurrency") or "EUR"
    if price is None or price == "":
        return ""
    try:
        amount = float(price)
        if amount == int(amount):
            return f"€\u00a0{int(amount)}"
        return f"€\u00a0{amount:.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return f"{price} {currency}".strip()


def _seller_from_ld(ld: dict[str, Any] | None) -> str:
    if not ld:
        return ""
    offers = ld.get("offers") or {}
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if not isinstance(offers, dict):
        return ""
    seller = offers.get("seller") or {}
    if isinstance(seller, dict):
        return str(seller.get("name") or "").strip()
    return ""


def parse_detail_html(html: str, url: str) -> dict[str, Any] | None:
    """Полная карточка. None — нет продавца / битая страница."""
    ld = _parse_ld_json(html)
    title = ""
    if ld:
        title = str(ld.get("name") or "").strip()
    if not title:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        title = _strip(m.group(1)) if m else ""

    seller_name = _seller_from_ld(ld)
    if not seller_name:
        m = _NAME_RE.search(html)
        if m:
            seller_name = unescape(m.group(1).strip())

    seller_id = None
    m = _USER_ID_RE.search(html)
    if m:
        seller_id = int(m.group(1) or m.group(2))

    # Без данных продавца — пропускаем
    if not seller_id and not seller_name:
        return None

    desc = ""
    if ld and ld.get("description"):
        desc = _strip(str(ld.get("description")))
    if not desc:
        m = _DESC_RE.search(html)
        if m:
            desc = _strip(m.group(1))

    location = ""
    m = _LOC_RE.search(html)
    if m:
        location = unescape(m.group(1).strip())

    created = ""
    m = _DATE_RE.search(html)
    if m:
        created = unescape(m.group(1).strip())

    ad_id = ""
    m = re.search(r"/anzeige/[^/]+/([a-z0-9]+)\.html", url, re.I)
    if m:
        ad_id = m.group(1)
    if not ad_id:
        m = re.search(r'data-id="([^"]+)"', html)
        if m:
            ad_id = m.group(1)

    person_link = ""
    if seller_id:
        person_link = f"{BASE}/user-profile-{seller_id}"

    return {
        "id": ad_id,
        "url": url,
        "title": title,
        "description": desc,
        "price": _price_from_ld(ld),
        "photo": _first_image(ld),
        "location": location,
        "created_date": created,
        "seller_id": seller_id,
        "seller_name": seller_name,
        "person_link": person_link,
    }
