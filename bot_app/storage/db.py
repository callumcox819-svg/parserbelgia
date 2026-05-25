from __future__ import annotations

import logging
import os
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


def resolve_db_path() -> Path:
    """Путь к SQLite. На Railway — volume (не стирается при деплое)."""
    explicit = os.environ.get("DATABASE_PATH")
    if explicit:
        return Path(explicit)

    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if mount:
        return Path(mount) / "bot.db"

    on_railway = bool(
        os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("RAILWAY_PROJECT_ID")
        or os.environ.get("RAILWAY_SERVICE_ID")
    )
    if on_railway:
        return Path("/app/data/bot.db")
    return Path("data/bot.db")


DB_PATH = resolve_db_path()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    has_access INTEGER NOT NULL DEFAULT 0,
    platform TEXT NOT NULL DEFAULT '2dehands',
    json_limit INTEGER NOT NULL DEFAULT 50,
    proxy TEXT,
    parse_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_categories (
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL DEFAULT '2dehands',
    category_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, platform, category_key)
);

CREATE TABLE IF NOT EXISTS user_seen_sellers (
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL DEFAULT '2dehands',
    seller_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, platform, seller_id)
);

CREATE TABLE IF NOT EXISTS category_id_cache (
    platform TEXT NOT NULL DEFAULT '2dehands',
    category_key TEXT NOT NULL,
    l1_id INTEGER NOT NULL,
    PRIMARY KEY (platform, category_key)
);
"""


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return {row[1] for row in rows}


async def _migrate_schema(db: aiosqlite.Connection) -> None:
    user_cols = await _table_columns(db, "users")
    if user_cols and "platform" not in user_cols:
        await db.execute(
            "ALTER TABLE users ADD COLUMN platform TEXT NOT NULL DEFAULT '2dehands'"
        )

    cat_cols = await _table_columns(db, "user_categories")
    if cat_cols and "platform" not in cat_cols:
        await db.executescript(
            """
            CREATE TABLE user_categories_new (
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL DEFAULT '2dehands',
                category_key TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, platform, category_key)
            );
            INSERT INTO user_categories_new (user_id, platform, category_key, enabled)
                SELECT user_id, '2dehands', category_key, enabled FROM user_categories;
            DROP TABLE user_categories;
            ALTER TABLE user_categories_new RENAME TO user_categories;
            """
        )

    seen_cols = await _table_columns(db, "user_seen_sellers")
    if seen_cols and "platform" not in seen_cols:
        await db.executescript(
            """
            CREATE TABLE user_seen_sellers_new (
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL DEFAULT '2dehands',
                seller_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, platform, seller_id)
            );
            INSERT INTO user_seen_sellers_new (user_id, platform, seller_id)
                SELECT user_id, '2dehands', seller_id FROM user_seen_sellers;
            DROP TABLE user_seen_sellers;
            ALTER TABLE user_seen_sellers_new RENAME TO user_seen_sellers;
            """
        )

    cache_cols = await _table_columns(db, "category_id_cache")
    if cache_cols and "platform" not in cache_cols:
        await db.executescript(
            """
            CREATE TABLE category_id_cache_new (
                platform TEXT NOT NULL DEFAULT '2dehands',
                category_key TEXT NOT NULL,
                l1_id INTEGER NOT NULL,
                PRIMARY KEY (platform, category_key)
            );
            INSERT INTO category_id_cache_new (platform, category_key, l1_id)
                SELECT '2dehands', category_key, l1_id FROM category_id_cache;
            DROP TABLE category_id_cache;
            ALTER TABLE category_id_cache_new RENAME TO category_id_cache;
            """
        )


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await _migrate_schema(db)
        await db.commit()
    logger.info("Database: %s", DB_PATH.resolve())
