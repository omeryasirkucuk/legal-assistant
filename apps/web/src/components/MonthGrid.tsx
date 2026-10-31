"use client";

// A month as a lawyer's wall calendar: weeks from Monday, each day with its deadlines as
// labels coloured by how near they are, today marked, weekends and official holidays set
// back, and the judicial recess shaded, since a period cannot end on those days.
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

  return (
    <div className="overflow-hidden rounded-xl border border-rule bg-sheet">
      <div className="grid grid-cols-7 border-b border-rule bg-paper/60">
        {weekdays().map((w, i) => (
          <div key={w} className={`px-2.5 py-2 text-xs font-medium ${i >= 5 ? "text-faint" : "text-muted"}`}>{w}</div>
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
              className={`relative min-h-[6.5rem] border-b border-r border-rule p-1.5 [&:nth-child(7n)]:border-r-0 ${
                outside ? "bg-paper/70" : closed ? "bg-paper/40" : ""} ${recess && !outside ? "bg-[repeating-linear-gradient(135deg,transparent,transparent_6px,rgba(35,75,130,0.05)_6px,rgba(35,75,130,0.05)_12px)]" : ""}`}>
              <div className="flex items-start justify-between gap-1">
                <span className={`flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-[13px] tabular-nums ${
                  isToday ? "bg-ink font-medium text-white" : outside ? "text-faint/70" : closed ? "text-faint" : "text-ink"}`}>
                  {d.getDate()}
                </span>
                {recess && !outside && parseDay(calendars[d.getFullYear()]!.recess_start).getTime() === d.getTime() && (
                  <span className="truncate pt-1 text-[10px] text-cite">{t("judicialRecess")}</span>
                )}
              </div>
              {h && !outside && (
                <p title={h.name} className={`mt-0.5 truncate px-1 text-[10px] leading-tight ${h.half ? "text-faint" : "text-caution"}`}>
                  {h.half ? t("halfDay", { name: h.name }) : h.name}
                </p>
              )}
              <div className="mt-1 space-y-0.5">
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
  );
}
