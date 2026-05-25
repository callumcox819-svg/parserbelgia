from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot_app.config import is_admin
from bot_app.keyboards import (
    CB_ADMIN_BACK,
    CB_ADMIN_GRANT,
    CB_ADMIN_REVOKE,
    CB_ADMIN_STATS,
    admin_menu_keyboard,
    cancel_keyboard,
    main_menu_keyboard,
)
from bot_app.states import AdminForm
from bot_app.storage import repo

router = Router(name="admin")

ADMIN_TEXT = "🛠 **Админ панель**"


async def show_admin_panel(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        ADMIN_TEXT,
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "main:admin")
async def open_admin(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для администратора.", show_alert=True)
        return
    await show_admin_panel(callback)


@router.callback_query(F.data == CB_ADMIN_BACK)
async def admin_back(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "👋 Главное меню",
        reply_markup=main_menu_keyboard(is_admin=True),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_ADMIN_STATS)
async def admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    st = await repo.get_stats()
    text = (
        "📊 **Статистика**\n\n"
        f"👥 Всего пользователей: **{st['total_users']}**\n"
        f"✅ С доступом: **{st['with_access']}**\n"
        f"⛔ Без доступа: **{st['without_access']}**\n"
        f"📥 Всего парсингов: **{st['total_parses']}**"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_ADMIN_GRANT)
async def admin_grant_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    await state.set_state(AdminForm.waiting_grant_user)
    await callback.message.answer(
        "✅ Отправьте **ID пользователя** (число) или **перешлите** его сообщение.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == CB_ADMIN_REVOKE)
async def admin_revoke_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    await state.set_state(AdminForm.waiting_revoke_user)
    await callback.message.answer(
        "🚫 Отправьте **ID пользователя** или **перешлите** сообщение.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


def _extract_user_id(message: Message) -> int | None:
    origin = message.forward_origin
    if origin is not None:
        sender = getattr(origin, "sender_user", None)
        if sender is not None:
            return sender.id
    if message.text:
        m = re.search(r"\d{5,}", message.text)
        if m:
            return int(m.group())
    return None


@router.message(AdminForm.waiting_grant_user)
async def admin_grant_finish(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu_keyboard(is_admin=True))
        return
    uid = _extract_user_id(message)
    if uid is None:
        await message.answer("Не удалось определить ID. Отправьте число или перешлите сообщение.")
        return
    await repo.ensure_user(uid, None)
    await repo.set_access(uid, True)
    await state.clear()
    await message.answer(
        f"✅ Доступ выдан пользователю `{uid}`.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin=True),
    )


@router.message(AdminForm.waiting_revoke_user)
async def admin_revoke_finish(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu_keyboard(is_admin=True))
        return
    uid = _extract_user_id(message)
    if uid is None:
        await message.answer("Не удалось определить ID.")
        return
    if is_admin(uid):
        await message.answer("Нельзя забрать доступ у администратора.")
        return
    await repo.set_access(uid, False)
    await state.clear()
    await message.answer(
        f"🚫 Доступ снят с пользователя `{uid}`.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin=True),
    )
