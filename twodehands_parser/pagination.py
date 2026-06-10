from __future__ import annotations

PAGE_SIZE = 100
# API отклоняет limit=1..29 (HTTP 400); последние объявления добираем страницей ≥30.
API_MIN_LIMIT = 30


def page_request_limit(remaining: int, *, page_size: int = PAGE_SIZE) -> int:
    if remaining < 1:
        raise ValueError("remaining must be >= 1")
    return min(max(remaining, API_MIN_LIMIT), page_size)
