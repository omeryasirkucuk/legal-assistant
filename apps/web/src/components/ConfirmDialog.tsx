"use client";

// An in-app question before something that cannot be undone, in place of the browser's
// confirm box (which looks foreign, blocks the page and cannot be styled for a phone).
// `useConfirm` gives an `ask(message)` that resolves to the answer, and the dialog to render.
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t } from "@/lib/i18n";

type Pending = { message: string; action: string; resolve: (yes: boolean) => void };

export function useConfirm(): [React.ReactNode, (message: string, action?: string) => Promise<boolean>] {
  const [pending, setPending] = useState<Pending | null>(null);
  const ask = useCallback((message: string, action = t("delete")) =>
    new Promise<boolean>((resolve) => setPending({ message, action, resolve })), []);
  const answer = (yes: boolean) => {
    pending?.resolve(yes);
    setPending(null);
  };
  const dialog = pending ? <ConfirmDialog message={pending.message} action={pending.action} onAnswer={answer} /> : null;
  return [dialog, ask];
}

function ConfirmDialog({ message, action, onAnswer }: {
  message: string; action: string; onAnswer: (yes: boolean) => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancel.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onAnswer(false); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onAnswer]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/25 px-3 pt-[20vh] sm:px-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onAnswer(false); }}>
      <div role="alertdialog" aria-modal="true" aria-describedby="confirm-message"
        className="w-full max-w-sm rounded-2xl border border-rule bg-paper p-5 shadow-xl">
        <p id="confirm-message" className="text-[15px] leading-relaxed text-ink">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button ref={cancel} onClick={() => onAnswer(false)}
            className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-sheet hover:text-ink">{t("cancel")}</button>
          <button onClick={() => onAnswer(true)}
            className="rounded-lg bg-danger px-4 py-2 text-sm font-medium text-white hover:brightness-110">{action}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
