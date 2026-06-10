"""Основные категории 2dehands (L1) — slug для API, названия на русском в боте."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    l1_id: int | None = None


L1_CATEGORIES: list[Category] = [
    Category("antiek-en-kunst", "🖼 Антиквариат", 1),
    Category("audio-tv-en-foto", "📷 Аудио и фото", 31),
    Category("autos", "🚗 Авто", 91),
    Category("auto-onderdelen", "🔧 Автозапчасти", 260),
    Category("fietsen-en-brommers", "🚲 Вело и мопеды", 287),
    Category("huis-en-inrichting", "🛋 Дом и интерьер", 504),
    Category("immo", "🏠 Недвижимость", 1098),
    Category("computers-en-software", "💻 Компьютеры", 322),
    Category("telecommunicatie", "📱 Телефоны", 820),
    Category("speelgoed-en-spellen", "🎮 Игрушки", 356),
    Category("sport-en-fitness", "⚽ Спорт", 378),
    Category("tuin-en-terras", "🌿 Сад", 1841),
    Category("dieren-en-toebehoren", "🐾 Животные", 395),
    Category("diensten-en-vakmensen", "🛠 Услуги", 1099),
    Category("zakelijke-goederen", "📦 Бизнес", 1085),
    Category("kleding-dames", "👗 Женская одежда", 621),
    Category("kleding-heren", "👔 Мужская одежда", 1776),
    Category("sieraden-tassen-uiterlijk", "💎 Украшения", 443),
    Category("kinderen-en-baby", "👶 Детские", 565),
    Category("boeken", "📚 Книги", 201),
]

CATEGORY_BY_KEY = {c.key: c for c in L1_CATEGORIES}
