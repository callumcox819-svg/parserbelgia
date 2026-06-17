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
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot_app.keyboards import CB_MAIN_PARSE, CB_PARSE_STOP, parsing_keyboard
from bot_app.platforms import normalize_platform
from bot_app.services.parse_control import begin as begin_parse, end as end_parse, request_cancel
from bot_app.services.parser_runner import (
    persist_parse_sellers,
    resolve_user_proxies,
    run_user_parse,
)
from bot_app.services.proxy_check import verify_first_proxy
from bot_app.storage import repo

router = Router(name="parser")
logger = logging.getLogger(__name__)

PARSE_TIMEOUT_SEC = float(os.environ.get("PARSE_TIMEOUT_SEC", "1800"))
PARSE_SOFT_DELIVERY_SEC = float(os.environ.get("PARSE_SOFT_DELIVERY_SEC", "480"))
PROGRESS_EDIT_SEC = float(os.environ.get("PARSE_PROGRESS_EDIT_SEC", "25"))


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
        trimmed = int(stats.get("sellers_trimmed") or 0)
        if trimmed:
            extra += f"\n✂️ Обрезано старых продавцов: **{trimmed}**."
        repeats = int(stats.get("output_repeat_sellers") or 0)
        if repeats:
            extra += (
                f"\n🚨 **Ошибка:** **{repeats}** продавцов в JSON уже были в памяти — "
                "напишите админу."
            )
        sellers_skip = int(stats.get("skipped_sellers") or 0)
        seen_db = int(stats.get("seen_sellers_before") or 0)
        if stats.get("remember_sellers") and seen_db:
            extra += (
                f"\n👤 **Ваш личный** ЧС: **{seen_db}** продавцов "
                f"(пропущено в этом запуске: **{sellers_skip}**)."
            )
        elif sellers_skip:
            extra += f"\n👤 Пропущено из памяти: **{sellers_skip}**."
        full = int(stats.get("full_name_count") or 0)
        single = int(stats.get("single_word_names") or 0)
        uniq = int(stats.get("unique_names") or 0)
        if count:
            extra += (
                f"\n📋 Имена: **{uniq}** уник., "
                f"**{full}** с 2+ словами (обычно годятся для валидации), "
                f"**{single}** однословных ников."
            )
            extra += (
                "\n💡 ЧС в **софте** и **личная память бота** (Фильтры) — "
                "**разные**. У каждого пользователя своя память."
            )
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


async def _safe_edit_status(status: Message, text: str) -> None:
    """Статус после JSON: не роняем доставку файла из-за Markdown / flood."""
    if len(text) > 4000:
        text = text[:3990] + "…"
    try:
        await status.edit_text(text, parse_mode="Markdown", reply_markup=None)
        return
    except TelegramRetryAfter as exc:
        await asyncio.sleep(float(exc.retry_after) + 0.5)
        try:
            await status.edit_text(text, parse_mode="Markdown", reply_markup=None)
            return
        except Exception:
            logger.warning("status edit retry failed", exc_info=True)
    except TelegramBadRequest:
        plain = text.replace("**", "")
        try:
            await status.edit_text(plain[:4096])
            return
        except Exception:
            logger.warning("status edit plain failed", exc_info=True)
    except Exception:
        logger.warning("status edit failed", exc_info=True)


async def _send_parse_document(
    callback: CallbackQuery,
    tmp_path: Path,
    *,
    platform: str,
    stamp: str,
    count: int,
) -> None:
    doc = FSInputFile(tmp_path, filename=f"{platform}_{stamp}.json")
    for attempt in range(3):
        try:
            await callback.message.answer_document(doc, caption=f"{count} items")
            return
        except TelegramRetryAfter as exc:
            wait = float(exc.retry_after) + 0.5
            logger.warning("document flood wait %.1fs attempt=%s", wait, attempt + 1)
            await asyncio.sleep(wait)
        except Exception:
            if attempt >= 2:
                raise
            logger.warning("document send retry", exc_info=True)
            await asyncio.sleep(2.0)
    raise RuntimeError("Не удалось отправить JSON в Telegram после 3 попыток")


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

    extra = _build_extra(platform, stats, count, limit)
    if stats.get("timed_out"):
        title = "⏱ Частично (лимит времени)"
    elif stats.get("cancelled"):
        title = "⏹ Остановлено"
    elif stats.get("stagnated"):
        title = "📋 Частично (новых нет)"
    elif stats.get("partial"):
        title = "⚠️ Частично"
    elif count < limit:
        title = "✅ Готово (не полный лимит)"
    else:
        title = "✅ Готово"
    summary = f"{title} ({plat_label}): **{count}** из **{limit}**.{extra}"

    try:
        await _send_parse_document(
            callback,
            tmp_path,
            platform=platform,
            stamp=stamp,
            count=count,
        )
    except Exception:
        logger.exception(
            "JSON delivery failed user=%s platform=%s count=%s",
            callback.from_user.id,
            platform,
            count,
        )
        try:
            await callback.message.answer(
                f"⚠️ JSON (**{count}** шт.) не отправился — нажмите «Запустить парсер» "
                "ещё раз или напишите админу."
            )
        except Exception:
            pass
        raise
    finally:
        tmp_path.unlink(missing_ok=True)

    await _safe_edit_status(status, summary)


