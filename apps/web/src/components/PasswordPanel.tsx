"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";

const fields = [
  { name: "current", label: "currentPassword", autoComplete: "current-password" },
  { name: "next", label: "newPassword", autoComplete: "new-password", minLength: 8, maxLength: 256 },
  { name: "confirm", label: "confirmPassword", autoComplete: "new-password", minLength: 8, maxLength: 256 },
] as const;

export function PasswordPanel({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const current = String(form.get("current"));
    const next = String(form.get("next"));
    if (next !== form.get("confirm")) {
      setError(t("passwordMismatch"));
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(current, next);
      setSaved(true);
    } catch (e) {
      const status = e instanceof ApiError ? e.status : null;
      setError(t(status === 403 ? "incorrectPassword"
        : status === 409 ? "passwordMustDiffer"
        : status === 401 ? "passwordSessionExpired" : "passwordChangeFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <dialog ref={dialog} onCancel={(event) => { if (saving) event.preventDefault(); else onClose(); }}
      onClick={(event) => { if (!saving && event.target === event.currentTarget) onClose(); }}
      aria-labelledby="password-title"
      className="m-auto max-h-[90dvh] w-[min(92vw,28rem)] max-w-none overflow-auto rounded-xl border border-rule bg-paper p-0 text-ink shadow-xl backdrop:bg-black/35">
      <section>
        <header className="flex items-center justify-between gap-4 border-b border-rule px-5 py-4">
          <h2 id="password-title" className="font-serif text-2xl">{t("changePassword")}</h2>
          <button type="button" onClick={onClose} disabled={saving} aria-label={t("close")}
            className="rounded-md p-2 text-muted hover:bg-sheet hover:text-ink disabled:opacity-60">
            <X size={20} />
          </button>
        </header>
        {saved ? (
          <p role="status" className="p-5 text-sm text-verified">{t("passwordChanged")}</p>
        ) : (
          <form onSubmit={submit} className="space-y-4 p-5">
            {fields.map(({ label, ...field }) => (
              <label key={field.name} className="block text-sm text-muted">
                {t(label)}
                <input {...field} type="password" required readOnly={saving}
                  className="mt-1 block w-full rounded-md border border-rule bg-sheet px-3 py-2.5 text-base text-ink outline-none focus:border-cite" />
              </label>
            ))}
            <p className="text-sm text-muted">{t("passwordChangeHint")}</p>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <button type="submit" disabled={saving}
              className="w-full rounded-md bg-ink py-2.5 text-sm font-medium text-white disabled:opacity-60">
              {t("save")}
            </button>
          </form>
        )}
      </section>
    </dialog>
  );
}
