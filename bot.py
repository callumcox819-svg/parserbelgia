#!/usr/bin/env python3
"""Telegram-бот: парсинг 2dehands.be по ссылке → JSON-файл."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from twodehands_parser import parse_2dehands

try:
    import config
except ImportError as exc:
    raise SystemExit(
        "Создайте config.py из config.example.py и укажите BOT_TOKEN."
    ) from exc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

URL_RE = re.compile(
    r"https?://(?:www\.)?(?:2dehands|2ememain)\.be[^\s]*",
    re.IGNORECASE,
)

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Отправьте ссылку на поиск или категорию 2dehands.be — "
        "верну JSON с объявлениями (формат void-parser).\n\n"
        "Пример:\n"
        "https://www.2dehands.be/q/iphone/\n\n"
        "Команды:\n"
        "/parse <url> [limit] — парсинг с лимитом"
    )


@dp.message(Command("parse"))
async def cmd_parse(message: Message) -> None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /parse <url> [limit]")
        return
    url = parts[1]
    limit = int(parts[2]) if len(parts) > 2 else getattr(config, "DEFAULT_LIMIT", 50)
    await _run_parse(message, url, limit)


@dp.message(F.text)
async def on_text(message: Message) -> None:
    match = URL_RE.search(message.text or "")
    if not match:
        return
    limit = getattr(config, "DEFAULT_LIMIT", 50)
    await _run_parse(message, match.group(0), limit)


async def _run_parse(message: Message, url: str, limit: int) -> None:
    status = await message.answer(f"Парсинг… (до {limit} объявлений)")
    proxy = getattr(config, "PROXY", None)
    try:
        result = await parse_2dehands(url, limit=limit, proxy=proxy)
    except Exception as exc:
        logger.exception("parse failed")
        await status.edit_text(f"Ошибка: {exc}")
        return

    count = len(result.get("items", []))
    if count == 0:
        await status.edit_text("Объявления не найдены.")
        return

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"2dehands_{stamp}_",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(result, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)

    try:
        await status.edit_text(f"Готово: {count} объявлений. Отправляю файл…")
        await message.answer_document(
            FSInputFile(tmp_path, filename=f"2dehands-result_{stamp}.json"),
            caption=f"{count} items",
        )
    finally:
        tmp_path.unlink(missing_ok=True)


async def main() -> None:
    token = getattr(config, "BOT_TOKEN", "") or ""
    if not token.strip():
        raise SystemExit("Укажите BOT_TOKEN в config.py")

    bot = Bot(token=token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
