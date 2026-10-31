"use client";

// Adding a deadline to a file, in a dialog. By default the lawyer gives what is on the notice (when and
// how it came, the period, the branch) and the last day is computed on the server with the
// holidays and the judicial recess, each step shown before it is saved; or the lawyer types
// the last day directly.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { api, type Branch, type NoticeResult, type NoticeStep, type PeriodUnit, type Service } from "@/lib/api";
import { formatDay, todayIso } from "@/lib/dates";
import { t, type MessageKey } from "@/lib/i18n";

type Mode = "notice" | "date";

const SERVICES: Array<[Service, MessageKey]> = [
  ["electronic", "serviceElectronic"], ["hearing", "serviceHearing"], ["physical", "servicePhysical"],
];
const UNITS: Array<[PeriodUnit, MessageKey]> = [["day", "unitDay"], ["week", "unitWeek"], ["month", "unitMonth"]];
const PRESETS: Array<[number, PeriodUnit, MessageKey]> = [
  [1, "week", "presetOneWeek"], [2, "week", "presetTwoWeeks"], [1, "month", "presetOneMonth"],
];
export const BRANCHES: Array<[Branch, MessageKey]> = [
  ["civil", "branchCivil"], ["criminal", "branchCriminal"], ["enforcement", "branchEnforcement"],
  ["administrative", "branchAdministrative"], ["arbitration", "branchArbitration"],
];

/** The branch's name, for showing a saved deadline. */
export function branchName(b: Branch | null): string {
  const key = BRANCHES.find(([x]) => x === b)?.[1];
  return key ? t(key) : "";
}

const field = "rounded-lg border border-rule bg-sheet px-3 py-2 text-sm outline-none placeholder:text-faint focus:border-cite";

