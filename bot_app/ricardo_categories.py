"""Категории Ricardo.ch — slug в URL /de/c/{slug}/ (проверенные ID)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RicardoCategory:
    key: str
    title: str
    slug: str


RICARDO_CATEGORIES: list[RicardoCategory] = [
    RicardoCategory("auto", "🚗 Autos", "autos-69957"),
    RicardoCategory("auto-teile", "🔧 Auto-Ersatzteile", "alle-auto-ersatzteile-74897"),
    RicardoCategory("moto", "🏍 Mofas & Motorrad", "mofas-69983"),
    RicardoCategory("pc", "💻 PCs & Computer", "pcs-39289"),
    RicardoCategory("handy", "📱 Handys & Smartphones", "handys-smartphones-49329"),
    RicardoCategory("notebook", "💻 Notebooks", "notebooks-und-zubehoer-39272"),
    RicardoCategory("foto", "📷 Kameras", "kamera-82026"),
    RicardoCategory("games", "🎮 Games", "games-82019"),
    RicardoCategory("konsolen", "🕹 Konsolen", "konsolen-82018"),
    RicardoCategory("tv", "📺 Fernseher", "fernseher-42209"),
    RicardoCategory("audio", "🎧 Lautsprecher", "lautsprecher-38525"),
    RicardoCategory("mode-d", "👗 Damenmode", "damenmode-40800"),
    RicardoCategory("mode-h", "👔 Herrenmode", "herrenmode-40801"),
    RicardoCategory("jacken-h", "🧥 Herren Jacken", "herren-jacken-41016"),
    RicardoCategory("schuhe-d", "👠 Damenschuhe", "damenschuhe-40943"),
    RicardoCategory("schuhe-h", "👞 Herrenschuhe", "herrenschuhe-40822"),
    RicardoCategory("uhren", "⌚ Uhren", "uhren-81990"),
    RicardoCategory("moebel", "🛋 Haushalt & Wohnen", "haushalt-wohnen-40295"),
    RicardoCategory("garten", "🌿 Gartendeko", "gartendekoration-39862"),
    RicardoCategory("baby", "👶 Babykleidung", "babykleidung-babymode-76519"),
    RicardoCategory("sport", "🚲 Velo & Fahrrad", "velo-fahrrad-41950"),
    RicardoCategory("spielzeug", "🧸 Spielzeug", "spielzeug-82075"),
    RicardoCategory("buecher", "📚 Bücher", "kunst-und-kultur-buecher-38979"),
]

RICARDO_CATEGORY_BY_KEY = {c.key: c for c in RICARDO_CATEGORIES}
