"use client";

// Every open file's deadlines: as a month (the default, a wall calendar with holidays and the
// judicial recess) or as a list by when they fall: missed, this week, next week, later.
import { useCallback, useEffect, useState } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { DeadlineActions } from "@/components/DeadlineActions";
import { branchName } from "@/components/DeadlineForm";
import { daysLeftText } from "@/components/DeadlinePanel";
import { MonthGrid, monthDays } from "@/components/MonthGrid";
import { PeriodPicker } from "@/components/PeriodPicker";
import { api, type CalendarItem, type CalendarYear } from "@/lib/api";
import { daysUntil, parseDay, urgency } from "@/lib/dates";
import { t, type MessageKey } from "@/lib/i18n";

type Bucket = "overdue" | "thisWeek" | "nextWeek" | "later";
const BUCKETS: Array<[Bucket, MessageKey]> = [
  ["overdue", "calendarOverdue"], ["thisWeek", "calendarThisWeek"],
  ["nextWeek", "calendarNextWeek"], ["later", "calendarLater"],
];

function bucketOf(iso: string): Bucket {
  const days = daysUntil(iso);
  if (days < 0) return "overdue";
  const now = new Date();
  const toSunday = (7 - ((now.getDay() + 6) % 7)) - 1;     // days left in this week (Mon-Sun)
  return days <= toSunday ? "thisWeek" : days <= toSunday + 7 ? "nextWeek" : "later";
}

type Mode = "month" | "list";

function useMode(): [Mode, (m: Mode) => void] {
  const [mode, setMode] = useState<Mode>("month");
  useEffect(() => {
    try {
      if (localStorage.getItem("calendarMode") === "list") setMode("list");
    } catch {}
  }, []);
  return [mode, (m) => {
    setMode(m);
    try {
      localStorage.setItem("calendarMode", m);
    } catch {}
  }];
}

