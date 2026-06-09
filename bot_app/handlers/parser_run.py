from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile

from bot_app.keyboards import CB_MAIN_PARSE
from bot_app.platforms import normalize_platform
from bot_app.services.parser_runner import run_user_parse, user_proxies_or_error
from bot_app.services.proxy_check import verify_first_proxy
from bot_app.storage import repo

router = Router(name="parser")
logger = logging.getLogger(__name__)


def _empty_result_text(platform: str, stats: dict, seen_before: int) -> str:
    lines = [
        "📭 **Ничего не найдено**",
        "",
        f"Просмотрено страниц API: **{stats.get('pages_fetched', 0)}**",
        f"Листингов на страницах: **{stats.get('listings_scanned', 0)}**",
    ]
    if platform == "2dehands":
        auctions = int(stats.get("skipped_auctions") or 0)
        sellers = int(stats.get("skipped_sellers") or 0)
        if auctions:
            lines.append(f"Пропущено аукционов (Bieden): **{auctions}**")
        if sellers:
            lines.append(f"Пропущено (продавец уже был): **{sellers}**")
    if seen_before:
        lines.append(f"Продавцов в памяти бота: **{seen_before}**")
    lines.extend(
        [
            "",
            "**Частые причины:**",
            "• прокси не той страны (2dehands → BE, Ricardo → CH);",
            "• все подходящие продавцы уже в памяти — сбросьте в Фильтры;",
            "• фильтр Bieden отсекает большинство объявлений;",
            "• CloudFront 403 — смените прокси или снизьте лимит.",
        ]
    )
    return "\n".join(lines)


@router.callback_query(F.data == CB_MAIN_PARSE)
async def run_parser(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.answer()
    settings = await repo.get_user_settings(uid)
    platform = normalize_platform(settings.get("platform"))
    plat_label = "Ricardo" if platform == "ricardo" else "2dehands"
    status = await callback.message.answer(f"⏳ Проверка прокси…")

    try:
        proxies = user_proxies_or_error(settings, platform)
        await verify_first_proxy(platform, proxies[0])
    except ValueError as exc:
        await status.edit_text(str(exc), parse_mode="Markdown")
        return
    except RuntimeError as exc:
        await status.edit_text(f"❌ {exc}")
        return

    await status.edit_text(f"⏳ Парсинг {plat_label}…")

    try:
        result = await run_user_parse(uid)
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}", parse_mode="Markdown")
        return
    except Exception as exc:
        logger.exception("parse failed user=%s", uid)
        await status.edit_text(f"❌ Ошибка: {exc}")
        return

    items = result.get("items", [])
    count = len(items)
    stats = result.get("stats") or {}
    if count == 0:
        seen_before = int(stats.get("seen_sellers_before") or 0)
        await status.edit_text(
            _empty_result_text(platform, stats, seen_before),
            parse_mode="Markdown",
        )
        return

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_prefix = f"{platform}_{uid}_{stamp}_"
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
        limit = settings["json_limit"]
        stats = result.get("stats") or {}
        extra = ""
        if platform == "2dehands" and stats:
            skipped = int(stats.get("skipped_auctions") or 0)
            if skipped:
                extra += f"\n🚫 Пропущено аукционов (Bieden): **{skipped}**"
            if stats.get("partial"):
                note = stats.get("note") or "Частичный результат (403 / лимит страниц)."
                extra += f"\n\n⚠️ {note}"
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
        await status.edit_text(
            f"✅ Готово ({plat_label}): **{count}** объявлений (лимит {limit}).{extra}",
            parse_mode="Markdown",
        )
        await callback.message.answer_document(
            FSInputFile(tmp_path, filename=f"{platform}_{stamp}.json"),
            caption=f"{count} items",
        )
    finally:
        tmp_path.unlink(missing_ok=True)
