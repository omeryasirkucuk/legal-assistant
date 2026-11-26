"""Export a saved calendar event as an iCalendar file."""

from datetime import UTC, datetime

from legal_api.db.matter_models import ISTANBUL, CalendarEvent


def _text(value: str) -> str:
    value = value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(char for char in value if char in "\t\n" or char.isprintable())
    return value.replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    parts = []
    width = 0
    for char in line:
        size = len(char.encode("utf-8"))
        if width + size > 75:
            parts.append("\r\n ")
            width = 1
        parts.append(char)
        width += size
    return "".join(parts)


def event_ical(event: CalendarEvent) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Legal Assistant//Calendar//TR",
             "BEGIN:VEVENT", f"UID:{event.id}@legal-assistant", f"DTSTAMP:{_utc(datetime.now(UTC))}",
             f"SUMMARY:{_text(event.label)}"]
    if event.start_time is None:
        lines.append(f"DTSTART;VALUE=DATE:{event.due:%Y%m%d}")
    else:
        start = datetime.combine(event.due, event.start_time, ISTANBUL)
        lines.append(f"DTSTART:{_utc(start)}")
        if event.end_time is not None:
            end = datetime.combine(event.due, event.end_time, ISTANBUL)
            lines.append(f"DTEND:{_utc(end)}")
    if event.location:
        lines.append(f"LOCATION:{_text(event.location)}")
    if event.notes:
        lines.append(f"DESCRIPTION:{_text(event.notes)}")
    if event.remind_at and not (event.done or event.reminder_dismissed):
        lines.extend(["BEGIN:VALARM", f"TRIGGER;VALUE=DATE-TIME:{_utc(event.remind_at)}",
                      "ACTION:DISPLAY", f"DESCRIPTION:{_text(event.label)}", "END:VALARM"])
    lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(map(_fold, lines))
