"""Категории Ländleanzeiger.at (Австрия)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LaendleCategory:
    key: str
    title: str
    slug: str


LAENDLE_CATEGORIES: list[LaendleCategory] = [
    LaendleCategory("elektronik", "📱 Elektronik", "elektronik"),
    LaendleCategory("haus-familie", "🏠 Haus & Familie", "haus-familie"),
    LaendleCategory("hobby-freizeit", "🎯 Hobby & Freizeit", "hobby-freizeit"),
    LaendleCategory("sport-wellness", "⚽ Sport & Wellness", "sport-wellness"),
    LaendleCategory("auto-motorrad", "🚗 Auto & Motorrad", "auto-motorrad"),
    LaendleCategory("immobilienmarkt", "🏘 Immobilien", "immobilienmarkt"),
    LaendleCategory("jobs-business", "💼 Jobs & Business", "jobs-business"),
    LaendleCategory("tiermarkt", "🐾 Tiermarkt", "tiermarkt"),
    LaendleCategory("landwirtschaft", "🌾 Landwirtschaft", "landwirtschaft"),
    LaendleCategory("alles-moegliche", "📦 Alles Mögliche", "alles-moegliche"),
]

LAENDLE_CATEGORY_BY_KEY = {c.key: c for c in LAENDLE_CATEGORIES}
