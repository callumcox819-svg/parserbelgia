from __future__ import annotations

import os

from settings import load_settings

SETTINGS = load_settings()


def _parse_admin_ids() -> set[int]:
    raw = os.environ.get("ADMIN_IDS") or os.environ.get("ADMIN_ID") or ""
    if not raw and SETTINGS.get("admin_ids"):
        raw = str(SETTINGS["admin_ids"])
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = _parse_admin_ids()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
