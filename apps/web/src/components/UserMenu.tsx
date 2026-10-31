"use client";

// The account menu, opened from the user's row (or their initials on the collapsed rail):
// who is signed in, today's use, the writing style, model settings for admins, sign out.
import { useEffect, useRef } from "react";
import { LogOut, PenLine, Settings } from "lucide-react";
import type { TodayStats, User } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import { t } from "@/lib/i18n";

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toLocaleUpperCase("tr")).join("");
}

type Props = {
  user: User;
  today: TodayStats | null;
  onStyle: () => void;
  onSettings: () => void;
  onLogout: () => void;
  onClose: () => void;
  className?: string;
};

export function UserMenu({ user, today, onStyle, onSettings, onLogout, onClose, className = "" }: Props) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && onClose();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    box.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  const item = "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm text-ink hover:bg-paper";
  const pick = (fn: () => void) => () => { onClose(); fn(); };

  return (
    <div ref={box} role="menu" aria-label={t("userMenu")}
      className={`absolute z-30 w-64 rounded-xl border border-rule bg-sheet p-1.5 shadow-xl ${className}`}>
      <div className="px-3 pb-2 pt-1.5">
        <p className="truncate text-sm text-muted">{user.email}</p>
        {today && today.answers > 0 && (
          <p className="mt-0.5 text-xs text-faint">
            {t("usageToday", { answers: today.answers, cost: formatUsd(today.cost_usd) })}
          </p>
        )}
      </div>
      <div className="border-t border-rule pt-1.5">
        <button role="menuitem" onClick={pick(onStyle)} className={item}>
          <PenLine size={16} className="text-muted" /> {t("myPetitions")}
        </button>
        {user.is_admin && (
          <button role="menuitem" onClick={pick(onSettings)} className={item}>
            <Settings size={16} className="text-muted" /> {t("modelSettings")}
          </button>
        )}
      </div>
      <div className="mt-1.5 border-t border-rule pt-1.5">
        <button role="menuitem" onClick={pick(onLogout)} className={item}>
          <LogOut size={16} className="text-muted" /> {t("logout")}
        </button>
      </div>
    </div>
  );
}
