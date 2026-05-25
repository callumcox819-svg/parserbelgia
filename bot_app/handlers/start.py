from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, CallbackQuery, Message

from bot_app.config import is_admin
from bot_app.keyboards import CB_SET_BACK, main_menu_keyboard
from bot_app.storage import repo

router = Router(name="start")

NO_ACCESS_TEXT = (
    "👋 Добро пожаловать!\n\n"
    "Бот закрыт. Ожидайте, пока администратор выдаст доступ.\n"
    "Ваш ID: `{user_id}`"
)

ACCESS_TEXT = (
    "👋 Главное меню\n\n"
    "▶️ **Запустить парсер** — сбор JSON по вашим категориям\n"
    "⚙️ **Настройки** — категории, лимит, прокси\n"
    "Продавцы не повторяются для вас лично (чёрный список)."
)


async def setup_bot_commands(bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, has_access: bool, is_admin_user: bool) -> None:
    uid = message.from_user.id
    await repo.ensure_user(uid, message.from_user.username)

    if is_admin(uid):
        await repo.set_access(uid, True)
        has_access = True

    if not has_access:
        await message.answer(
            NO_ACCESS_TEXT.format(user_id=uid),
            parse_mode="Markdown",
        )
        return

    await message.answer(
        ACCESS_TEXT,
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == CB_SET_BACK)
async def back_to_main(callback: CallbackQuery, is_admin_user: bool) -> None:
    await callback.message.edit_text(
        ACCESS_TEXT,
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        parse_mode="Markdown",
    )
    await callback.answer()
