from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

DB_PATH = Path(os.environ.get("DATABASE_PATH", "data/bot.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    has_access INTEGER NOT NULL DEFAULT 0,
    json_limit INTEGER NOT NULL DEFAULT 50,
    proxy TEXT,
    parse_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_categories (
    user_id INTEGER NOT NULL,
    category_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, category_key)
);

CREATE TABLE IF NOT EXISTS user_seen_sellers (
    user_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, seller_id)
);

CREATE TABLE IF NOT EXISTS category_id_cache (
    category_key TEXT PRIMARY KEY,
    l1_id INTEGER NOT NULL
);
"""


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
