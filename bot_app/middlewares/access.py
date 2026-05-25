from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot_app.app_config import is_admin
from bot_app.storage import repo


class AccessMiddleware(BaseMiddleware):
    """Блокирует всё, кроме /start, пока нет доступа (админ всегда проходит)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if is_admin(user.id):
            data["has_access"] = True
            data["is_admin_user"] = True
            return await handler(event, data)

        has_access = await repo.user_has_access(user.id)
        data["has_access"] = has_access
        data["is_admin_user"] = False

        if has_access:
            return await handler(event, data)

        if isinstance(event, Message):
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
            await event.answer(
                "⛔ Бот закрыт. Доступ только после одобрения администратора."
            )
            return None

        if isinstance(event, CallbackQuery):
            if event.data and event.data == "noop":
                await event.answer()
                return None
            await event.answer("⛔ Нет доступа.", show_alert=True)
            return None

        return None