function Segmented<T extends string>({ options, value, onChange, label }: {
  options: Array<[T, MessageKey]>; value: T | null; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-lg bg-desk p-0.5 text-[13px]">
      {options.map(([v, key]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={`flex-1 whitespace-nowrap rounded-md px-2 py-1.5 ${value === v ? "bg-sheet font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
          {t(key)}
        </button>
      ))}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <p className="mb-1 text-xs text-muted">{children}</p>;
}

/** One line of the explanation, from the server's step codes. */
function stepText(s: NoticeStep, law: string): string {
  const v = Object.fromEntries(Object.entries(s.values).map(([k, x]) => [k, /^\d{4}-\d{2}-\d{2}$/.test(x) ? formatDay(x, "long") : x]));
  switch (s.code) {
    case "period": return t("stepPeriod", { end: v.end });
    case "recess": return t("stepRecess", { end: v.end, law });
    case "weekend": return t("stepWeekend", { day: v.day, end: v.end });
    case "holiday": return t("stepHoliday", { day: v.day, name: v.name, end: v.end });
    case "not_covered": return t("warnNotCovered", { year: v.year });
    case "half_day": return t("warnHalfDay", { name: v.name });
    default: return "";
  }
}

function useBranch(matterId: string): [Branch, (b: Branch) => void] {
  const key = `deadlineBranch:${matterId}`;
  const [branch, setBranch] = useState<Branch>("civil");
  useEffect(() => {
    try {
      const saved = localStorage.getItem(key) as Branch | null;
      if (saved && BRANCHES.some(([b]) => b === saved)) setBranch(saved);
    } catch {}
  }, [key]);
  return [branch, (b) => {
    setBranch(b);
    try { localStorage.setItem(key, b); } catch {}
  }];
}

export function DeadlineForm({ matterId, onSaved, onCancel }: {
  matterId: string; onSaved: () => void; onCancel: () => void;
}) {
  const [mode, setMode] = useState<Mode>("notice");
  const [label, setLabel] = useState("");
  const [received, setReceived] = useState(todayIso());
  const [service, setService] = useState<Service>("electronic");
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState<PeriodUnit>("week");
  const [branch, setBranch] = useBranch(matterId);
  const [due, setDue] = useState("");
  const [result, setResult] = useState<NoticeResult | null>(null);

  const n = Number(amount);
  const bump = (by: number) => setAmount(String(Math.max(1, (Number.isInteger(n) ? n : 0) + by)));
  const complete = mode === "notice" ? !!received && n >= 1 && Number.isInteger(n) : !!due;

  useEffect(() => {
    if (mode !== "notice" || !received || !(n >= 1) || !Number.isInteger(n)) {
      setResult(null);
      return;
    }
    let live = true;
    api.calculateDeadline({ received, service, amount: n, unit, branch })
      .then((r) => { if (live) setResult(r); })
      .catch(() => { if (live) setResult(null); });
    return () => { live = false; };
  }, [mode, received, service, n, unit, branch]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const day = mode === "notice" ? result?.due : due;
    if (!label.trim() || !day) return;
    await api.addDeadline(matterId, label.trim(), day, undefined, branch);
    onSaved();
  }

  const notes = result ? [
    ...(branch === "enforcement" ? [t("noteEnforcement")] : []),
    ...result.notes.map((x) => t(x === "detention" ? "noteDetention" : "noteArbitration")),
  ] : [];

  const branchPicker = (
    <div>
      <Label>{t("branch")}</Label>
      <div className="flex flex-wrap gap-1.5">
        {BRANCHES.map(([b, key]) => (
          <button key={b} type="button" onClick={() => setBranch(b)} aria-pressed={branch === b}
            className={`rounded-full border px-2.5 py-0.5 text-xs pointer-coarse:py-1.5 ${branch === b ? "border-ink bg-ink text-white" : "border-rule text-muted hover:border-ink hover:text-ink"}`}>
            {t(key)}
          </button>
        ))}
      </div>
    </div>
  );

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onCancel]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/25 px-3 py-4 sm:px-4 sm:py-[8vh]"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
    <form onSubmit={save} role="dialog" aria-modal="true" aria-labelledby="deadline-form-title"
      className="w-full max-w-md space-y-4 rounded-2xl border border-rule bg-paper p-5 shadow-xl sm:p-6">
      <div className="flex items-baseline justify-between">
        <h2 id="deadline-form-title" className="font-serif text-xl text-ink">{t("deadlineAdd")}</h2>
        <button type="button" onClick={onCancel} aria-label={t("cancel")}
          className="rounded-md p-1 text-muted hover:bg-sheet hover:text-ink"><X size={16} /></button>
      </div>
      <div>
        <Label>{t("deadlineWhatFor")}</Label>
        <input autoFocus value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder={t("deadlineLabelHint")} aria-label={t("deadlineLabel")} className={`w-full ${field}`} />
      </div>

      <Segmented label={t("deadlineAdd")} value={mode} onChange={setMode}
        options={[["notice", "deadlineFromNotice"], ["date", "deadlineKnownDate"]]} />

      {mode === "notice" ? (
        <>
          <div>
            <Label>{service === "electronic" ? t("noticeReached") : t("noticeDate")}</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input type="date" value={received} onChange={(e) => setReceived(e.target.value)}
                aria-label={t("noticeDate")} className={`w-full shrink-0 sm:w-40 ${field}`} />
              <div className="flex min-w-0 flex-1 items-center">
                <div className="w-full"><Segmented label={t("noticeDate")} value={service} onChange={setService} options={SERVICES} /></div>
              </div>
            </div>
          </div>

          <div>
            <Label>{t("periodLength")}</Label>
            <div className="flex gap-1.5">
              <div className={`flex w-24 shrink-0 items-stretch overflow-hidden !p-0 ${field}`}>
                <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/\D/g, ""))}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowUp") { e.preventDefault(); bump(1); }
                    if (e.key === "ArrowDown") { e.preventDefault(); bump(-1); }
                  }}
                  aria-label={t("periodLength")} placeholder="0"
                  className="min-w-0 flex-1 bg-transparent text-center tabular-nums outline-none" />
                <div className="flex flex-col border-l border-rule">
                  <button type="button" onClick={() => bump(1)} aria-label={t("periodMore")}
                    className="flex flex-1 items-center px-1.5 text-muted hover:bg-paper hover:text-ink"><ChevronUp size={13} /></button>
                  <button type="button" onClick={() => bump(-1)} aria-label={t("periodLess")} disabled={!(n > 1)}
                    className="flex flex-1 items-center border-t border-rule px-1.5 text-muted hover:bg-paper hover:text-ink disabled:opacity-30"><ChevronDown size={13} /></button>
                </div>
              </div>
              <div className="min-w-0 flex-1">
                <Segmented label={t("periodLength")} value={unit} onChange={setUnit} options={UNITS} />
              </div>
            </div>
            <div className="mt-2 flex gap-1.5">
              {PRESETS.map(([a, u, key]) => {
                const on = n === a && unit === u;
                return (
                  <button key={key} type="button" onClick={() => { setAmount(String(a)); setUnit(u); }}
                    className={`rounded-full border px-2.5 py-0.5 text-xs pointer-coarse:py-1.5 ${on ? "border-cite bg-cite-soft text-cite" : "border-rule text-muted hover:border-cite hover:text-cite"}`}>
                    {t(key)}
                  </button>
                );
              })}
            </div>
          </div>

          {branchPicker}

          {result && (
            <div className="rounded-lg border border-rule bg-sheet px-3 py-2.5" aria-live="polite">
              <p className="text-xs text-muted">{t("lastDay")}</p>
              <p className="font-serif text-lg leading-snug text-ink">{formatDay(result.due, "long")}</p>
              <ul className="mt-1.5 space-y-0.5 text-[12px] leading-snug text-muted">
                {service === "electronic" && <li>{t("stepServed", { day: formatDay(result.served, "long") })}</li>}
                {result.steps.map((s, i) => <li key={i}>{stepText(s, result.law)}</li>)}
                {result.warnings.map((s, i) => <li key={`w${i}`} className="text-caution">{stepText(s, result.law)}</li>)}
                {notes.map((x) => <li key={x}>{x}</li>)}
              </ul>
            </div>
          )}
        </>
      ) : (
        <>
          <div>
            <Label>{t("deadlineDate")}</Label>
            <input type="date" value={due} min={todayIso()} onChange={(e) => setDue(e.target.value)}
              aria-label={t("deadlineDate")} className={`w-full ${field}`} />
          </div>
          {branchPicker}
        </>
      )}

      <div className="flex items-center justify-end gap-3 pt-1">
        <button type="button" onClick={onCancel} className="px-2 py-2 text-sm text-muted hover:text-ink">{t("cancel")}</button>
        <button type="submit" disabled={!label.trim() || !complete || (mode === "notice" && !result)}
          className="rounded-lg bg-ink px-5 py-2 text-sm text-white disabled:opacity-40">{t("add")}</button>
      </div>
    </form>
    </div>,
    document.body,
  );
}
