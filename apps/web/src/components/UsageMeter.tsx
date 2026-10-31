"use client";

// Today's use as a small ring under the message box (share of the daily limit); a click opens
// the details: answers, spend against the limit, and the file space used.
import { useEffect, useRef, useState } from "react";
import { api, type FileUsage, type TodayStats } from "@/lib/api";
import { formatBytes, formatUsd } from "@/lib/format";
import { t } from "@/lib/i18n";

function Ring({ share }: { share: number }) {
  const r = 6.5;
  const c = 2 * Math.PI * r;
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden className="-rotate-90">
      <circle cx="8" cy="8" r={r} fill="none" stroke="var(--color-rule)" strokeWidth="2.5" />
      <circle cx="8" cy="8" r={r} fill="none" strokeWidth="2.5" strokeLinecap="round"
        stroke={share >= 0.9 ? "var(--color-caution)" : "var(--color-cite)"}
        strokeDasharray={`${c * Math.min(1, share)} ${c}`} />
    </svg>
  );
}

export function UsageMeter({ today, onOpenFiles }: { today: TodayStats | null; onOpenFiles: () => void }) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<FileUsage | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const share = today && today.budget_usd ? today.cost_usd / today.budget_usd : 0;

  useEffect(() => {
    if (!open) return;
    api.fileUsage().then(setFiles).catch(() => {});
    const away = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  if (!today) return null;
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} onMouseDown={(e) => e.stopPropagation()}
        aria-expanded={open} aria-label={t("usage")}
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted hover:bg-sheet hover:text-ink">
        <Ring share={share} /> %{Math.round(share * 100)}
      </button>
      {open && (
        <div className="absolute bottom-full right-0 z-30 mb-2 w-72 rounded-xl border border-rule bg-sheet p-4 text-sm shadow-xl">
          <p className="font-medium text-ink">{t("usageAnswers", { answers: today.answers })}</p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-paper">
            <div className="h-full rounded-full bg-cite" style={{ width: `${Math.min(100, share * 100)}%` }} />
          </div>
          <p className="mt-1.5 text-muted">
            {t("usageSpend", { cost: formatUsd(today.cost_usd), budget: formatUsd(today.budget_usd) })}
          </p>
          <p className="mt-0.5 text-xs text-faint">{t("usageResets")}</p>
          {files && (
            <>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-paper">
                <div className="h-full rounded-full bg-verified"
                  style={{ width: `${Math.min(100, (files.used_bytes / files.quota_bytes) * 100)}%` }} />
              </div>
              <p className="mt-1.5 text-muted">
                {t("usageStorage", { used: formatBytes(files.used_bytes), quota: formatBytes(files.quota_bytes) })}
              </p>
            </>
          )}
          <button onClick={() => { setOpen(false); onOpenFiles(); }}
            className="mt-3 text-sm text-cite underline-offset-2 hover:underline">
            {t("openFiles")}
          </button>
        </div>
      )}
    </div>
  );
}
