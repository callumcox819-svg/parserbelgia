from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot_app.keyboards import (
    CB_CAT_ALL_OFF,
    CB_CAT_ALL_ON,
    CB_CAT_TOGGLE,
    CB_PLATFORM_PREFIX,
    CB_SET_MENU,
    CB_SET_CATEGORIES,
    CB_SET_LIMIT,
    CB_SET_PLATFORM,
    CB_SET_PROXY,
    CB_SET_FILTERS,
    CB_FILTER_SKIP_BIDS,
    CB_FILTER_SKIP_VEHICLES,
    CB_FILTER_CLEAR_SELLERS,
    CB_FILTER_REMEMBER_SELLERS,
    cancel_keyboard,
    filters_keyboard,
    categories_keyboard,
    main_menu_keyboard,
    platform_keyboard,
    settings_menu_keyboard,
)
from bot_app.category_registry import categories_for_platform
from bot_app.platforms import PLATFORMS, normalize_platform
from bot_app.states import SettingsForm
from bot_app.storage import repo
from bot_app.services.proxy_check import proxy_geo_warnings
from settings import normalize_proxy, parse_proxy_list

router = Router(name="settings")


async def _settings_summary(user_id: int) -> str:
    s = await repo.get_user_settings(user_id)
    platform = normalize_platform(s.get("platform"))
    plat = PLATFORMS[platform]
    keys = await repo.get_enabled_category_keys(user_id, platform)
    plist = parse_proxy_list(s.get("proxy"))
    if plist:
        proxy = f"**{len(plist)}** шт. (ротация)"
    else:
        proxy = "**выкл** — прямо с сервера (для 2dehands часто стабильнее)"
    delay_hint = (
        "~0.8 с между запросами"
        if platform == "2dehands"
        else "~1.5 с категории (как void), карточки — опционально"
    )
    filters_line = ""
    if platform == "2dehands":
        bids = "вкл" if s.get("filter_skip_bids", True) else "выкл"
        veh = "вкл" if s.get("filter_skip_vehicles", True) else "выкл"
        filters_line = (
            f"\n🚫 Фильтры: без **Bieden** ({bids}), "
            f"без **авто/броммеров** ({veh})"
        )
    return (
        "⚙️ **Настройки**\n\n"
        f"🏪 Площадка: **{plat['title']}**\n"
        f"🔢 Лимит JSON: **{s['json_limit']}**\n"
        f"📂 Категорий включено: **{len(keys)}**\n"
        f"🌐 Прокси ({plat['proxy_hint']}): {proxy}\n"
        f"⏱ Скорость: {delay_hint}"
        f"{filters_line}"
    )


