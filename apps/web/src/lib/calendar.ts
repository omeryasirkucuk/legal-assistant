import type { CalendarDeadline, CalendarEvent, EventKind } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";

export type CalendarItem = (CalendarDeadline & { kind: "deadline" }) | CalendarEvent;
export type CalendarKind = "deadline" | EventKind;

export const kinds: Record<CalendarKind, MessageKey> = {
  deadline: "calendarKindDeadline",
  hearing: "calendarKindHearing",
  meeting: "calendarKindMeeting",
  reminder: "calendarKindReminder",
  event: "calendarKindEvent",
};

export const kindOptions = Object.keys(kinds) as CalendarKind[];

export const kindColor: Record<CalendarKind, string> = {
  deadline: "border-caution bg-caution-soft text-caution",
  hearing: "border-cite bg-cite-soft text-cite",
  meeting: "border-verified bg-verified/10 text-verified",
  reminder: "border-purple-500 bg-purple-500/10 text-purple-700 dark:text-purple-300",
  event: "border-faint bg-desk text-ink",
};

export function calendarToday() {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts();
  const value = (type: string) => parts.find((part) => part.type === type)?.value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}

export function calendarTime(item: CalendarItem): string {
  if (item.kind === "deadline") return "";
  const start = item.start_time?.slice(0, 5);
  return start ? [start, item.end_time?.slice(0, 5)].filter(Boolean).join("–") : t("calendarAllDay");
}

export function sortCalendar(a: CalendarItem, b: CalendarItem): number {
  const time = (item: CalendarItem) => item.kind === "deadline" ? "" : item.start_time ?? "";
  return a.due.localeCompare(b.due) || time(a).localeCompare(time(b)) || a.label.localeCompare(b.label, "tr");
}
