"use client";

// Opening or editing a case file: whose file it is (the only thing required) and, as far as
// known, the subject, the other side, the court and the docket number.
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import type { MatterFields } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";

const FIELDS: Array<{ key: keyof MatterFields; label: MessageKey; hint: MessageKey }> = [
  { key: "client", label: "matterClient", hint: "matterClientHint" },
  { key: "subject", label: "matterSubject", hint: "matterSubjectHint" },
  { key: "opponent", label: "matterOpponent", hint: "matterOpponentHint" },
  { key: "court", label: "matterCourt", hint: "matterCourtHint" },
  { key: "case_no", label: "matterCaseNo", hint: "matterCaseNoHint" },
];

const EMPTY: MatterFields = { client: "", subject: "", opponent: "", court: "", case_no: "" };

export function MatterForm({ initial, onSave, onClose }: {
  initial?: MatterFields;
  onSave: (fields: MatterFields) => Promise<void>;
  onClose: () => void;
}) {
  const [fields, setFields] = useState<MatterFields>(initial ?? EMPTY);
  const [saving, setSaving] = useState(false);
  const first = useRef<HTMLInputElement>(null);

  useEffect(() => {
    first.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!fields.client.trim() || saving) return;
    setSaving(true);
    try {
      await onSave({ ...fields, client: fields.client.trim() });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/25 px-4 pt-[12vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="matter-form-title"
        className="w-full max-w-md rounded-2xl bg-sheet p-6 shadow-2xl">
        <div className="flex items-start justify-between">
          <h2 id="matter-form-title" className="font-serif text-2xl text-ink">
            {initial ? t("matterEdit") : t("matterNew")}
          </h2>
          <button type="button" onClick={onClose} aria-label={t("close")}
            className="-mr-1.5 rounded-md p-1.5 text-faint hover:bg-paper hover:text-ink">
            <X size={18} />
          </button>
        </div>
        <div className="mt-5 space-y-4">
          {FIELDS.map(({ key, label, hint }, i) => (
            <label key={key} className="block">
              <span className="text-sm font-medium text-ink">{t(label)}</span>
              <input ref={i === 0 ? first : undefined} value={fields[key]}
                onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
                placeholder={t(hint)} required={key === "client"}
                className="mt-1 w-full rounded-lg border border-rule bg-sheet px-3 py-2 text-[15px] text-ink outline-none placeholder:text-faint focus:border-cite" />
            </label>
          ))}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose}
            className="rounded-lg px-3.5 py-2 text-sm text-muted hover:bg-paper hover:text-ink">
            {t("cancel")}
          </button>
          <button type="submit" disabled={!fields.client.trim() || saving}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
            {initial ? t("save") : t("matterCreate")}
          </button>
        </div>
      </form>
    </div>
  );
}
