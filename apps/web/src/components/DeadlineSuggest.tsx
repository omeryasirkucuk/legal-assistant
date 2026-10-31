"use client";

// Under an answer in a case file that computed a period: put its last day in the file's
// deadlines with one click. When the judicial recess may or may not apply, both days are
// offered, as the answer explains which one holds.
import { useState } from "react";
import { CalendarPlus, Check } from "lucide-react";
import { api, type ComputedDeadline, type Deadline } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import { t } from "@/lib/i18n";

export function DeadlineSuggest({ matterId, messageId, computed, existing, onAdded }: {
  matterId: string;
  messageId: string;
  computed: ComputedDeadline[];
  existing: Deadline[];
  onAdded: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const added = (label: string, due: string) =>
    existing.some((d) => d.message_id === messageId && d.label === label && d.due === due);

  async function add(label: string, due: string) {
    setBusy(`${label}${due}`);
    try {
      await api.addDeadline(matterId, label, due, messageId);
      onAdded();
    } finally {
      setBusy(null);
    }
  }

  const options = computed.flatMap((c) => c.without_recess
    ? [{ label: c.label, due: c.due, note: t("withRecess") },
       { label: c.label, due: c.without_recess, note: t("withoutRecess") }]
    : [{ label: c.label, due: c.due, note: "" }]);

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {options.map((o) => {
        const done = added(o.label, o.due);
        return (
          <button key={`${o.label}${o.due}`} disabled={done || busy !== null} onClick={() => add(o.label, o.due)}
            className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${
              done ? "border-verified/40 bg-verified-soft text-verified" : "border-rule bg-sheet text-ink hover:border-cite hover:text-cite"}`}>
            {done ? <Check size={14} /> : <CalendarPlus size={14} />}
            <span>{done ? t("deadlineAdded") : t("deadlineAddToMatter")}: {o.label}, {formatDay(o.due)}</span>
            {o.note && <span className="text-xs text-faint">({o.note})</span>}
          </button>
        );
      })}
    </div>
  );
}
