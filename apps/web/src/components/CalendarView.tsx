"use client";

import { useEffect, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { CalendarEditor } from "@/components/CalendarEditor";
import { CalendarRow } from "@/components/CalendarRow";
import { MonthGrid, monthDays } from "@/components/MonthGrid";
import { PeriodPicker } from "@/components/PeriodPicker";
import { api, type CalendarYear, type Matter } from "@/lib/api";
import { type CalendarItem, type CalendarKind, calendarToday, kindColor, kindOptions, kinds, sortCalendar } from "@/lib/calendar";
import { daysUntil, formatDay, parseDay } from "@/lib/dates";
import { t, type MessageKey } from "@/lib/i18n";

type Mode = "month" | "list";
type Bucket = "overdue" | "past" | "thisWeek" | "nextWeek" | "later" | "done";
const buckets: Array<[Bucket, MessageKey]> = [
  ["overdue", "calendarOverdue"], ["thisWeek", "calendarThisWeek"],
  ["nextWeek", "calendarNextWeek"], ["later", "calendarLater"],
  ["past", "calendarPast"], ["done", "calendarDone"],
];

function bucketOf(item: CalendarItem, now: Date): Bucket {
  if (item.done) return "done";
  const days = daysUntil(item.due, now);
  if (days < 0) return item.kind === "deadline" || item.kind === "reminder" ? "overdue" : "past";
  const toSunday = 6 - (now.getDay() + 6) % 7;
  return days <= toSunday ? "thisWeek" : days <= toSunday + 7 ? "nextWeek" : "later";
}

const control = "min-w-0 rounded-lg border border-rule bg-sheet px-2.5 py-2 text-sm text-ink focus:border-cite";

export function CalendarView({ matters, reminderId, onReminderOpened, onOpenMatter, onChanged }: {
  matters: Matter[];
  reminderId: string | null;
  onReminderOpened: () => void;
  onOpenMatter: (id: string) => void;
  onChanged: (kind: CalendarKind) => void;
}) {
  const [items, setItems] = useState<CalendarItem[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [version, setVersion] = useState(0);
  const [mode, setMode] = useState<Mode>("month");
  const today = calendarToday();
  const now = parseDay(today);
  const [shown, setShown] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [selected, setSelected] = useState(today);
  const [calendars, setCalendars] = useState<Record<number, CalendarYear>>({});
  const [failedYears, setFailedYears] = useState<number[]>([]);
  const [editor, setEditor] = useState<{ day: string; item?: CalendarItem } | null>(null);
  const [kind, setKind] = useState<CalendarKind | "all">("all");
  const [status, setStatus] = useState("all");
  const [matterId, setMatterId] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    try { if (localStorage.getItem("calendarMode") === "list") setMode("list"); } catch {}
  }, []);

  useEffect(() => {
    let live = true;
    Promise.all([api.calendar(), api.calendarEvents()])
      .then(([deadlines, events]) => {
        if (!live) return;
        const rows: CalendarItem[] = [...deadlines.map((item) => ({ ...item, kind: "deadline" as const })), ...events];
        setItems(rows.sort(sortCalendar));
        setLoadError(false);
      })
      .catch(() => { if (live) setLoadError(true); });
    return () => { live = false; };
  }, [version]);

  useEffect(() => {
    const days = monthDays(shown.year, shown.month);
    const years = [...new Set([days[0].getFullYear(), days[days.length - 1].getFullYear()])]
      .filter((year) => !calendars[year] && !failedYears.includes(year));
    if (!years.length) return;
    let live = true;
    Promise.allSettled(years.map(api.holidays)).then((results) => {
      if (!live) return;
      const loaded = results.flatMap((result) => result.status === "fulfilled" ? [[result.value.year, result.value]] : []);
      setCalendars((current) => ({ ...current, ...Object.fromEntries(loaded) }));
      setFailedYears((current) => [...current, ...years.filter((_, i) => results[i].status === "rejected")]);
    });
    return () => { live = false; };
  }, [shown, calendars, failedYears]);

  useEffect(() => {
    if (!reminderId || !items) return;
    const item = items.find((row) => row.kind !== "deadline" && row.id === reminderId);
    if (item) {
      const date = parseDay(item.due);
      setShown({ year: date.getFullYear(), month: date.getMonth() });
      setSelected(item.due);
      setEditor({ day: item.due, item });
    }
    onReminderOpened();
  }, [items, reminderId, onReminderOpened]);

  function selectDay(day: string) {
    const date = parseDay(day);
    if (date.getFullYear() !== shown.year || date.getMonth() !== shown.month) {
      setShown({ year: date.getFullYear(), month: date.getMonth() });
    }
    setSelected(day);
  }

  function pickMonth(year: number, month: number) {
    selectDay(year === now.getFullYear() && month === now.getMonth() ? today
      : `${year}-${String(month + 1).padStart(2, "0")}-01`);
  }

  function step(by: number) {
    const date = new Date(shown.year, shown.month + by, 1);
    pickMonth(date.getFullYear(), date.getMonth());
  }

  const matterById = new Map(matters.map((matter) => [matter.id, matter]));
  function matterName(item: CalendarItem) {
    const matter = item.matter_id ? matterById.get(item.matter_id) : null;
    if (matter) return [matter.client, matter.subject, matter.case_no].filter(Boolean).join(" · ");
    return item.kind === "deadline" ? [item.client, item.subject].filter(Boolean).join(" · ")
      : item.matter_id ? t("calendarLinkedMatter") : t("calendarPersonal");
  }

  const term = query.trim().toLocaleLowerCase("tr");
  const visible = (items ?? []).filter((item) =>
    (kind === "all" || item.kind === kind)
    && (status === "all" || item.done === (status === "done"))
    && (!matterId || (matterId === "personal" ? !item.matter_id : item.matter_id === matterId))
    && (!term || [item.label, matterName(item), t(kinds[item.kind]), ...(item.kind === "deadline" ? [] : [item.notes, item.location])]
      .some((value) => value.toLocaleLowerCase("tr").includes(term)))
  );
  const selectedItems = visible.filter((item) => item.due === selected);
  const daysCalendar = calendars[parseDay(selected).getFullYear()];
  const holiday = daysCalendar?.holidays.find((h) => h.day === selected);
  const inRecess = daysCalendar && selected >= daysCalendar.recess_start && selected <= daysCalendar.recess_end;
  const editItem = (item: CalendarItem) => setEditor({ day: item.due, item });
  const addItem = () => setEditor({ day: mode === "month" ? selected : today });
  const row = (item: CalendarItem, showDate = false) => (
    <CalendarRow key={`${item.kind}-${item.id}`} item={item} matter={matterName(item)} showDate={showDate} onEdit={() => editItem(item)} />
  );

  return (
    <div className="pb-12">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-[2rem] leading-tight text-ink">{t("calendar")}</h1>
          <p className="mt-1 text-[15px] text-muted">{t("calendarIntro")}</p>
        </div>
        <button type="button" onClick={addItem} className="inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white">
          <Plus size={17} /> {t("calendarAdd")}
        </button>
      </header>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <div className="relative min-w-40 flex-1">
          <Search size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input type="search" value={query} onChange={(e) => {
            setQuery(e.target.value);
            if (e.target.value.trim()) setMode("list");
          }} aria-label={t("calendarSearch")}
            placeholder={t("calendarSearch")} className={`w-full pl-8 ${control}`} />
        </div>
        <select className={control} aria-label={t("calendarType")} value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="all">{t("calendarAllTypes")}</option>
          {kindOptions.map((value) => <option key={value} value={value}>{t(kinds[value])}</option>)}
        </select>
        <select className={`max-w-48 ${control}`} aria-label={t("calendarMatter")} value={matterId} onChange={(e) => setMatterId(e.target.value)}>
          <option value="">{t("calendarAllMatters")}</option>
          <option value="personal">{t("calendarPersonal")}</option>
          {matters.map((matter) => <option key={matter.id} value={matter.id}>{[matter.client, matter.subject, matter.case_no].filter(Boolean).join(" · ")}</option>)}
        </select>
        <select className={control} aria-label={t("calendarStatus")} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="all">{t("calendarAllStatuses")}</option>
          <option value="open">{t("calendarOpen")}</option>
          <option value="done">{t("calendarDone")}</option>
        </select>
        <div role="group" aria-label={t("calendarMode")} className="ml-auto flex rounded-lg bg-desk p-0.5 text-sm">
          {(["month", "list"] as Mode[]).map((value) => (
            <button type="button" key={value} aria-pressed={mode === value} onClick={() => {
              setMode(value);
              try { localStorage.setItem("calendarMode", value); } catch {}
            }} className={`rounded-md px-3 py-1.5 ${mode === value ? "bg-sheet font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
              {t(value === "month" ? "calendarMonth" : "calendarList")}
            </button>
          ))}
        </div>
      </div>

      {loadError && <p role="alert" className="mt-4 text-sm text-danger">
        {t("calendarLoadError")} <button type="button" className="underline" onClick={() => setVersion((v) => v + 1)}>{t("calendarRetry")}</button>
      </p>}
      {!items && !loadError && <p role="status" className="mt-4 text-sm text-muted">{t("loading")}</p>}

      {mode === "month" && (
        <div className="mt-5">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <PeriodPicker year={shown.year} month={shown.month} onPick={pickMonth} />
            <button type="button" onClick={() => step(-1)} aria-label={t("calendarPrev")}
              className="rounded-md p-2 text-muted hover:bg-sheet hover:text-ink"><ChevronLeft size={17} /></button>
            <button type="button" onClick={() => step(1)} aria-label={t("calendarNext")}
              className="rounded-md p-2 text-muted hover:bg-sheet hover:text-ink"><ChevronRight size={17} /></button>
            <button type="button" onClick={() => selectDay(today)} className="rounded-md border border-rule px-2.5 py-1 text-sm text-ink hover:bg-sheet">
              {t("calendarToday")}
            </button>
            {failedYears.includes(shown.year) ? (
              <button type="button" className="text-xs text-caution underline sm:ml-auto" onClick={() => setFailedYears([])}>{t("calendarHolidayRetry")}</button>
            ) : calendars[shown.year] && !calendars[shown.year].covered && (
              <span className="text-xs text-caution sm:ml-auto">{t("calendarNotCovered", { year: shown.year })}</span>
            )}
          </div>
          <MonthGrid year={shown.year} month={shown.month} items={visible} calendars={calendars}
            today={today} selected={selected} onSelect={selectDay} onEdit={editItem} />
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {kindOptions.map((value) => <span key={value} className="flex items-center gap-1.5">
              <span aria-hidden className={`h-2 w-2 rounded-full border ${kindColor[value]}`} />{t(kinds[value])}
            </span>)}
          </div>

          <section className="mt-6 rounded-xl border border-rule bg-sheet px-3 py-2 sm:px-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule py-2">
              <h2 className="flex items-center gap-2 font-serif text-lg text-ink"><CalendarDays size={17} />{formatDay(selected, "long")}</h2>
              <button type="button" onClick={addItem} className="inline-flex items-center gap-1 rounded px-2 py-1 text-sm text-cite hover:bg-cite-soft">
                <Plus size={15} /> {t("calendarAddOnDay")}
              </button>
            </div>
            {(holiday || inRecess) && <div className="flex flex-wrap gap-2 border-b border-rule py-2 text-xs text-caution">
              {holiday && <span>{holiday.half ? t("halfDay", { name: holiday.name }) : holiday.name}</span>}
              {inRecess && <span className="text-cite">{t("judicialRecess")}</span>}
            </div>}
            {items && (selectedItems.length > 0
              ? <ul className="divide-y divide-rule py-1">{selectedItems.map((item) => row(item))}</ul>
              : <p className="px-2 py-4 text-sm text-muted">{t("calendarDayEmpty")}</p>)}
          </section>
        </div>
      )}

      {mode === "list" && items && visible.length === 0 && <p className="mt-8 text-sm text-muted">{t("calendarEmpty")}</p>}
      {mode === "list" && buckets.map(([bucket, heading]) => {
        const list = visible.filter((item) => bucketOf(item, now) === bucket);
        if (!list.length) return null;
        if (bucket === "past" || bucket === "done") list.reverse();
        return (
          <section key={bucket} className="mt-6 rounded-xl border border-rule bg-sheet px-3 py-2 sm:px-4">
            <h2 className={`border-b border-rule px-2 py-2 font-serif text-lg ${bucket === "overdue" ? "text-danger" : "text-ink"}`}>{t(heading)}</h2>
            <ul className="divide-y divide-rule py-1">{list.map((item) => row(item, true))}</ul>
          </section>
        );
      })}

      {editor && <CalendarEditor item={editor.item} day={editor.day} matters={matters}
        initialKind={kind === "all" ? undefined : kind} matterId={!editor.item && matterId !== "personal" ? matterId : undefined}
        onClose={() => setEditor(null)} onOpenMatter={onOpenMatter} onChanged={(day, changedKind) => {
          setEditor(null);
          selectDay(day);
          setVersion((v) => v + 1);
          if (!editor.item) {
            if (kind !== "all" && kind !== changedKind) setKind("all");
            setStatus("all");
            setMatterId("");
            setQuery("");
          }
          onChanged(changedKind);
        }} />}
    </div>
  );
}
