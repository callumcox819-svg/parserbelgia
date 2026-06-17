from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class ActiveParse:
    user_id: int
    cancel: asyncio.Event = field(default_factory=asyncio.Event)


_active: dict[int, ActiveParse] = {}


def begin(user_id: int) -> ActiveParse:
    """Новый парсинг: отменяет предыдущий прогон того же пользователя."""
    prev = _active.get(user_id)
    if prev is not None:
        prev.cancel.set()
    session = ActiveParse(user_id=user_id)
    _active[user_id] = session
    return session


def end(user_id: int) -> None:
    _active.pop(user_id, None)


def request_cancel(user_id: int) -> bool:
    session = _active.get(user_id)
    if session is None:
        return False
    session.cancel.set()
    return True


def is_cancelled(user_id: int) -> bool:
    session = _active.get(user_id)
    return session.cancel.is_set() if session else False
