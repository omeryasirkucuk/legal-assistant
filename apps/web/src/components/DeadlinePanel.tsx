"use client";

// A case file's deadlines: the next one set large, as days left (the one figure that must
// not be missed), then the rest in date order with a tick for done, and a line to add one.
import { useState } from "react";
import { Check, Plus, Trash2 } from "lucide-react";
import { DeadlineActions } from "@/components/DeadlineActions";
import { DeadlineForm, branchName } from "@/components/DeadlineForm";
import { api, type Deadline } from "@/lib/api";
import { daysUntil, formatDay, urgency, type Urgency } from "@/lib/dates";
import { t } from "@/lib/i18n";

const TONE: Record<Urgency, string> = {
  overdue: "text-danger", today: "text-caution", soon: "text-caution", later: "text-ink",
};

export function daysLeftText(days: number): string {
  return days < 0 ? t("daysOverdue", { n: -days }) : days === 0 ? t("dueToday") : t("daysLeft", { n: days });
}

function NextDeadline({ d }: { d: Deadline }) {
  const days = daysUntil(d.due);
  const tone = TONE[urgency(days)];
  return (
    <div>
      <p className="text-xs text-muted">{t("nextDeadline")}</p>
      {days === 0 ? (
        <p className={`mt-1 font-serif text-[2.2rem] leading-none ${tone}`}>{t("dueToday")}</p>
      ) : (
        <p className={`mt-1 flex items-baseline gap-2 ${tone}`}>
          <span className="font-serif text-[2.6rem] leading-none tabular-nums">{Math.abs(days)}</span>
          <span className="text-[15px]">{t("dayUnit")} {days < 0 ? t("passed") : t("left")}</span>
        </p>
      )}
      <p className="mt-3 text-[15px] font-medium leading-snug text-ink">{d.label}</p>
      <p className="text-sm text-muted">{formatDay(d.due, "long")}{d.branch && ` · ${branchName(d.branch)}`}</p>
    </div>
  );
}

export function DeadlinePanel({ matterId, deadlines, onChanged }: {
  matterId: string; deadlines: Deadline[]; onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [asking, setAsking] = useState<string | null>(null);   // the open deadline whose circle was clicked
  const open = deadlines.filter((d) => !d.done);
  const done = deadlines.filter((d) => d.done);
  const next = open.find((d) => daysUntil(d.due) < 0) ?? open[0];

  async function toggle(d: Deadline) {
    setAsking(null);
    await api.editDeadline(d.id, { done: !d.done });
    onChanged();
  }

  async function remove(d: Deadline) {
    setAsking(null);
    await api.deleteDeadline(d.id);
    onChanged();
  }

  const row = (d: Deadline) => {
    const days = daysUntil(d.due);
    return (
      <li key={d.id} className="group flex items-start gap-3 py-2">
        <button onClick={() => (d.done ? toggle(d) : setAsking(asking === d.id ? null : d.id))}
          aria-pressed={d.done} aria-expanded={d.done ? undefined : asking === d.id}
          aria-label={d.done ? t("deadlineUndo") : t("deadlineDone")}
          className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
            d.done ? "border-verified bg-verified text-white"
              : asking === d.id ? "border-ink ring-2 ring-ink/10" : "border-faint hover:border-ink"}`}>
          {d.done && <Check size={10} strokeWidth={3} />}
        </button>
        <span className="min-w-0 flex-1">
          <span className={`block text-sm leading-snug ${d.done ? "text-faint line-through" : "text-ink"}`}>{d.label}</span>
          <span className={`block text-xs ${d.done ? "text-faint" : TONE[urgency(days)] === "text-ink" ? "text-muted" : TONE[urgency(days)]}`}>
            {formatDay(d.due)}{d.branch && ` · ${branchName(d.branch)}`}{!d.done && ` · ${daysLeftText(days)}`}
          </span>
          {asking === d.id && (
            <DeadlineActions onDone={() => toggle(d)} onDelete={() => remove(d)} onCancel={() => setAsking(null)} />
          )}
        </span>
        <button onClick={() => remove(d)} aria-label={t("deadlineDelete")} hidden={asking === d.id}
          className="rounded p-1 text-faint opacity-0 hover:text-danger group-hover:opacity-100 focus-visible:opacity-100">
          <Trash2 size={13} />
        </button>
      </li>
    );
  };

  return (
    <div>
      {next ? <NextDeadline d={next} /> : <p className="text-sm leading-relaxed text-muted">{t("noDeadlines")}</p>}

      {open.length > 1 && (
        <ul className="mt-5 divide-y divide-rule border-t border-rule">
          {open.filter((d) => d !== next).map(row)}
        </ul>
      )}

      {adding ? (
        <DeadlineForm matterId={matterId} onCancel={() => setAdding(false)}
          onSaved={() => { setAdding(false); onChanged(); }} />
      ) : (
        <button onClick={() => setAdding(true)}
          className="mt-4 flex items-center gap-1.5 text-sm text-cite hover:underline">
          <Plus size={14} /> {t("deadlineAdd")}
        </button>
      )}

      {done.length > 0 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-xs text-muted hover:text-ink">{t("deadlinesDone", { n: done.length })}</summary>
          <ul className="mt-1 divide-y divide-rule">{done.map(row)}</ul>
        </details>
      )}
    </div>
  );
}
