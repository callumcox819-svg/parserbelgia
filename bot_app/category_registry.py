from __future__ import annotations

from dataclasses import dataclass

from bot_app.categories import L1_CATEGORIES
from bot_app.platforms import PLATFORM_2DEHANDS, PLATFORM_RICARDO
from bot_app.ricardo_categories import RICARDO_CATEGORIES


@dataclass(frozen=True)
class BotCategory:
    key: str
    title: str
    platform: str
    l1_id: int | None = None
    ricardo_slug: str | None = None


def categories_for_platform(platform: str) -> list[BotCategory]:
    if platform == PLATFORM_RICARDO:
        return [
            BotCategory(
                key=c.key,
                title=c.title,
                platform=PLATFORM_RICARDO,
                ricardo_slug=c.slug,
            )
            for c in RICARDO_CATEGORIES
        ]
    return [
        BotCategory(
            key=c.key,
            title=c.title,
            platform=PLATFORM_2DEHANDS,
            l1_id=c.l1_id,
        )
        for c in L1_CATEGORIES
    ]


def category_by_key(platform: str, key: str) -> BotCategory | None:
    for cat in categories_for_platform(platform):
        if cat.key == key:
            return cat
    return None
