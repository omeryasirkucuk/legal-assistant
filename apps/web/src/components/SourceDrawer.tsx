"use client";

import { useEffect, useRef } from "react";
import type { Evidence, SourceText } from "@/lib/api";
import { t } from "@/lib/i18n";

type Props = {
  evidence: Evidence | null;
  number: number;
  source: SourceText | null;
  onClose: () => void;
};

export function SourceDrawer({ evidence, number, source, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!evidence) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [evidence, onClose]);

  if (!evidence) return null;

  return (
    <div className="fixed inset-0 z-30 flex justify-end" role="dialog" aria-modal="true" aria-label={evidence.citation}>
      <button className="flex-1 bg-ink/20" aria-label={t("close")} onClick={onClose} />
      <section className="flex h-full w-full max-w-2xl flex-col bg-sheet shadow-2xl">
        <header className="flex items-start gap-4 border-b border-rule px-6 py-5">
          <span className="mt-0.5 text-sm font-semibold text-cite">{number || ""}</span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[15px] font-semibold leading-snug text-ink">{evidence.citation}</h2>
            <div className="mt-1 flex flex-wrap gap-x-4 text-sm text-muted">
              <a href={evidence.url} target="_blank" rel="noreferrer" className="text-cite hover:underline">
                {t("openOfficial")}
              </a>
              {source && (
                <span>{t("fetchedAt", { date: new Date(source.fetched_at).toLocaleString("tr-TR") })}</span>
              )}
            </div>
          </div>
          <button ref={closeRef} onClick={onClose} className="rounded px-2 text-xl leading-none text-faint hover:text-ink" aria-label={t("close")}>
            ×
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {source ? (
            <div className="mx-auto max-w-[38rem] whitespace-pre-wrap font-serif text-[0.975rem] leading-[1.75] text-ink">
              {source.text}
            </div>
          ) : (
            <p className="text-sm text-muted">{t("loadingSource")}</p>
          )}
        </div>
      </section>
    </div>
  );
}