@router.callback_query(F.data == CB_SET_MENU)
async def back_to_settings_menu(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.message.edit_text(
        await _settings_summary(uid),
        reply_markup=settings_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "main:settings")
async def open_settings(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.message.edit_text(
        await _settings_summary(uid),
        reply_markup=settings_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_SET_PLATFORM)
async def open_platform(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    s = await repo.get_user_settings(uid)
    platform = normalize_platform(s.get("platform"))
    await callback.message.edit_text(
        "🏪 **Площадка**\n\n"
        "2dehands — Бельгия (BE/EU прокси).\n"
        "Ricardo — Швейцария (**CH** residential прокси).",
        reply_markup=platform_keyboard(platform),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_PLATFORM_PREFIX))
async def set_platform(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    platform = normalize_platform(callback.data.removeprefix(CB_PLATFORM_PREFIX))
    await repo.set_platform(uid, platform)
    await callback.message.edit_text(
        await _settings_summary(uid),
        reply_markup=settings_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer(f"Площадка: {PLATFORMS[platform]['title']}")


async def _categories_text(uid: int, platform: str) -> str:
    n = await repo.count_enabled_categories(uid, platform)
    total = len(categories_for_platform(platform))
    plat = PLATFORMS[platform]["title"]
    return (
        f"📂 Категории **{plat}** (вкл/выкл). Включено: **{n}** из {total}\n\n"
        "Или «Выбрать все» / «Снять все»."
    )


@router.callback_query(F.data == CB_SET_CATEGORIES)
async def open_categories(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.ensure_user(uid, callback.from_user.username)
    s = await repo.get_user_settings(uid)
    platform = normalize_platform(s.get("platform"))
    states = await repo.get_category_states(uid, platform)
    await callback.message.edit_text(
        await _categories_text(uid, platform),
        reply_markup=categories_keyboard(states, platform),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_CAT_ALL_ON)
async def categories_all_on(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    platform = normalize_platform((await repo.get_user_settings(uid)).get("platform"))
    await repo.set_all_categories(uid, platform, True)
    states = await repo.get_category_states(uid, platform)
    await callback.message.edit_text(
        await _categories_text(uid, platform),
        reply_markup=categories_keyboard(states, platform),
        parse_mode="Markdown",
    )
    await callback.answer("Все категории включены")


@router.callback_query(F.data == CB_CAT_ALL_OFF)
async def categories_all_off(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    platform = normalize_platform((await repo.get_user_settings(uid)).get("platform"))
    await repo.set_all_categories(uid, platform, False)
    states = await repo.get_category_states(uid, platform)
    await callback.message.edit_text(
        await _categories_text(uid, platform),
        reply_markup=categories_keyboard(states, platform),
        parse_mode="Markdown",
    )
    await callback.answer("Все категории выключены")


@router.callback_query(F.data.startswith(CB_CAT_TOGGLE))
async def toggle_category(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    key = callback.data.removeprefix(CB_CAT_TOGGLE)
    platform = normalize_platform((await repo.get_user_settings(uid)).get("platform"))
    await repo.toggle_category(uid, platform, key)
    states = await repo.get_category_states(uid, platform)
    await callback.message.edit_text(
        await _categories_text(uid, platform),
        reply_markup=categories_keyboard(states, platform),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_SET_FILTERS)
async def open_filters(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    s = await repo.get_user_settings(uid)
    platform = normalize_platform(s.get("platform"))
    text = (
        "🚫 **Фильтры (2dehands)**\n\n"
        "**Без ставок (Bieden)** — пропускать аукционы "
        "(FAST_BID / MIN_BID), только фикс. цена €.\n\n"
        "**Без авто / броммеров** — не парсить категории:\n"
        "🚗 Авто, 🔧 Автозапчасти, 🚲 Вело и мопеды.\n\n"
        "**Не повторять продавцов** — личная память **каждого пользователя**, "
        "не сбрасывается и не обрезается. Только кнопка «Сбросить память».\n\n"
        "Вкл/выкл кнопками ниже."
    )
    if platform != "2dehands":
        text = (
            "Фильтры категорий — только для **2dehands**.\n\n"
            "**Память продавцов** — **личная у каждого пользователя** (не общая). "
            "Если Ricardo «ничего не нашёл», сбросьте **свою** память кнопкой ниже."
        )
    await callback.message.edit_text(
        text,
        reply_markup=filters_keyboard(
            skip_bids=bool(s.get("filter_skip_bids", True)),
            skip_vehicles=bool(s.get("filter_skip_vehicles", True)),
            remember_sellers=bool(s.get("filter_remember_sellers", True)),
            platform=platform,
        ),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == CB_FILTER_SKIP_BIDS)
async def toggle_skip_bids(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.toggle_filter_skip_bids(uid)
    s = await repo.get_user_settings(uid)
    platform = normalize_platform(s.get("platform"))
    await callback.message.edit_reply_markup(
        reply_markup=filters_keyboard(
            skip_bids=bool(s.get("filter_skip_bids", True)),
            skip_vehicles=bool(s.get("filter_skip_vehicles", True)),
            remember_sellers=bool(s.get("filter_remember_sellers", True)),
            platform=platform,
        ),
    )
    state = "включён" if s.get("filter_skip_bids", True) else "выключен"
    await callback.answer(f"Без Bieden: {state}")


@router.callback_query(F.data == CB_FILTER_CLEAR_SELLERS)
async def clear_sellers_memory(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    platform = normalize_platform((await repo.get_user_settings(uid)).get("platform"))
    removed = await repo.clear_seen_sellers(uid, platform)
    await callback.answer(f"Сброшено в **вашем** личном ЧС: {removed}")


@router.callback_query(F.data == CB_FILTER_SKIP_VEHICLES)
async def toggle_skip_vehicles(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.toggle_filter_skip_vehicles(uid)
    s = await repo.get_user_settings(uid)
    platform = normalize_platform(s.get("platform"))
    await callback.message.edit_reply_markup(
        reply_markup=filters_keyboard(
            skip_bids=bool(s.get("filter_skip_bids", True)),
            skip_vehicles=bool(s.get("filter_skip_vehicles", True)),
            remember_sellers=bool(s.get("filter_remember_sellers", True)),
            platform=platform,
        ),
    )
    state = "включён" if s.get("filter_skip_vehicles", True) else "выключен"
    await callback.answer(f"Без авто/броммеров: {state}")


@router.callback_query(F.data == CB_FILTER_REMEMBER_SELLERS)
async def toggle_remember_sellers(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await repo.toggle_filter_remember_sellers(uid)
    s = await repo.get_user_settings(uid)
    platform = normalize_platform(s.get("platform"))
    await callback.message.edit_reply_markup(
        reply_markup=filters_keyboard(
            skip_bids=bool(s.get("filter_skip_bids", True)),
            skip_vehicles=bool(s.get("filter_skip_vehicles", True)),
            remember_sellers=bool(s.get("filter_remember_sellers", True)),
            platform=platform,
        ),
    )
    state = "включено" if s.get("filter_remember_sellers", True) else "выключено"
    await callback.answer(f"Не повторять продавцов: {state}")


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
    s = await repo.get_user_settings(callback.from_user.id)
    platform = normalize_platform(s.get("platform"))
    hint = PLATFORMS[platform]["proxy_hint"]
    await state.set_state(SettingsForm.waiting_proxy)
    await callback.message.answer(
        f"🌐 Прокси ({hint}):\n"
        "SOCKS5: `socks5://login:pass@host:port`\n"
        "или LomaProxy: `host:port:login:pass`\n"
        "HTTP: `http://login:pass@host:port`\n\n"
        "**Несколько прокси** — каждый с новой строки "
        "(ротация при 403 Cloudflare).\n"
        "Без прокси (прямо с сервера): `off` или `0`\n"
        "Для **2dehands** без прокси часто стабильнее, чем Loma BE.",
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
            "✅ Прокси выкл — парсинг **напрямую** с сервера.\n"
            "Для 2dehands это часто даёт больше объявлений, чем через Loma.",
            reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        )
        return
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1 and "," in lines[0]:
        lines = [p.strip() for p in lines[0].split(",") if p.strip()]

    proxies: list[str] = []
    for line in lines:
        proxy = normalize_proxy(line)
        if not proxy:
            await message.answer(
                f"Не разобрана строка:\n`{line[:80]}`\n\n"
                "Форматы:\n"
                "`socks5://login:pass@host:port`\n"
                "`host:port:login:pass` (LomaProxy)"
            )
            return
        if "://" not in proxy or "@" not in proxy:
            await message.answer(
                f"Не удалось разобрать:\n`{line[:80]}`\n"
                "Пример LomaProxy:\n"
                "`proxy.lomaproxy.com:48174:USER:PASS`"
            )
            return
        proxies.append(proxy)

    stored = "\n".join(proxies)
    await repo.set_proxy(message.from_user.id, stored)
    await state.clear()
    count = len(proxies)
    platform = normalize_platform(
        (await repo.get_user_settings(message.from_user.id)).get("platform")
    )
    extra = ""
    warns = proxy_geo_warnings(proxies, platform)
    if warns:
        extra = "\n\n⚠️ " + warns[0]
    await message.answer(
        f"✅ Сохранено прокси: **{count}**.{extra}\n"
        "Если мало объявлений — попробуйте `off` (без прокси).",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
        parse_mode="Markdown",
    )
