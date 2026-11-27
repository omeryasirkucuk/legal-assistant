"""Calendar references for Turkish legal work."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ISTANBUL = ZoneInfo("Europe/Istanbul")


def istanbul_date(at: datetime | None = None) -> date:
    return (at.astimezone(ISTANBUL) if at is not None else datetime.now(ISTANBUL)).date()


def date_context(today: date) -> str:
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    return (f"Bu istek için güvenilir takvim (Europe/Istanbul): "
            f"<today>{today}</today>, <yesterday>{yesterday}</yesterday>, "
            f"<tomorrow>{tomorrow}</tomorrow>.")
