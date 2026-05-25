from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot_app.category_registry import categories_for_platform
from bot_app.platforms import PLATFORMS, PLATFORM_2DEHANDS, PLATFORM_RICARDO

CB_MAIN_PARSE = "main:parse"
CB_MAIN_SETTINGS = "main:settings"
CB_MAIN_ADMIN = "main:admin"

CB_SET_PLATFORM = "set:platform"
CB_SET_CATEGORIES = "set:categories"
CB_SET_LIMIT = "set:limit"
CB_SET_PROXY = "set:proxy"
CB_SET_BACK = "set:back"
CB_SET_MENU = "set:menu"

CB_PLATFORM_PREFIX = "plat:"
CB_CAT_TOGGLE = "cat:"
CB_CAT_ALL_ON = "cat:all:on"
CB_CAT_ALL_OFF = "cat:all:off"

CB_ADMIN_GRANT = "admin:grant"
CB_ADMIN_REVOKE = "admin:revoke"
CB_ADMIN_STATS = "admin:stats"
CB_ADMIN_BACK = "admin:back"


def main_menu_keyboard(*, is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="▶️ Запустить парсер", callback_data=CB_MAIN_PARSE)],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data=CB_MAIN_SETTINGS)],
    ]
    if is_admin:
        rows.append(
            [InlineKeyboardButton(text="🛠 Админ панель", callback_data=CB_MAIN_ADMIN)]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏪 Площадка", callback_data=CB_SET_PLATFORM
                )
            ],
            [InlineKeyboardButton(text="📂 Категории", callback_data=CB_SET_CATEGORIES)],
            [
                InlineKeyboardButton(
                    text="🔢 Количество в JSON", callback_data=CB_SET_LIMIT
                )
            ],
            [InlineKeyboardButton(text="🌐 Прокси", callback_data=CB_SET_PROXY)],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=CB_SET_BACK)],
        ]
    )


def platform_keyboard(current: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key in (PLATFORM_2DEHANDS, PLATFORM_RICARDO):
        meta = PLATFORMS[key]
        mark = "✅ " if key == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{meta['label']}",
                    callback_data=f"{CB_PLATFORM_PREFIX}{key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=CB_SET_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def categories_keyboard(states: dict[str, bool], platform: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="✅ Выбрать все", callback_data=CB_CAT_ALL_ON),
            InlineKeyboardButton(text="⬜ Снять все", callback_data=CB_CAT_ALL_OFF),
        ],
    ]
    for cat in categories_for_platform(platform):
        on = states.get(cat.key, False)
        mark = "✅" if on else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {cat.title}",
                    callback_data=f"{CB_CAT_TOGGLE}{cat.key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=CB_SET_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выдать доступ", callback_data=CB_ADMIN_GRANT
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Убрать доступ", callback_data=CB_ADMIN_REVOKE
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика", callback_data=CB_ADMIN_STATS
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=CB_ADMIN_BACK)],
        ]
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
