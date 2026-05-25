from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot_app.app_config import ADMIN_IDS, SETTINGS
from bot_app.handlers import setup_routers
from bot_app.handlers.start import setup_bot_commands
from bot_app.middlewares import AccessMiddleware
from bot_app.storage import init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    token = SETTINGS.get("bot_token") or ""
    if not token:
        raise SystemExit(
            "BOT_TOKEN not set. Railway: Variables -> BOT_TOKEN\n"
            "ADMIN_IDS — ваш Telegram user id"
        )
    if not ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS не задан — никто не сможет выдавать доступ. "
            "Укажите ADMIN_IDS в Variables."
        )

    await init_db()

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())
    dp.include_router(setup_routers())

    await setup_bot_commands(bot)
    logger.info("Bot started. Admins: %s", ADMIN_IDS)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
