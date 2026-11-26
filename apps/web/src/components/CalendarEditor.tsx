"use client";

import { cloneElement, useEffect, useId, useRef, useState, type FormEvent, type ReactElement } from "react";
import { CalendarClock, Check, Download, ExternalLink, Trash2, X } from "lucide-react";
import { DeadlineForm, BRANCHES } from "@/components/DeadlineForm";
import { api, type Branch, type Matter } from "@/lib/api";
import { type CalendarItem, type CalendarKind, kindOptions, kinds } from "@/lib/calendar";
import { t } from "@/lib/i18n";

const field = "w-full min-w-0 rounded-lg border border-rule bg-sheet px-3 py-2 text-sm text-ink outline-none focus:border-cite";
const button = "inline-flex items-center gap-1.5 rounded-lg border border-rule px-3 py-2 text-sm text-ink hover:bg-desk disabled:opacity-50";
const offsets = [0, 5, 15, 30, 60, 120, 1440, 2880, 10080];

function Field({ label, children }: { label: string; children: ReactElement<{ id?: string }> }) {
  const id = useId();
  return <div className="grid min-w-0 gap-1 text-sm text-muted">
    <label htmlFor={id}>{label}</label>{cloneElement(children, { id })}
  </div>;
}

export function CalendarEditor({ item, day, matters, matterId, initialKind, onClose, onChanged, onOpenMatter }: {
  item?: CalendarItem;
  day: string;
  matters: Matter[];
  matterId?: string;
  initialKind?: CalendarKind;
  onClose: () => void;
  onChanged: (day: string, kind: CalendarKind) => void;
  onOpenMatter?: (id: string) => void;
}) {
  const event = item && item.kind !== "deadline" ? item : undefined;
  const [kind, setKind] = useState<CalendarKind>(item?.kind ?? initialKind ?? "event");
  const [label, setLabel] = useState(item?.label ?? "");
  const [due, setDue] = useState(item?.due ?? day);
  const initialMatter = matters.find((matter) => matter.id === matterId);
  const [linked, setLinked] = useState(item?.matter_id ?? (kind === "deadline" && initialMatter?.closed ? "" : matterId ?? ""));
  const [branch, setBranch] = useState<Branch | "">(item?.kind === "deadline" ? item.branch ?? "" : "");
  const [startTime, setStartTime] = useState(event?.start_time?.slice(0, 5) ?? "");
  const [endTime, setEndTime] = useState(event?.end_time?.slice(0, 5) ?? "");
  const [location, setLocation] = useState(event?.location ?? "");
  const [notes, setNotes] = useState(event?.notes ?? "");
  const [reminder, setReminder] = useState(event?.reminder_minutes?.toString() ?? (!item && initialKind === "reminder" ? "0" : ""));
  const [calculate, setCalculate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const deadline = kind === "deadline";
  const choices = deadline ? matters.filter((matter) => !matter.closed || matter.id === item?.matter_id) : matters;
  const meetingLink = event?.location.match(/^https?:\/\/[^\s]+$/i)?.[0];

  useEffect(() => {
    const node = dialog.current;
    if (!node || calculate) return;
    node.showModal();
    return () => node.close();
  }, [calculate]);

  async function mutate(action: () => Promise<unknown>, changedDay = due) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged(changedDay, kind);
    } catch {
      setError(t("calendarSaveError"));
    } finally {
      setBusy(false);
    }
  }

  function save(e: FormEvent) {
    e.preventDefault();
    if (!label.trim() || !due || (deadline && !linked)) return;
    if (!deadline && endTime && (!startTime || endTime <= startTime)) {
      setError(t("calendarTimeError"));
      return;
    }
    if (deadline) {
      if (item) void mutate(() => api.editDeadline(item.id, { label: label.trim(), due, branch: branch || null }));
      else void mutate(() => api.addDeadline(linked, label.trim(), due, undefined, branch || undefined));
      return;
    }
    const fields = {
      kind, label: label.trim(), due, matter_id: linked || null,
      start_time: startTime || null, end_time: endTime || null,
      location: location.trim(), notes: notes.trim(), reminder_minutes: reminder === "" ? null : Number(reminder),
    };
    void mutate(() => item ? api.editCalendarEvent(item.id, fields) : api.addCalendarEvent(fields));
  }

  if (calculate) return (
    <DeadlineForm matterId={linked} initial={{ label, due, branch }} onCancel={() => setCalculate(false)} onSaved={(savedDay) => onChanged(savedDay, "deadline")} />
  );

  return (
    <dialog ref={dialog} aria-labelledby="calendar-editor-title"
      onCancel={(e) => { e.preventDefault(); if (!busy) onClose(); }}
      className="fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg overflow-y-auto rounded-2xl border border-rule bg-paper p-5 text-ink shadow-xl backdrop:bg-black/35 sm:p-6">
      <form onSubmit={save} className="space-y-4">
        <header className="flex items-center justify-between gap-3">
          <h2 id="calendar-editor-title" className="font-serif text-2xl">{t(item ? "calendarEdit" : "calendarAdd")}</h2>
          <button type="button" disabled={busy} onClick={onClose} aria-label={t("cancel")} className={button}><X size={17} /></button>
        </header>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("calendarType")}>
            <select className={field} value={kind} disabled={item?.kind === "deadline"} onChange={(e) => {
              const value = e.target.value as CalendarKind;
              setKind(value);
              if (value === "deadline" && matters.some((matter) => matter.id === linked && matter.closed)) setLinked("");
              setError("");
              if (value === "reminder" && !reminder) setReminder("0");
            }}>
              {kindOptions.filter((value) => !item || (value === "deadline") === (item.kind === "deadline"))
                .map((value) => <option key={value} value={value}>{t(kinds[value])}</option>)}
            </select>
          </Field>
          <Field label={t(deadline ? "calendarMatterRequired" : "calendarMatter")}>
            <select required={deadline} disabled={item?.kind === "deadline"} className={field} value={linked} onChange={(e) => setLinked(e.target.value)}>
              <option value="">{t(deadline ? "calendarChooseMatter" : "calendarPersonal")}</option>
              {linked && !choices.some((matter) => matter.id === linked) && (
                <option value={linked}>{item?.kind === "deadline" ? item.client : t("calendarLinkedMatter")}</option>
              )}
              {choices.map((matter) => <option key={matter.id} value={matter.id}>
                {[matter.client, matter.subject, matter.case_no].filter(Boolean).join(" · ")}
              </option>)}
            </select>
          </Field>
        </div>

        <Field label={t("calendarLabel")}>
          <input autoFocus required maxLength={200} className={field} value={label}
            placeholder={t(kind === "reminder" ? "calendarReminderHint" : "calendarLabelHint")}
            onChange={(e) => setLabel(e.target.value)} />
        </Field>

        <div className={deadline ? "grid gap-3 sm:grid-cols-2" : "grid grid-cols-2 gap-3 sm:grid-cols-3"}>
          <div className={deadline ? "" : "col-span-2 sm:col-span-1"}>
            <Field label={t("calendarDate")}><input required className={field} type="date" min="1900-01-01"
              max="9999-12-30" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
          </div>
          {deadline ? (
            <Field label={t("branch")}>
              <select className={field} value={branch} onChange={(e) => setBranch(e.target.value as Branch | "")}>
                <option value="">{t("calendarUnspecified")}</option>
                {BRANCHES.map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}
              </select>
            </Field>
          ) : (
            <>
              <Field label={t("calendarStarts")}><input className={field} type="time" value={startTime} onChange={(e) => {
                setStartTime(e.target.value);
                if (!e.target.value) setEndTime("");
              }} /></Field>
              <Field label={t("calendarEnds")}><input className={field} type="time" value={endTime} disabled={!startTime}
                onChange={(e) => setEndTime(e.target.value)} /></Field>
            </>
          )}
        </div>

        {!deadline && (
          <>
            <p className="text-xs text-muted">{t("calendarTimeZone")}</p>
            <Field label={t("calendarAlert")}>
              <select className={field} value={reminder} onChange={(e) => setReminder(e.target.value)}>
                <option value="">{t("calendarNoAlert")}</option>
                {[...new Set([...offsets, ...(reminder ? [Number(reminder)] : [])])].sort((a, b) => a - b)
                  .map((minutes) => <option key={minutes} value={minutes}>
                    {minutes === 0 ? t(startTime ? "calendarAlertAtStart" : "calendarAlertAllDay")
                      : minutes % 1440 === 0 ? t("calendarAlertDays", { n: minutes / 1440 })
                      : minutes % 60 === 0 ? t("calendarAlertHours", { n: minutes / 60 })
                      : t("calendarAlertMinutes", { n: minutes })}
                  </option>)}
              </select>
            </Field>
            {reminder !== "" && <p className="text-xs text-muted">
              {t(startTime ? "calendarAlertDelivery" : "calendarAlertAllDayDelivery")}
            </p>}
            <Field label={t("calendarLocation")}><input className={field} maxLength={300} value={location}
              onChange={(e) => setLocation(e.target.value)} /></Field>
            {meetingLink && <a href={meetingLink} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-cite hover:underline">
              <ExternalLink size={14} /> {t("calendarOpenLocation")}
            </a>}
            <Field label={t("calendarNotes")}><textarea className={field} rows={2} maxLength={10000} value={notes}
              onChange={(e) => setNotes(e.target.value)} /></Field>
          </>
        )}

        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex flex-wrap items-center gap-2 border-t border-rule pt-4">
          {item && (
            <>
              <button type="button" disabled={busy} className={button} onClick={() => void mutate(
                () => item.kind === "deadline" ? api.editDeadline(item.id, { done: !item.done })
                  : api.updateCalendarEvent(item.id, { done: !item.done }), item.due)}>
                <Check size={15} /> {t(item.done ? "deadlineUndo" : "calendarComplete")}
              </button>
              {item.matter_id && onOpenMatter && (
                <button type="button" disabled={busy} className={button} onClick={() => onOpenMatter(item.matter_id!)}>
                  <ExternalLink size={14} /> {t("calendarOpenMatter")}
                </button>
              )}
              {event && <a href={api.calendarEventIcsUrl(event.id)} className={button}>
                <Download size={15} /> {t("calendarExport")}
              </a>}
              {!confirmDelete && <button type="button" disabled={busy} className={button} onClick={() => setConfirmDelete(true)}>
                <Trash2 size={14} /> {t("delete")}
              </button>}
            </>
          )}
          {!item && deadline && linked && (
            <button type="button" className={button} onClick={() => setCalculate(true)}>
              <CalendarClock size={15} /> {t("deadlineFromNotice")}
            </button>
          )}
          {!confirmDelete && <button disabled={busy} className="ml-auto rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-50">
            {t("save")}
          </button>}
        </div>
        {item && confirmDelete && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-danger/40 p-3">
            <p className="w-full text-sm">{t("calendarDeleteConfirm")}</p>
            <button type="button" disabled={busy} className={button} onClick={() => setConfirmDelete(false)}>{t("cancel")}</button>
            <button type="button" disabled={busy} className="rounded-lg bg-danger px-3 py-2 text-sm text-white disabled:opacity-50"
              onClick={() => void mutate(() => item.kind === "deadline" ? api.deleteDeadline(item.id) : api.deleteCalendarEvent(item.id), item.due)}>
              {t("delete")}
            </button>
          </div>
        )}
      </form>
    </dialog>
  );
}
