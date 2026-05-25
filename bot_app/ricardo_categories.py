"""Категории Ricardo.ch — slug в URL /de/c/{slug}/."""

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
    RicardoCategory("moto", "🏍 Motorrad", "motorrad-69958"),
    RicardoCategory("computer", "💻 Computer", "computer-netzwerk-4130"),
    RicardoCategory("handy", "📱 Handys", "handys-telefon-4136"),
    RicardoCategory("foto", "📷 Foto & Optik", "foto-optik-4142"),
    RicardoCategory("games", "🎮 Games", "games-konsolen-4148"),
    RicardoCategory("tv", "📺 TV & Video", "tv-video-4154"),
    RicardoCategory("audio", "🎧 Audio & HiFi", "audio-hifi-4160"),
    RicardoCategory("mode-d", "👗 Damenmode", "damenmode-40800"),
    RicardoCategory("mode-h", "👔 Herrenmode", "herrenmode-40801"),
    RicardoCategory("jacken-h", "🧥 Herren Jacken", "herren-jacken-41016"),
    RicardoCategory("schuhe-d", "👠 Damenschuhe", "damenschuhe-40802"),
    RicardoCategory("schuhe-h", "👞 Herrenschuhe", "herrenschuhe-40803"),
    RicardoCategory("uhren", "⌚ Uhren & Schmuck", "uhren-schmuck-4166"),
    RicardoCategory("moebel", "🛋 Möbel", "moebel-wohnen-4172"),
    RicardoCategory("garten", "🌿 Garten", "garten-handwerk-4178"),
    RicardoCategory("baby", "👶 Baby & Kind", "baby-kind-4184"),
    RicardoCategory("sport", "⚽ Sport", "sport-4190"),
    RicardoCategory("buecher", "📚 Bücher", "buecher-comics-4208"),
]

RICARDO_CATEGORY_BY_KEY = {c.key: c for c in RICARDO_CATEGORIES}
