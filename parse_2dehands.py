#!/usr/bin/env python3
"""CLI: парсер 2dehands.be → JSON (формат void-parser)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from settings import load_settings
from twodehands_parser import parse_2dehands_sync

SETTINGS = load_settings()


def _default_output() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d %H %M %S")
    return Path.cwd() / "output" / f"2dehands-parser-result {stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сбор объявлений 2dehands.be в JSON (формат void-parser)."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="URL страницы 2dehands")
    src.add_argument("--api-url", help="Прямой URL lrp/api/search")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    limit = args.limit if args.limit is not None else SETTINGS["default_limit"]

    proxy = args.proxy if args.proxy is not None else SETTINGS["proxy"]
    if proxy is None:
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

    source = args.api_url or args.url
    try:
        result = parse_2dehands_sync(
            source,
            limit=limit,
            max_pages=args.max_pages,
            proxy=proxy,
        )
    except Exception as exc:
        logging.error("%s", exc)
        return 1

    out_path = args.output or _default_output()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(result['items'])} items -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
