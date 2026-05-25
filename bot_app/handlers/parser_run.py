from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile

from bot_app.config import SETTINGS
from bot_app.keyboards import CB_MAIN_PARSE
from bot_app.services.parser_runner import run_user_parse

router = Router(name="parser")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == CB_MAIN_PARSE)
async def run_parser(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    await callback.answer()
    status = await callback.message.answer("⏳ Парсинг…")

    try:
        result = await run_user_parse(uid, SETTINGS.get("proxy"))
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return
    except Exception as exc:
        logger.exception("parse failed user=%s", uid)
        await status.edit_text(f"❌ Ошибка: {exc}")
        return

    items = result.get("items", [])
    count = len(items)
    if count == 0:
        await status.edit_text(
            "Объявления не найдены (категории пустые или все продавцы уже были)."
        )
        return

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"2dehands_{uid}_{stamp}_",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(result, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)

    try:
        from bot_app.storage import repo as user_repo

        settings = await user_repo.get_user_settings(uid)
        limit = settings["json_limit"]
        await status.edit_text(
            f"✅ Готово: **{count}** объявлений (лимит {limit}).",
            parse_mode="Markdown",
        )
        await callback.message.answer_document(
            FSInputFile(tmp_path, filename=f"2dehands_{stamp}.json"),
            caption=f"{count} items",
        )
    finally:
        tmp_path.unlink(missing_ok=True)
