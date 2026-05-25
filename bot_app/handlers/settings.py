from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot_app.keyboards import (
    CB_CAT_ALL_OFF,
    CB_CAT_ALL_ON,
    CB_CAT_TOGGLE,
    CB_SET_BACK,
    CB_SET_CATEGORIES,
    CB_SET_LIMIT,
    CB_SET_PROXY,
    cancel_keyboard,
    categories_keyboard,
    main_menu_keyboard,
    settings_menu_keyboard,
)
from bot_app.states import SettingsForm
from bot_app.storage import repo
from settings import normalize_proxy

router = Router(name="settings")


async def _settings_summary(user_id: int) -> str:
    s = await repo.get_user_settings(user_id)
    keys = await repo.get_enabled_category_keys(user_id)
    proxy = s.get("proxy") or "не задан (глобальный с сервера)"
    return (
        "⚙️ **Настройки**\n\n"
        f"🔢 Лимит JSON: **{s['json_limit']}**\n"
        f"📂 Категорий включено: **{len(keys)}**\n"
        f"🌐 Прокси: `{proxy}`"
    )


@router.callback_query(F.data == "main:settings")
async def open_settings(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.message.edit_text(
        await _settings_summary(uid),
        reply_markup=settings_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


async def _categories_text(uid: int) -> str:
    n = await repo.count_enabled_categories(uid)
    total = len(await repo.get_category_states(uid))
    return (
        f"📂 Категории (вкл/выкл). Включено: **{n}** из {total}\n\n"
        "Или «Выбрать все» / «Снять все»."
    )


@router.callback_query(F.data == CB_SET_CATEGORIES)
async def open_categories(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.ensure_user(uid, callback.from_user.username)
    states = await repo.get_category_states(uid)
    await callback.message.edit_text(
        await _categories_text(uid),
        reply_markup=categories_keyboard(states),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_CAT_ALL_ON)
async def categories_all_on(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.set_all_categories(uid, True)
    states = await repo.get_category_states(uid)
    await callback.message.edit_text(
        await _categories_text(uid),
        reply_markup=categories_keyboard(states),
        parse_mode="Markdown",
    )
    await callback.answer("Все категории включены")


@router.callback_query(F.data == CB_CAT_ALL_OFF)
async def categories_all_off(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.set_all_categories(uid, False)
    states = await repo.get_category_states(uid)
    await callback.message.edit_text(
        await _categories_text(uid),
        reply_markup=categories_keyboard(states),
        parse_mode="Markdown",
    )
    await callback.answer("Все категории выключены")


@router.callback_query(F.data.startswith(CB_CAT_TOGGLE))
async def toggle_category(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    key = callback.data.removeprefix(CB_CAT_TOGGLE)
    await repo.toggle_category(uid, key)
    states = await repo.get_category_states(uid)
    await callback.message.edit_text(
        await _categories_text(uid),
        reply_markup=categories_keyboard(states),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_SET_LIMIT)
async def ask_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.waiting_json_limit)
    await callback.message.answer(
        "🔢 Введите число объявлений для JSON (1–500).\n"
        "Если объявлений меньше — получите сколько найдено.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(SettingsForm.waiting_json_limit, F.text)
async def save_limit(message: Message, state: FSMContext, is_admin_user: bool) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "Отменено.",
            reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        )
        return
    try:
        n = int((message.text or "").strip())
        if not 1 <= n <= 500:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число от 1 до 500.")
        return
    await repo.set_json_limit(message.from_user.id, n)
    await state.clear()
    await message.answer(
        f"✅ Лимит сохранён: {n}",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
    )


@router.callback_query(F.data == CB_SET_PROXY)
async def ask_proxy(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.waiting_proxy)
    await callback.message.answer(
        "🌐 Прокси (BE/EU):\n"
        "SOCKS5: `socks5://login:pass@host:port`\n"
        "HTTP: `http://login:pass@host:port`\n\n"
        "Для SOCKS5 обязательно префикс socks5://\n"
        "Сброс: `0` или `off`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(SettingsForm.waiting_proxy, F.text)
async def save_proxy(message: Message, state: FSMContext, is_admin_user: bool) -> None:
    text = (message.text or "").strip()
    if text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "Отменено.",
            reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        )
        return
    if text.lower() in ("0", "off", "нет", "none", "-"):
        await repo.set_proxy(message.from_user.id, None)
        await state.clear()
        await message.answer(
            "✅ Прокси сброшен.",
            reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        )
        return
    proxy = normalize_proxy(text)
    if not proxy:
        await message.answer("Некорректный прокси.")
        return
    await repo.set_proxy(message.from_user.id, proxy)
    await state.clear()
    await message.answer(
        "✅ Прокси сохранён.",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
    )
