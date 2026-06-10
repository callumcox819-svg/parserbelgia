from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from bot_app.app_config import ADMIN_IDS
from bot_app.storage import repo

logger = logging.getLogger(__name__)

RESTART_TEXT = (
    "🔄 **Бот перезагружен** после обновления на сервере.\n\n"
    "Можно снова запускать парсер."
)


def _notify_enabled() -> bool:
    raw = os.environ.get("STARTUP_NOTIFY", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


async def notify_bot_restarted(bot: Bot) -> None:
    if not _notify_enabled():
        logger.info("startup notify disabled (STARTUP_NOTIFY)")
        return

    user_ids = set(await repo.get_user_ids_with_access())
    user_ids.update(ADMIN_IDS)
    if not user_ids:
        logger.info("startup notify: no users with access")
        return

    sent = 0
    for uid in sorted(user_ids):
        try:
            await bot.send_message(uid, RESTART_TEXT, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramForbiddenError:
            logger.debug("startup notify blocked user=%s", uid)
        except TelegramAPIError as exc:
            logger.warning("startup notify failed user=%s: %s", uid, exc)
        except Exception:
            logger.exception("startup notify error user=%s", uid)

    logger.info("startup notify sent=%s users=%s", sent, len(user_ids))
