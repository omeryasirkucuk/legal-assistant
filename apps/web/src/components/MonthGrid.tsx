"use client";

import type { CalendarYear } from "@/lib/api";
import { type CalendarItem, kindColor, kinds } from "@/lib/calendar";
import { formatDay } from "@/lib/dates";
import { t } from "@/lib/i18n";

const MAX_IN_CELL = 3;

export function dayIso(day: Date): string {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

/** Whole weeks from the Monday before the first of the month. */
export function monthDays(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7;
  const last = new Date(year, month + 1, 0);
  const length = Math.ceil((offset + last.getDate()) / 7) * 7;
  return Array.from({ length }, (_, i) => new Date(year, month, 1 - offset + i));
}

export function MonthGrid({ year, month, items, calendars, today, selected, onSelect, onEdit }: {
  year: number;
  month: number;
  items: CalendarItem[];
  calendars: Record<number, CalendarYear>;
  today: string;
  selected: string;
  onSelect: (day: string) => void;
  onEdit: (item: CalendarItem) => void;
}) {
  const byDay = new Map<string, CalendarItem[]>();
  for (const item of items) {
    const entries = byDay.get(item.due) ?? [];
    entries.push(item);
    byDay.set(item.due, entries);
  }

  return (
    <div className="overflow-hidden rounded-xl border border-rule bg-sheet">
      <div className="grid grid-cols-7 border-b border-rule bg-paper/60">
        {t("weekdaysShort").split(",").map((day, i) => (
          <div key={day} className={`px-1 py-2 text-center text-xs font-medium sm:px-2.5 sm:text-left ${i >= 5 ? "text-faint" : "text-muted"}`}>{day}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {monthDays(year, month).map((day, i) => {
          const key = dayIso(day);
          const outside = day.getMonth() !== month;
          const calendar = calendars[day.getFullYear()];
          const holiday = calendar?.holidays.find((entry) => entry.day === key);
          const recess = calendar && calendar.recess_start <= key && key <= calendar.recess_end;
          const entries = byDay.get(key) ?? [];
          return (
            <div key={key} className={`relative min-w-0 border-b border-r border-rule p-0.5 sm:min-h-[7rem] sm:p-1 [&:nth-child(7n)]:border-r-0 ${
              selected === key ? "bg-cite-soft/60" : outside || i % 7 >= 5 || (holiday && !holiday.half) ? "bg-paper/60" : ""
            } ${recess && !outside ? "bg-[repeating-linear-gradient(135deg,transparent,transparent_6px,rgba(35,75,130,0.05)_6px,rgba(35,75,130,0.05)_12px)]" : ""}`}>
              <button type="button" onClick={() => onSelect(key)} aria-pressed={key === selected} aria-current={key === today ? "date" : undefined}
                aria-label={t("calendarDayCount", { date: formatDay(key, "long"), n: entries.length })}
                className="flex min-h-11 w-full flex-col items-center justify-start rounded-md pt-1 text-left hover:bg-desk sm:min-h-7 sm:flex-row sm:justify-between sm:px-1 sm:pt-0">
                <span className={`grid h-6 min-w-6 place-items-center rounded-full text-[13px] tabular-nums ${
                  key === today ? "bg-ink text-white" : selected === key ? "bg-cite text-white" : outside ? "text-faint" : "text-ink"
                }`}>{day.getDate()}</span>
                {key === calendar?.recess_start && <span className="hidden truncate text-[10px] text-cite sm:inline">{t("judicialRecess")}</span>}
                <span aria-hidden className="mt-1 flex gap-0.5 sm:hidden">
                  {holiday && <span className="h-1.5 w-1.5 rounded-full bg-caution" />}
                  {entries.slice(0, 3).map((entry) => <span key={entry.id}
                    className={`h-1.5 w-1.5 rounded-full border ${entry.done ? "border-faint opacity-50" : kindColor[entry.kind]}`} />)}
                </span>
              </button>
              {holiday && (
                <p title={holiday.name} className="hidden truncate px-1 text-[10px] text-caution sm:block">
                  {holiday.half ? t("halfDay", { name: holiday.name }) : holiday.name}
                </p>
              )}
              <div className="mt-1 hidden space-y-0.5 sm:block">
                {entries.slice(0, MAX_IN_CELL).map((entry) => (
                  <button type="button" key={entry.id} onClick={() => onEdit(entry)}
                    title={`${t(kinds[entry.kind])} · ${entry.label}`}
                    className={`block w-full truncate rounded border-l-2 px-1 py-0.5 text-left text-xs hover:brightness-95 ${
                      entry.done ? "border-faint bg-paper text-faint line-through" : kindColor[entry.kind]
                    }`}>
                    {entry.kind !== "deadline" && entry.start_time && <span className="mr-1 tabular-nums">{entry.start_time.slice(0, 5)}</span>}
                    {entry.label}
                  </button>
                ))}
                {entries.length > MAX_IN_CELL && (
                  <button type="button" onClick={() => onSelect(key)} className="px-1 text-xs text-muted hover:text-cite">
                    {t("moreInDay", { n: entries.length - MAX_IN_CELL })}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
