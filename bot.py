#!/usr/bin/env python3
"""Точка входа Telegram-бота."""

from bot_app.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
