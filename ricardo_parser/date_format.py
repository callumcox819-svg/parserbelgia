from __future__ import annotations

from datetime import datetime, timezone


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        return many
    if n1 == 1:
        return one
    if 2 <= n1 <= 4:
        return few
    return many


def _parse_iso(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def format_relative_ru(iso_value: str) -> str:
    dt = _parse_iso(iso_value)
    if not dt:
        return iso_value or ""
    now = datetime.now(timezone.utc)
    sec = max(0, int((now - dt).total_seconds()))
    if sec < 60:
        w = _ru_plural(sec, "секунду", "секунды", "секунд")
        return f"{sec} {w} назад"
    minutes, rem = divmod(sec, 60)
    if minutes < 60:
        w = _ru_plural(minutes, "минуту", "минуты", "минут")
        if rem:
            sw = _ru_plural(rem, "секунду", "секунды", "секунд")
            return f"{minutes} {w} {rem} {sw} назад"
        return f"{minutes} {w} назад"
    hours, _ = divmod(sec, 3600)
    if hours < 24:
        w = _ru_plural(hours, "час", "часа", "часов")
        return f"{hours} {w} назад"
    days = sec // 86400
    if days < 30:
        w = _ru_plural(days, "день", "дня", "дней")
        return f"{days} {w} назад"
    months = days // 30
    if months < 12:
        w = _ru_plural(months, "месяц", "месяца", "месяцев")
        return f"{months} {w} назад"
    years = days // 365
    w = _ru_plural(years, "год", "года", "лет")
    return f"{years} {w} назад"


def format_member_since_ru(iso_value: str) -> str:
    dt = _parse_iso(iso_value)
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    years = max(0, (now - dt).days // 365)
    if years < 1:
        months = max(1, (now - dt).days // 30)
        w = _ru_plural(months, "месяц", "месяца", "месяцев")
        return f"{months} {w} назад"
    w = _ru_plural(years, "год", "года", "лет")
    return f"{years} {w} назад"
