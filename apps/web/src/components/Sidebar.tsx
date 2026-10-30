"use client";

import { useEffect, useState } from "react";
import { api, type ChatSummary, type HistoryHit, type TodayStats, type User } from "@/lib/api";
import { t } from "@/lib/i18n";

type Props = {
  user: User;
  chats: ChatSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
  onSettings: () => void;
  today: TodayStats | null;
};

export function Sidebar({ user, chats, activeId, onSelect, onNew, onDelete, onLogout,
  onSettings, today }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<HistoryHit[] | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits(null);
      return;
    }
    const timer = setTimeout(() => api.searchHistory(q).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-rule bg-paper">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full rounded-md border border-rule bg-sheet px-3 py-2 text-left text-sm font-medium text-ink hover:border-faint"
        >
          {t("newChat")}
        </button>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("searchChats")}
          aria-label={t("searchChats")}
          className="mt-2 w-full rounded-md bg-transparent px-3 py-2 text-sm outline-none placeholder:text-faint focus:bg-sheet"
        />
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {hits ? (
          hits.length === 0 ? (
            <p className="px-3 py-2 text-sm text-faint">{t("noSearchResults")}</p>
          ) : (
            hits.map((h) => (
              <button
                key={h.chat_id}
                onClick={() => onSelect(h.chat_id)}
                className="block w-full rounded-md px-3 py-2 text-left hover:bg-sheet"
              >
                <span className="block truncate text-sm text-ink">{h.title}</span>
                <span className="mt-0.5 line-clamp-2 block text-xs text-muted">
                  {h.snippet.split(/<<|>>/).map((part, i) =>
                    i % 2 ? <mark key={i} className="bg-cite-soft text-ink">{part}</mark> : part,
                  )}
                </span>
              </button>
            ))
          )
        ) : chats.length === 0 ? (
          <p className="px-3 py-2 text-sm text-faint">{t("noChats")}</p>
        ) : (
          chats.map((c) => (
            <div
              key={c.id}
              className={`group flex items-center rounded-md ${c.id === activeId ? "bg-sheet" : "hover:bg-sheet/70"}`}
            >
              <button
                onClick={() => onSelect(c.id)}
                className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm text-ink"
                aria-current={c.id === activeId ? "page" : undefined}
              >
                {c.title}
              </button>
              <button
                onClick={() => onDelete(c.id)}
                aria-label={t("deleteChat")}
                title={t("deleteChat")}
                className="mr-1 hidden rounded px-2 py-1 text-faint hover:text-danger group-hover:block focus-visible:block"
              >
                ×
              </button>
            </div>
          ))
        )}
      </nav>

      <div className="border-t border-rule px-4 py-3 text-sm">
        <span className="block truncate text-muted">{user.name}</span>
        {today && (
          <span className="mt-1 block text-xs text-faint">
            {today.answers
              ? t("todayStats", { answers: today.answers, average: Math.round(today.average_s) })
              : t("todayNone")}
          </span>
        )}
        <div className="mt-2 flex items-center justify-between gap-3">
          {user.is_admin ? (
            <button onClick={onSettings} className="text-faint hover:text-ink">
              {t("settings")}
            </button>
          ) : <span />}
          <button onClick={onLogout} className="text-faint hover:text-ink">
            {t("logout")}
          </button>
        </div>
      </div>
    </aside>
  );
}
