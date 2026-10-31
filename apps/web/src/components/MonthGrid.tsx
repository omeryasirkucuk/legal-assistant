"use client";

// A month as a lawyer's wall calendar: weeks from Monday, each day with its deadlines as
// labels coloured by how near they are, today marked, weekends and official holidays set
// back, and the judicial recess shaded, since a period cannot end on those days. On a phone
// the cells are too narrow for labels: a day shows a dot per deadline and the month's
// deadlines are listed under the grid.
import type { CalendarItem, CalendarYear } from "@/lib/api";
import { daysUntil, parseDay, todayIso, urgency } from "@/lib/dates";
import { t } from "@/lib/i18n";

const weekdays = () => t("weekdaysShort").split(",");
const MAX_IN_CELL = 3;

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** The days shown for a month: whole weeks from the Monday before the 1st. */
export function monthDays(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7));
  const last = new Date(year, month + 1, 0);
  const weeks = Math.ceil((((first.getDay() + 6) % 7) + last.getDate()) / 7);
  return Array.from({ length: weeks * 7 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

const dayText = (d: Date) => `${d.getDate()} ${d.toLocaleDateString("tr-TR", { weekday: "short" })}`;

function dotTone(d: CalendarItem): string {
  if (d.done) return "bg-faint/50";
  const u = urgency(daysUntil(d.due));
  return u === "overdue" ? "bg-danger" : u === "later" ? "bg-cite" : "bg-caution";
}

function chipTone(d: CalendarItem): string {
  if (d.done) return "bg-paper text-faint line-through";
  const u = urgency(daysUntil(d.due));
  return u === "overdue" ? "bg-danger/10 text-danger"
    : u === "later" ? "bg-cite-soft text-cite" : "bg-caution-soft text-caution";
}

export function MonthGrid({ year, month, items, calendars, onOpenMatter }: {
  year: number;
  month: number;                                    // 0-11
  items: CalendarItem[];
  calendars: Record<number, CalendarYear>;          // by year (a grid can span two)
  onOpenMatter: (id: string) => void;
}) {
  const today = todayIso();
  const holiday = (d: Date) => calendars[d.getFullYear()]?.holidays.find((h) => h.day === iso(d));
  const inRecess = (d: Date) => {
    const c = calendars[d.getFullYear()];
    return !!c && iso(d) >= c.recess_start && iso(d) <= c.recess_end;
  };

  // Phones: what the narrow cells cannot spell out, listed under the grid.
  const inShownMonth = (day: string) => parseDay(day).getMonth() === month && parseDay(day).getFullYear() === year;
  const inMonth = items.filter((x) => inShownMonth(x.due));
  const holidays = (calendars[year]?.holidays ?? []).filter((h) => inShownMonth(h.day));

  return (
    <>
    <div className="overflow-hidden rounded-xl border border-rule bg-sheet">
      <div className="grid grid-cols-7 border-b border-rule bg-paper/60">
        {weekdays().map((w, i) => (
          <div key={w} className={`px-1 py-2 text-center text-xs font-medium sm:px-2.5 sm:text-left ${i >= 5 ? "text-faint" : "text-muted"}`}>{w}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {monthDays(year, month).map((d, i) => {
          const key = iso(d);
          const outside = d.getMonth() !== month;
          const weekend = i % 7 >= 5;
          const h = holiday(d);
          const recess = inRecess(d);
          const isToday = key === today;
          const due = items.filter((x) => x.due === key);
          const closed = weekend || (h && !h.half);
          return (
            <div key={key}
              className={`relative min-h-[3.25rem] border-b border-r border-rule p-1 sm:min-h-[6.5rem] sm:p-1.5 [&:nth-child(7n)]:border-r-0 ${
                outside ? "bg-paper/70" : closed ? "bg-paper/40" : ""} ${recess && !outside ? "bg-[repeating-linear-gradient(135deg,transparent,transparent_6px,rgba(35,75,130,0.05)_6px,rgba(35,75,130,0.05)_12px)]" : ""}`}>
              <div className="flex items-start justify-center gap-1 sm:justify-between">
                <span className={`flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-[13px] tabular-nums ${
                  isToday ? "bg-ink font-medium text-white" : outside ? "text-faint/70" : closed ? "text-faint" : "text-ink"}`}>
                  {d.getDate()}
                </span>
                {recess && !outside && parseDay(calendars[d.getFullYear()]!.recess_start).getTime() === d.getTime() && (
                  <span className="hidden truncate pt-1 text-[10px] text-cite sm:inline">{t("judicialRecess")}</span>
                )}
              </div>
              {h && !outside && (
                <p title={h.name} className={`mt-0.5 hidden truncate px-1 text-[10px] leading-tight sm:block ${h.half ? "text-faint" : "text-caution"}`}>
                  {h.half ? t("halfDay", { name: h.name }) : h.name}
                </p>
              )}
              {due.length > 0 && (
                <div className="mt-1 flex justify-center gap-0.5 sm:hidden" aria-hidden>
                  {due.slice(0, 4).map((x) => <span key={x.id} className={`h-1.5 w-1.5 rounded-full ${dotTone(x)}`} />)}
                </div>
              )}
              <div className="mt-1 hidden space-y-0.5 sm:block">
                {due.slice(0, MAX_IN_CELL).map((x) => (
                  <button key={x.id} onClick={() => onOpenMatter(x.matter_id)}
                    title={`${x.label}, ${x.client}${x.subject ? `, ${x.subject}` : ""}`}
                    className={`block w-full rounded px-1.5 py-1 text-left leading-tight hover:brightness-95 ${chipTone(x)}`}>
                    <span className="block truncate text-[12px] font-medium">{x.label}</span>
                    <span className="block truncate text-[11px] opacity-75">{x.client}</span>
                  </button>
                ))}
                {due.length > MAX_IN_CELL && (
                  <p className="px-1.5 text-[11px] text-muted">{t("moreInDay", { n: due.length - MAX_IN_CELL })}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
    {(inMonth.length > 0 || holidays.length > 0) && (
      <ul className="mt-4 divide-y divide-rule rounded-xl border border-rule bg-sheet sm:hidden">
        {holidays.map((h) => (
          <li key={h.day} className="flex items-center gap-3 px-3 py-2 text-sm">
            <span className="h-2 w-2 shrink-0" />
            <span className="w-14 shrink-0 tabular-nums text-faint">{dayText(parseDay(h.day))}</span>
            <span className={`min-w-0 flex-1 truncate ${h.half ? "text-faint" : "text-caution"}`}>
              {h.half ? t("halfDay", { name: h.name }) : h.name}
            </span>
          </li>
        ))}
        {inMonth.map((x) => (
          <li key={x.id}>
            <button onClick={() => onOpenMatter(x.matter_id)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left">
              <span className={`h-2 w-2 shrink-0 rounded-full ${dotTone(x)}`} />
              <span className="w-14 shrink-0 text-sm tabular-nums text-muted">{dayText(parseDay(x.due))}</span>
              <span className="min-w-0 flex-1">
                <span className={`block truncate text-sm ${x.done ? "text-faint line-through" : "text-ink"}`}>{x.label}</span>
                <span className="block truncate text-xs text-muted">{x.client}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    )}
    </>
  );
}