@router.callback_query(F.data == CB_PARSE_STOP)
async def stop_parser(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    if request_cancel(uid):
        await callback.answer("Останавливаю парсер…")
    else:
        await callback.answer("Сейчас нет активного парсинга", show_alert=True)


@router.callback_query(F.data == CB_MAIN_PARSE)
async def run_parser(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.answer()
    session = begin_parse(uid)
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
            f"⏳ Парсинг {plat_label}… (без прокси, с сервера)",
            reply_markup=parsing_keyboard(),
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
        if now - last_progress_edit < PROGRESS_EDIT_SEC:
            return
        last_progress_edit = now
        try:
            skipped = stats.get("skipped_sellers") or 0
            skip_line = (
                f"\nПропущено (ваш ЧС): **{skipped}**"
                if skipped
                else ""
            )
            await status.edit_text(
                f"⏳ Парсинг {plat_label}…\n"
                f"Страниц API: **{stats.get('pages_fetched', 0)}**, "
                f"найдено: **{stats.get('items', 0)}**{skip_line}\n"
                f"⏹ **СТОП** — отдать JSON сейчас",
                parse_mode="Markdown",
                reply_markup=parsing_keyboard(),
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
                f"\n👤 **Ваш личный** ЧС: **{seen_n}** продавцов — в JSON только **новые**."
            )
        if seen_n > limit * 20:
            seen_warn += (
                f"\n⚠️ При **{seen_n}** в памяти за прогон часто **100–350**, "
                "не 500. **Сбросить память** — для полного лимита."
            )
    timeout_min = int(PARSE_TIMEOUT_SEC // 60)
    soft_min = int(PARSE_SOFT_DELIVERY_SEC // 60) if PARSE_SOFT_DELIVERY_SEC > 0 else 0
    start_hint = "без прокси" if using_direct else f"{len(proxies)} прокси"
    soft_hint = (
        f"\nЕсли за **{soft_min} мин** не наберёт **{limit}** — отдам **частичный JSON**."
        if soft_min
        else ""
    )
    await status.edit_text(
        f"⏳ Парсинг {plat_label}… ({start_hint}, лимит {limit}, до {timeout_min} мин)\n"
        f"⏹ **СТОП** — завершить и отдать JSON.{soft_hint}"
        f"{seen_warn}",
        parse_mode="Markdown",
        reply_markup=parsing_keyboard(),
    )

    deadline = time.monotonic() + PARSE_TIMEOUT_SEC
    soft_deadline = (
        time.monotonic() + PARSE_SOFT_DELIVERY_SEC
        if PARSE_SOFT_DELIVERY_SEC > 0
        else None
    )

    def should_stop() -> bool:
        return session.cancel.is_set()

    try:
        result = await run_user_parse(
            uid,
            on_progress=on_progress,
            deadline=deadline,
            soft_deadline=soft_deadline,
            should_stop=should_stop,
            persist_sellers=False,
        )
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}", parse_mode="Markdown", reply_markup=None)
        return
    except Exception as exc:
        logger.exception("parse failed user=%s", uid)
        await status.edit_text(f"❌ Ошибка: {exc}", reply_markup=None)
        return
    finally:
        end_parse(uid)

    await _deliver_parse_result(
        callback,
        status,
        result,
        settings=settings,
        platform=platform,
        plat_label=plat_label,
    )
    await persist_parse_sellers(uid, result)
