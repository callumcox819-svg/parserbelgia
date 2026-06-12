from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot_app.keyboards import CB_MAIN_PARSE
from bot_app.platforms import normalize_platform
from bot_app.services.parser_runner import resolve_user_proxies, run_user_parse
from bot_app.services.proxy_check import verify_first_proxy
from bot_app.storage import repo

router = Router(name="parser")
logger = logging.getLogger(__name__)

PARSE_TIMEOUT_SEC = float(os.environ.get("PARSE_TIMEOUT_SEC", "900"))


def _empty_result_text(platform: str, stats: dict, seen_before: int) -> str:
    scanned = int(stats.get("listings_scanned") or 0)
    lines = [
        "📭 **Ничего не найдено**",
        "",
        f"Просмотрено страниц API: **{stats.get('pages_fetched', 0)}**",
        f"Листингов на страницах: **{scanned}**",
    ]
    auctions = 0
    sellers = 0
    if platform == "2dehands":
        auctions = int(stats.get("skipped_auctions") or 0)
        sellers = int(stats.get("skipped_sellers") or 0)
        if auctions:
            lines.append(f"Пропущено аукционов (Bieden): **{auctions}**")
        if sellers:
            lines.append(f"Пропущено (продавец уже был): **{sellers}**")
    if seen_before:
        lines.append(f"Продавцов в памяти бота: **{seen_before}**")

    if stats.get("all_filtered") and scanned > 0:
        lines.extend(
            [
                "",
                "✅ **Сайт отвечает** — бот просмотрел объявления, но **все** попали под фильтры:",
                "• **Bieden** (аукционы) и/или",
                "• **память продавцов** (уже отдавали в прошлых JSON).",
                "",
                "**Что сделать:**",
                "1. **Фильтры → Сбросить память продавцов** (главное при "
                f"**{seen_before}** в памяти),",
                "2. или выключить «Без Bieden»,",
                "3. запустить снова (**Прокси → off** для 2dehands).",
            ]
        )
    elif stats.get("blocked_403"):
        lines.extend(
            [
                "",
                "🚫 **CloudFront 403** — IP заблокирован с первых запросов.",
                "**Прокси → off**, подождите 3–5 мин, снова «Запустить парсер».",
            ]
        )
    elif stats.get("timed_out"):
        lines.append(
            f"\n⏱ Лимит времени (**{int(PARSE_TIMEOUT_SEC // 60)} мин**) — "
            "новых объявлений не найдено."
        )
    else:
        lines.extend(
            [
                "",
                "**Частые причины:**",
                "• память продавцов переполнена — **Фильтры → Сбросить память**;",
                "• фильтр Bieden отсекает большинство объявлений;",
                "• CloudFront 403 — **Прокси → off**.",
            ]
        )
    return "\n".join(lines)


def _build_extra(platform: str, stats: dict, count: int, limit: int) -> str:
    extra = ""
    if platform == "2dehands" and stats:
        skipped = int(stats.get("skipped_auctions") or 0)
        if skipped:
            extra += f"\n🚫 Пропущено аукционов (Bieden): **{skipped}**"
        note = stats.get("note")
        if note and count < limit:
            extra += f"\n\n⚠️ {note}"
        sellers_skip = int(stats.get("skipped_sellers") or 0)
        seen_db = int(stats.get("seen_sellers_before") or 0)
        if stats.get("remember_sellers") and seen_db:
            extra += (
                f"\n👤 В памяти бота: **{seen_db}** продавцов "
                f"(пропущено в этом запуске: **{sellers_skip}**)."
            )
        elif sellers_skip:
            extra += f"\n👤 Пропущено из памяти: **{sellers_skip}**."
    if platform == "ricardo" and stats:
        enriched = int(stats.get("enriched") or 0)
        proxies_n = int(stats.get("proxies") or 0)
        pages = int(stats.get("pages") or 0)
        enrich_calls = int(stats.get("enrich_calls") or 0)
        fast = stats.get("fast_mode")
        extra = (
            f"\n📄 Страниц категорий: **{pages}**\n"
            f"📸 С фото/ценой: **{enriched}** из {count}\n"
            f"🌐 Прокси: **{proxies_n}**"
        )
        note = stats.get("note")
        if note and count < limit:
            extra += f"\n\n⚠️ {note}"
        src = stats.get("data_source") or ""
        if src == "links":
            extra += (
                "\n\n⚠️ Ricardo отдал только **ссылки** (без JSON на странице). "
                "Фото/цена пустые — Cloudflare или прокси не CH. "
                "Проверьте exit IP в LomaProxy."
            )
        elif fast:
            extra += (
                "\n⚡ Режим **void** (без /de/a/). "
                "Полные карточки: `RICARDO_ENRICH_MAX=20`."
            )
        elif enrich_calls:
            extra += f"\n🔍 Открыто карточек: **{enrich_calls}**"
        if enriched < count * 0.3 and enrich_calls > 0:
            extra += (
                "\n\n⚠️ **403 Cloudflare** на карточках — поставьте "
                "`RICARDO_ENRICH_MAX=0` (только категории, как void)."
            )
    return extra


