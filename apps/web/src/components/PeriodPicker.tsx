"use client";

// The calendar's title as two buttons: the month opens the twelve months, the year opens a
// page of twelve years (arrows move a page), so a date a year or more away is two clicks.
import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { t } from "@/lib/i18n";

type Open = "month" | "year" | null;

const monthName = (m: number, style: "long" | "short") =>
  new Date(2000, m, 1).toLocaleDateString("tr-TR", { month: style });

export function PeriodPicker({ year, month, onPick }: {
  year: number;
  month: number;                                    // 0-11
  onPick: (year: number, month: number) => void;
}) {
  const [open, setOpen] = useState<Open>(null);
  const [page, setPage] = useState(year - 4);        // first year shown in the year grid
  const box = useRef<HTMLDivElement>(null);
  const now = new Date();

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(null); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const toggle = (which: Open) => {
    if (which === "year") setPage(year - 4);
    setOpen(open === which ? null : which);
  };

  const cell = (selected: boolean, current: boolean) =>
    `rounded-md px-2 py-1.5 text-sm capitalize ${selected ? "bg-ink text-white"
      : current ? "text-cite hover:bg-paper" : "text-ink hover:bg-paper"}`;

  const part = (which: Open) =>
    `rounded-md px-1.5 py-0.5 font-serif text-xl capitalize text-ink hover:bg-sheet ${open === which ? "bg-sheet" : ""}`;

  return (
    <div ref={box} className="relative flex min-w-[10rem] items-baseline">
      <button onClick={() => toggle("month")} aria-expanded={open === "month"} aria-label={t("calendarPickMonth")}
        className={part("month")}>{monthName(month, "long")}</button>
      <button onClick={() => toggle("year")} aria-expanded={open === "year"} aria-label={t("calendarPickYear")}
        className={`${part("year")} tabular-nums`}>{year}</button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-2 w-64 rounded-xl border border-rule bg-sheet p-2 shadow-lg">
          {open === "year" && (
            <div className="mb-1 flex items-center justify-between px-1">
              <button onClick={() => setPage(page - 12)} aria-label={t("calendarEarlierYears")}
                className="rounded-md p-1 text-muted hover:bg-paper hover:text-ink"><ChevronLeft size={15} /></button>
              <span className="text-xs tabular-nums text-muted">{page} – {page + 11}</span>
              <button onClick={() => setPage(page + 12)} aria-label={t("calendarLaterYears")}
                className="rounded-md p-1 text-muted hover:bg-paper hover:text-ink"><ChevronRight size={15} /></button>
            </div>
          )}
          <div className="grid grid-cols-3 gap-1">
            {open === "month"
              ? Array.from({ length: 12 }, (_, m) => (
                <button key={m} onClick={() => { onPick(year, m); setOpen(null); }}
                  className={cell(m === month, year === now.getFullYear() && m === now.getMonth())}>
                  {monthName(m, "short")}
                </button>))
              : Array.from({ length: 12 }, (_, i) => page + i).map((y) => (
                <button key={y} onClick={() => { onPick(y, month); setOpen(null); }}
                  className={`${cell(y === year, y === now.getFullYear())} tabular-nums`}>{y}</button>))}
          </div>
        </div>
      )}
    </div>
  );
}
