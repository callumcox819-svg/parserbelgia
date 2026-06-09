from __future__ import annotations

from typing import Any

import aiosqlite

from bot_app.category_registry import categories_for_platform, category_by_key
from bot_app.platforms import DEFAULT_PLATFORM, normalize_platform

from .db import DB_PATH


async def ensure_user(user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                updated_at = datetime('now')
            """,
            (user_id, username),
        )
        for platform in ("2dehands", "ricardo"):
            for cat in categories_for_platform(platform):
                await db.execute(
                    """
                    INSERT OR IGNORE INTO user_categories
                        (user_id, platform, category_key, enabled)
                    VALUES (?, ?, ?, 0)
                    """,
                    (user_id, platform, cat.key),
                )
        await db.commit()


async def user_has_access(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT has_access FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return bool(row and row[0])


async def set_access(user_id: int, granted: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, has_access)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                has_access = excluded.has_access,
                updated_at = datetime('now')
            """,
            (user_id, 1 if granted else 0),
        )
        await db.commit()


async def get_user_settings(user_id: int) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT platform, json_limit, proxy, parse_count,
                   filter_skip_bids, filter_skip_vehicles
            FROM users WHERE user_id = ?
            """,
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return {
            "platform": DEFAULT_PLATFORM,
            "json_limit": 50,
            "proxy": None,
            "parse_count": 0,
            "filter_skip_bids": True,
            "filter_skip_vehicles": True,
        }
    return {
        "platform": normalize_platform(row[0]),
        "json_limit": row[1],
        "proxy": row[2],
        "parse_count": row[3],
        "filter_skip_bids": bool(row[4]) if len(row) > 4 else True,
        "filter_skip_vehicles": bool(row[5]) if len(row) > 5 else True,
    }


async def toggle_filter_skip_bids(user_id: int) -> bool:
    s = await get_user_settings(user_id)
    new_val = not s.get("filter_skip_bids", True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users SET filter_skip_bids = ?, updated_at = datetime('now')
            WHERE user_id = ?
            """,
            (1 if new_val else 0, user_id),
        )
        await db.commit()
    return new_val


async def toggle_filter_skip_vehicles(user_id: int) -> bool:
    s = await get_user_settings(user_id)
    new_val = not s.get("filter_skip_vehicles", True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users SET filter_skip_vehicles = ?, updated_at = datetime('now')
            WHERE user_id = ?
            """,
            (1 if new_val else 0, user_id),
        )
        await db.commit()
    return new_val


async def set_platform(user_id: int, platform: str) -> None:
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users SET platform = ?, updated_at = datetime('now')
            WHERE user_id = ?
            """,
            (platform, user_id),
        )
        await db.commit()


async def set_json_limit(user_id: int, limit: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET json_limit = ?, updated_at = datetime('now') WHERE user_id = ?",
            (limit, user_id),
        )
        await db.commit()


async def set_proxy(user_id: int, proxy: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET proxy = ?, updated_at = datetime('now') WHERE user_id = ?",
            (proxy, user_id),
        )
        await db.commit()


async def get_category_states(user_id: int, platform: str) -> dict[str, bool]:
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT category_key, enabled FROM user_categories
            WHERE user_id = ? AND platform = ?
            """,
            (user_id, platform),
        ) as cur:
            rows = await cur.fetchall()
    return {key: bool(enabled) for key, enabled in rows}


async def set_all_categories(user_id: int, platform: str, enabled: bool) -> None:
    platform = normalize_platform(platform)
    val = 1 if enabled else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE user_categories SET enabled = ?
            WHERE user_id = ? AND platform = ?
            """,
            (val, user_id, platform),
        )
        await db.commit()


async def count_enabled_categories(user_id: int, platform: str) -> int:
    states = await get_category_states(user_id, platform)
    return sum(1 for on in states.values() if on)


async def toggle_category(user_id: int, platform: str, category_key: str) -> bool:
    platform = normalize_platform(platform)
    states = await get_category_states(user_id, platform)
    new_val = not states.get(category_key, False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE user_categories SET enabled = ?
            WHERE user_id = ? AND platform = ? AND category_key = ?
            """,
            (1 if new_val else 0, user_id, platform, category_key),
        )
        await db.commit()
    return new_val


async def get_enabled_category_keys(user_id: int, platform: str) -> list[str]:
    states = await get_category_states(user_id, platform)
    return [k for k, on in states.items() if on]


async def get_seen_seller_ids(user_id: int, platform: str) -> set[int]:
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT seller_id FROM user_seen_sellers
            WHERE user_id = ? AND platform = ?
            """,
            (user_id, platform),
        ) as cur:
            rows = await cur.fetchall()
    return {int(r[0]) for r in rows}


async def clear_seen_sellers(user_id: int, platform: str) -> int:
    """Сброс памяти продавцов. Возвращает число удалённых записей."""
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM user_seen_sellers
            WHERE user_id = ? AND platform = ?
            """,
            (user_id, platform),
        ) as cur:
            n = int((await cur.fetchone())[0])
        await db.execute(
            """
            DELETE FROM user_seen_sellers
            WHERE user_id = ? AND platform = ?
            """,
            (user_id, platform),
        )
        await db.commit()
    return n


async def add_seen_sellers(
    user_id: int, platform: str, seller_ids: set[int]
) -> None:
    if not seller_ids:
        return
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT OR IGNORE INTO user_seen_sellers (user_id, platform, seller_id)
            VALUES (?, ?, ?)
            """,
            [(user_id, platform, sid) for sid in seller_ids],
        )
        await db.commit()


async def cache_category_l1_id(platform: str, category_key: str, l1_id: int) -> None:
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO category_id_cache (platform, category_key, l1_id)
            VALUES (?, ?, ?)
            ON CONFLICT(platform, category_key) DO UPDATE SET l1_id = excluded.l1_id
            """,
            (platform, category_key, l1_id),
        )
        await db.commit()


async def get_cached_l1_id(platform: str, category_key: str) -> int | None:
    platform = normalize_platform(platform)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT l1_id FROM category_id_cache
            WHERE platform = ? AND category_key = ?
            """,
            (platform, category_key),
        ) as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else None


async def increment_parse_count(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users SET parse_count = parse_count + 1, updated_at = datetime('now')
            WHERE user_id = ?
            """,
            (user_id,),
        )
        await db.commit()


async def get_stats() -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE has_access = 1"
        ) as cur:
            with_access = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(parse_count), 0) FROM users") as cur:
            parses = (await cur.fetchone())[0]
    return {
        "total_users": total,
        "with_access": with_access,
        "without_access": total - with_access,
        "total_parses": parses,
    }


def default_l1_id(platform: str, category_key: str) -> int | None:
    cat = category_by_key(platform, category_key)
    return cat.l1_id if cat else None