async def _deliver_parse_result(
    callback: CallbackQuery,
    status: Message,
    result: dict,
    *,
    settings: dict,
    platform: str,
    plat_label: str,
) -> None:
    items = result.get("items", [])
    count = len(items)
    stats = result.get("stats") or {}
    limit = int(settings["json_limit"])

    if count == 0:
        seen_before = int(stats.get("seen_sellers_before") or 0)
        await status.edit_text(
            _empty_result_text(platform, stats, seen_before),
            parse_mode="Markdown",
        )
        return

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_prefix = f"{platform}_{callback.from_user.id}_{stamp}_"
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=file_prefix,
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(result, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)

    try:
        extra = _build_extra(platform, stats, count, limit)
        if stats.get("timed_out"):
            title = "⏱ Частично (лимит времени)"
        elif stats.get("partial"):
            title = "⚠️ Частично"
        elif count < limit:
            title = "✅ Готово (не полный лимит)"
        else:
            title = "✅ Готово"
        await status.edit_text(
            f"{title} ({plat_label}): **{count}** из **{limit}**.{extra}",
            parse_mode="Markdown",
        )
        await callback.message.answer_document(
            FSInputFile(tmp_path, filename=f"{platform}_{stamp}.json"),
            caption=f"{count} items",
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.callback_query(F.data == CB_MAIN_PARSE)
async def run_parser(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.answer()
    settings = await repo.get_user_settings(uid)
    platform = normalize_platform(settings.get("platform"))
    plat_label = "Ricardo" if platform == "ricardo" else "2dehands"
    proxies = resolve_user_proxies(settings)
    using_direct = proxies == [None]
    logger.info(
        "parse click user=%s platform=%s direct=%s proxies=%s",
        uid,
        platform,
        using_direct,
        len(proxies),
    )

    if using_direct:
        status = await callback.message.answer(
            f"⏳ Парсинг {plat_label}… (без прокси, с сервера)"
        )
    else:
        status = await callback.message.answer("⏳ Проверка прокси…")
        try:
            await asyncio.wait_for(
                verify_first_proxy(platform, proxies[0]),
                timeout=35.0,
            )
        except asyncio.TimeoutError:
            await status.edit_text(
                "❌ Прокси не ответил за 35 с. Проверьте host/port/login или LomaProxy."
            )
            return
        except RuntimeError as exc:
            await status.edit_text(f"❌ {exc}")
            return

    last_progress_edit = 0.0

    async def on_progress(stats: dict) -> None:
        nonlocal last_progress_edit
        now = time.monotonic()
        if now - last_progress_edit < 10.0:
            return
        last_progress_edit = now
        try:
            await status.edit_text(
                f"⏳ Парсинг {plat_label}…\n"
                f"Страниц API: **{stats.get('pages_fetched', 0)}**, "
                f"найдено: **{stats.get('items', 0)}**",
                parse_mode="Markdown",
            )
        except Exception:
            logger.debug("progress edit skipped", exc_info=True)

    limit = int(settings["json_limit"])
    remember = bool(settings.get("filter_remember_sellers", True))
    seen_warn = ""
    if remember:
        seen_n = len(await repo.get_seen_seller_ids(uid, platform))
        if seen_n > 0:
            seen_warn = (
                f"\n👤 Память: **{seen_n}** продавцов — свежие → все категории → "
                "снова с начала."
            )
            if seen_n > limit * 30:
                seen_warn += (
                    f"\n⚠️ Память **{seen_n}** — слишком большая, новых мало. "
                    "**Фильтры → Сбросить память**."
                )
    timeout_min = int(PARSE_TIMEOUT_SEC // 60)
    start_hint = "без прокси" if using_direct else f"{len(proxies)} прокси"
    await status.edit_text(
        f"⏳ Парсинг {plat_label}… ({start_hint}, лимит {limit}, до {timeout_min} мин)\n"
        f"Если за {timeout_min} мин не наберёт **{limit}** — отдам **сколько найдёт**."
        f"{seen_warn}",
        parse_mode="Markdown",
    )

    deadline = time.monotonic() + PARSE_TIMEOUT_SEC
    try:
        result = await run_user_parse(
            uid,
            on_progress=on_progress,
            deadline=deadline,
        )
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}", parse_mode="Markdown")
        return
    except Exception as exc:
        logger.exception("parse failed user=%s", uid)
        await status.edit_text(f"❌ Ошибка: {exc}")
        return

    await _deliver_parse_result(
        callback,
        status,
        result,
        settings=settings,
        platform=platform,
        plat_label=plat_label,
    )
