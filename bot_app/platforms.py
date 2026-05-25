"""Площадки, доступные в боте."""

from __future__ import annotations

PLATFORM_2DEHANDS = "2dehands"
PLATFORM_RICARDO = "ricardo"

PLATFORMS: dict[str, dict[str, str]] = {
    PLATFORM_2DEHANDS: {
        "title": "2dehands",
        "label": "🇧🇪 2dehands",
        "proxy_hint": "BE/EU",
    },
    PLATFORM_RICARDO: {
        "title": "Ricardo",
        "label": "🇨🇭 Ricardo",
        "proxy_hint": "CH (Швейцария)",
    },
}

DEFAULT_PLATFORM = PLATFORM_2DEHANDS


def normalize_platform(value: str | None) -> str:
    if not value:
        return DEFAULT_PLATFORM
    key = value.strip().lower()
    if key in PLATFORMS:
        return key
    return DEFAULT_PLATFORM