export function CalendarView({ onOpenMatter }: { onOpenMatter: (id: string) => void }) {
  const [items, setItems] = useState<CalendarItem[] | null>(null);
  const [mode, setMode] = useMode();
  const now = new Date();
  const [shown, setShown] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [calendars, setCalendars] = useState<Record<number, CalendarYear>>({});
  const load = useCallback(() => api.calendar().then(setItems).catch(() => setItems([])), []);
  useEffect(() => { load(); }, [load]);

  // The holidays of every year the shown month's grid touches.
  useEffect(() => {
    const days = monthDays(shown.year, shown.month);
    const years = [...new Set([days[0].getFullYear(), days[days.length - 1].getFullYear()])];
    for (const y of years) {
      if (calendars[y]) continue;
      api.holidays(y).then((c) => setCalendars((all) => ({ ...all, [y]: c }))).catch(() => {});
    }
  }, [shown, calendars]);

  const step = (by: number) => setShown(({ year, month }) => {
    const d = new Date(year, month + by, 1);
    return { year: d.getFullYear(), month: d.getMonth() };
  });
  const title = new Date(shown.year, shown.month, 1).toLocaleDateString("tr-TR", { month: "long", year: "numeric" });
  const isThisMonth = shown.year === now.getFullYear() && shown.month === now.getMonth();

  const [asking, setAsking] = useState<string | null>(null);

  async function toggle(d: CalendarItem) {
    setAsking(null);
    await api.editDeadline(d.id, { done: !d.done });
    load();
  }

  async function remove(d: CalendarItem) {
    setAsking(null);
    await api.deleteDeadline(d.id);
    load();
  }

  const open = (items ?? []).filter((d) => !d.done);
  const done = (items ?? []).filter((d) => d.done);

  return (
    <div className="pb-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-[2rem] leading-tight text-ink">{t("calendar")}</h1>
          <p className="mt-1 text-[15px] text-muted">{t("calendarIntro")}</p>
        </div>
        <div role="radiogroup" aria-label={t("calendarMode")} className="flex rounded-lg bg-desk p-0.5 text-sm">
          {(["month", "list"] as Mode[]).map((m) => (
            <button key={m} role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
              className={`rounded-md px-3 py-1 ${mode === m ? "bg-sheet font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
              {t(m === "month" ? "calendarMonth" : "calendarList")}
            </button>
          ))}
        </div>
      </div>

      {mode === "month" && (
        <div className="mt-6 sm:mt-8">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="sr-only">{title}</h2>
            <PeriodPicker year={shown.year} month={shown.month} onPick={(year, month) => setShown({ year, month })} />
            <button onClick={() => step(-1)} aria-label={t("calendarPrev")}
              className="rounded-md p-1.5 text-muted hover:bg-sheet hover:text-ink"><ChevronLeft size={17} /></button>
            <button onClick={() => step(1)} aria-label={t("calendarNext")}
              className="rounded-md p-1.5 text-muted hover:bg-sheet hover:text-ink"><ChevronRight size={17} /></button>
            {!isThisMonth && (
              <button onClick={() => setShown({ year: now.getFullYear(), month: now.getMonth() })}
                className="ml-1 rounded-md border border-rule px-2.5 py-1 text-sm text-ink hover:bg-sheet">{t("calendarToday")}</button>
            )}
            {calendars[shown.year] && !calendars[shown.year].covered && (
              <span className="text-xs text-caution sm:ml-auto">{t("calendarNotCovered", { year: shown.year })}</span>
            )}
          </div>
          <MonthGrid year={shown.year} month={shown.month} items={items ?? []} calendars={calendars}
            onOpenMatter={onOpenMatter} />
        </div>
      )}

      {mode === "list" && items && open.length === 0 && (
        <p className="mt-10 text-sm text-faint">{t("calendarEmpty")}</p>
      )}

      {mode === "list" && BUCKETS.map(([bucket, heading]) => {
        const list = open.filter((d) => bucketOf(d.due) === bucket);
        if (!list.length) return null;
        return (
          <section key={bucket} className="mt-10">
            <h2 className={`border-b border-rule pb-2 font-serif text-lg ${bucket === "overdue" ? "text-danger" : "text-ink"}`}>
              {t(heading)}
            </h2>
            <ul className="divide-y divide-rule">
              {list.map((d) => {
                const day = parseDay(d.due);
                const left = daysUntil(d.due);
                const tone = { overdue: "text-danger", today: "text-caution", soon: "text-caution", later: "text-muted" }[urgency(left)];
                return (
                  <li key={d.id} className="group flex items-center gap-3 py-3 sm:gap-5">
                    <div className="w-12 shrink-0 text-center">
                      <p className="font-serif text-2xl leading-none text-ink tabular-nums">{day.getDate()}</p>
                      <p className="mt-1 text-[11px] text-faint">
                        {day.toLocaleDateString("tr-TR", { month: "short" })} · {day.toLocaleDateString("tr-TR", { weekday: "short" })}
                      </p>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[15px] text-ink">{d.label}</p>
                      <button onClick={() => onOpenMatter(d.matter_id)} className="block max-w-full truncate text-left text-sm text-muted hover:text-cite hover:underline">
                        {d.client}{d.subject && `, ${d.subject}`}
                      </button>
                      <p className="text-xs">
                        <span className={`tabular-nums sm:hidden ${tone}`}>{daysLeftText(left)}</span>
                        {d.branch && <span className="text-faint max-sm:ml-2">{branchName(d.branch)}</span>}
                      </p>
                      {asking === d.id && (
                        <DeadlineActions onDone={() => toggle(d)} onDelete={() => remove(d)} onCancel={() => setAsking(null)} />
                      )}
                    </div>
                    <span className={`hidden shrink-0 text-sm tabular-nums sm:inline ${tone}`}>{daysLeftText(left)}</span>
                    <button onClick={() => setAsking(asking === d.id ? null : d.id)} aria-label={t("deadlineDone")}
                      aria-expanded={asking === d.id}
                      className="group/tick -m-2 shrink-0 p-2">
                      <span className={`flex h-5 w-5 items-center justify-center rounded-full border text-transparent group-hover/tick:border-verified group-hover/tick:text-verified ${
                        asking === d.id ? "border-ink ring-2 ring-ink/10" : "border-faint"}`}>
                        <Check size={11} strokeWidth={3} />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {mode === "list" && done.length > 0 && (
        <details className="mt-10">
          <summary className="cursor-pointer text-sm text-muted hover:text-ink">{t("deadlinesDone", { n: done.length })}</summary>
          <ul className="mt-2 divide-y divide-rule">
            {done.map((d) => (
              <li key={d.id} className="flex items-center gap-3 py-2 text-sm text-faint sm:gap-4">
                <span className="w-20 shrink-0 tabular-nums sm:w-24">{parseDay(d.due).toLocaleDateString("tr-TR")}</span>
                <span className="min-w-0 flex-1 truncate line-through">{d.label}</span>
                <span className="hidden truncate sm:inline">{d.client}</span>
                <button onClick={() => toggle(d)} className="text-xs text-muted hover:text-ink">{t("deadlineUndo")}</button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
