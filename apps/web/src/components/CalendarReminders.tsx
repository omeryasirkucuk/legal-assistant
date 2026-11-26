"use client";

import { useEffect, useState } from "react";
import { Bell, X } from "lucide-react";
import { api, type DueReminder } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import { t } from "@/lib/i18n";

export function CalendarReminders({ version, onOpen }: { version: number; onOpen: (id: string) => void }) {
  const [reminders, setReminders] = useState<DueReminder[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let live = true;
    let request = 0;
    async function load() {
      if (document.visibilityState === "hidden") return;
      const id = ++request;
      try {
        const rows = await api.dueReminders();
        if (live && id === request) {
          setReminders(rows);
          setDismissed((current) => new Set([...current].filter((key) => rows.some((row) => reminderKey(row) === key))));
        }
      } catch {
        // The next poll retries without clearing an already visible reminder.
      }
    }
    void load();
    const interval = window.setInterval(load, 30_000);
    document.addEventListener("visibilitychange", load);
    return () => {
      live = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", load);
    };
  }, [version]);

  const pending = reminders.filter((row) => !dismissed.has(reminderKey(row)));
  const reminder = pending[0];
  if (!reminder) return null;

  async function dismiss(row: DueReminder) {
    setBusy(true);
    setError(false);
    try {
      await api.updateCalendarEvent(row.id, { dismiss_reminder_at: row.remind_at });
      setDismissed((current) => new Set(current).add(reminderKey(row)));
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label={t("calendarReminderNow")} className="chat-reminder sticky top-0 z-10 px-4 py-2">
      <div className="mx-auto flex max-w-[58rem] items-start gap-2 rounded-xl border border-cite/25 bg-sheet p-3 shadow-sm">
        <Bell size={17} className="mt-0.5 shrink-0 text-cite" />
        <div className="min-w-0 flex-1" aria-live="polite">
          <p className="text-xs text-muted">{t("calendarReminderNow")}{pending.length > 1 && ` · ${t("calendarMoreAlerts", { n: pending.length - 1 })}`}</p>
          <button type="button" onClick={() => onOpen(reminder.id)}
            className="block max-w-full truncate rounded text-left text-sm font-medium text-cite hover:underline">
            {reminder.label}
          </button>
          <p className="text-xs text-muted">{formatDay(reminder.due, "long")}</p>
          {error && <p role="alert" className="mt-1 text-xs text-danger">{t("calendarSaveError")}</p>}
        </div>
        <button type="button" disabled={busy} onClick={() => void dismiss(reminder)}
          aria-label={t("calendarDismiss")} title={t("calendarDismiss")}
          className="shrink-0 rounded-md p-2 text-muted hover:bg-desk hover:text-ink disabled:opacity-50">
          <X size={17} />
        </button>
      </div>
    </section>
  );
}

function reminderKey(row: DueReminder) {
  return `${row.id}:${row.remind_at}`;
}
