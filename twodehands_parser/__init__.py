"""Парсер объявлений 2dehands.be → JSON (формат void-parser)."""

from .parser import parse_2dehands, parse_2dehands_sync

__all__ = ["parse_2dehands", "parse_2dehands_sync"]
