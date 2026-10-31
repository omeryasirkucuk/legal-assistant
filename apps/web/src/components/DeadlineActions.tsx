"use client";

// What a click on an open deadline's circle offers, so a slip of the mouse does not hide it:
// mark it done, delete it, or leave it as it was.
import { Check, Trash2, X } from "lucide-react";
import { t } from "@/lib/i18n";

export function DeadlineActions({ onDone, onDelete, onCancel }: {
  onDone: () => void; onDelete: () => void; onCancel: () => void;
}) {
  return (
    <div className="mt-2 flex items-center gap-1.5">
      <button onClick={onDone} autoFocus
        className="flex items-center gap-1 rounded-md bg-verified px-2 py-1 text-xs font-medium text-white hover:brightness-95">
        <Check size={12} strokeWidth={3} /> {t("deadlineMarkDone")}
      </button>
      <button onClick={onDelete}
        className="flex items-center gap-1 rounded-md border border-rule bg-sheet px-2 py-1 text-xs text-danger hover:border-danger/40">
        <Trash2 size={12} /> {t("delete")}
      </button>
      <button onClick={onCancel} aria-label={t("cancel")} title={t("cancel")}
        className="rounded-md p-1 text-muted hover:bg-sheet hover:text-ink"><X size={14} /></button>
    </div>
  );
}
