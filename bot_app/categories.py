"""Основные категории 2dehands (L1) — slug для API и кнопок."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    l1_id: int | None = None


L1_CATEGORIES: list[Category] = [
    Category("antiek-en-kunst", "🖼 Antiek en Kunst", 1),
    Category("audio-tv-en-foto", "📷 Audio, Tv en Foto", 31),
    Category("autos", "🚗 Auto's", 91),
    Category("auto-onderdelen", "🔧 Auto-onderdelen", 260),
    Category("fietsen-en-brommers", "🚲 Fietsen en Brommers", 287),
    Category("huis-en-inrichting", "🛋 Huis en Inrichting", 504),
    Category("immo", "🏠 Immo", 1098),
    Category("computers-en-software", "💻 Computers", 322),
    Category("telecommunicatie", "📱 Telecommunicatie", 820),
    Category("speelgoed-en-spellen", "🎮 Speelgoed", 356),
    Category("sport-en-fitness", "⚽ Sport", 376),
    Category("tuin-en-terras", "🌿 Tuin en Terras", 1841),
    Category("dieren-en-toebehoren", "🐾 Dieren", 395),
    Category("diensten-en-vakmensen", "🛠 Diensten", 1099),
    Category("zakelijke-goederen", "📦 Zakelijk", 1085),
    Category("kleding-dames", "👗 Kleding Dames", 621),
    Category("kleding-heren", "👔 Kleding Heren", 1776),
    Category("sieraden-tassen-uiterlijk", "💎 Sieraden", 443),
    Category("kinderen-en-baby", "👶 Kinderen", 565),
    Category("boeken", "📚 Boeken", 201),
]

CATEGORY_BY_KEY = {c.key: c for c in L1_CATEGORIES}
