from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

BASE = "https://www.2dehands.be"
API_SEARCH = f"{BASE}/lrp/api/search"

_HASH_PAIR = re.compile(r"^([^:]+):(.+)$")
_L1_FROM_HTML = re.compile(
    r'"l1Category"\s*:\s*\{[^}]*"key"\s*:\s*"(?P<key>[^"]+)"[^}]*"id"\s*:\s*(?P<id>\d+)',
    re.DOTALL,
)


def _parse_hash_filters(fragment: str) -> list[tuple[str, str]]:
    if not fragment:
        return []
    pairs: list[tuple[str, str]] = []
    for part in fragment.split("|"):
        part = part.strip()
        if not part:
            continue
        m = _HASH_PAIR.match(part)
        if m:
            pairs.append((m.group(1), m.group(2)))
    return pairs


def _query_from_path(path: str) -> str | None:
    m = re.match(r"^/q/([^/]+)/?", path)
    if not m:
        return None
    raw = unquote(m.group(1).replace("+", " "))
    return raw.strip() or None


def _category_slug_from_path(path: str) -> str | None:
    m = re.match(r"^/l/([^/]+)/?", path)
    if m:
        return m.group(1)
    return None


def build_api_params_from_browser_url(url: str) -> dict[str, str | list[str]]:
    parsed = urlparse(url)
    if "2dehands.be" not in parsed.netloc and "2ememain.be" not in parsed.netloc:
        raise ValueError(f"Не URL 2dehands: {url}")

    if "/lrp/api/search" in parsed.path:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        flat: dict[str, str | list[str]] = {}
        for k, v in qs.items():
            flat[k] = v if len(v) > 1 else v[0]
        return flat

    params: dict[str, str | list[str]] = {
        "viewOptions": "list-view",
        "sortBy": "SORT_INDEX",
        "sortOrder": "DECREASING",
    }

    fragment = parsed.fragment.lstrip("#")
    for key, value in _parse_hash_filters(fragment):
        if key in ("sortBy", "sortOrder"):
            params[key] = value
        else:
            params.setdefault("attributesByKey[]", [])
            if not isinstance(params["attributesByKey[]"], list):
                params["attributesByKey[]"] = [params["attributesByKey[]"]]
            params["attributesByKey[]"].append(f"{key}:{value}")

    q_from_path = _query_from_path(parsed.path)
    if q_from_path is not None:
        params["query"] = q_from_path
        params.setdefault("searchInTitleAndDescription", "true")
        if "attributesByKey[]" not in params:
            params["attributesByKey[]"] = ["Language:all-languages"]
    else:
        slug = _category_slug_from_path(parsed.path)
        if slug:
            params["_category_slug"] = slug
        elif parsed.path in ("", "/"):
            params["query"] = "*"
        else:
            params["query"] = "*"

    qs = parse_qs(parsed.query, keep_blank_values=True)
    for k, v in qs.items():
        if k.startswith("attributesByKey"):
            params.setdefault("attributesByKey[]", [])
            if not isinstance(params["attributesByKey[]"], list):
                params["attributesByKey[]"] = [params["attributesByKey[]"]]
            for item in v:
                params["attributesByKey[]"].append(item)
        elif k in ("limit", "offset", "sortBy", "sortOrder", "query", "l1CategoryId"):
            params[k] = v[-1]

    return params


def api_url_from_params(
    params: dict[str, str | list[str]],
    *,
    limit: int,
    offset: int,
) -> str:
    out: dict[str, str | list[str]] = dict(params)
    out["limit"] = str(limit)
    out["offset"] = str(offset)
    out.pop("_category_slug", None)

    pairs: list[tuple[str, str]] = []
    for key, value in out.items():
        if isinstance(value, list):
            for item in value:
                pairs.append((key, item))
        else:
            pairs.append((key, str(value)))

    query = urlencode(pairs, quote_via=quote)
    return f"{API_SEARCH}?{query}"


def extract_l1_category_id(html: str, slug: str) -> int | None:
    for m in _L1_FROM_HTML.finditer(html):
        if m.group("key") == slug:
            return int(m.group("id"))
    alt = re.search(rf'"/l/{re.escape(slug)}/"[^>]*>.*?"id"\s*:\s*(\d+)', html, re.DOTALL)
    if alt:
        return int(alt.group(1))
    m = re.search(rf'"key"\s*:\s*"{re.escape(slug)}"[^}}]*"id"\s*:\s*(\d+)', html)
    if m:
        return int(m.group(1))
    return None


def normalize_browser_url(url: str) -> str:
    if url.startswith("/"):
        return BASE + url
    if not url.startswith("http"):
        return BASE + "/" + url.lstrip("/")
    return url
