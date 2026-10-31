"use client";

// The desk: new chat, the calendar, the lawyer's files, search (files, their documents and chats), the case files (each with its next deadline), the
// chats that belong to no file grouped by day, and the account. Collapses to a rail of icons
// that keeps the main actions one click away.
import { useEffect, useRef, useState } from "react";
import { CalendarDays, FolderOpen, FolderPlus, PanelLeft, Search, SquarePen, X } from "lucide-react";
import { SearchResults } from "@/components/SearchResults";
import { api, type ChatSummary, type DeskHits, type Matter, type TodayStats, type User } from "@/lib/api";
import { daysUntil, urgency } from "@/lib/dates";
import { t } from "@/lib/i18n";
import { UserMenu, initials } from "./UserMenu";

type Props = {
  user: User;
  chats: ChatSummary[];
  matters: Matter[];
  activeId: string | null;
  activeMatterId: string | null;
  calendarOpen: boolean;
  onOpenMatter: (id: string) => void;
  onNewMatter: () => void;
  onCalendar: () => void;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
  onSettings: () => void;
  onStyle: () => void;
  onFiles: () => void;
  filesOpen?: boolean;
  today: TodayStats | null;
};

type Group = "today" | "yesterday" | "thisWeek" | "older";

function groupOf(iso: string, now: Date): Group {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(now) - day(new Date(iso))) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : days < 7 ? "thisWeek" : "older";
}

function RailButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} aria-label={label} title={label}
      className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-sheet hover:text-ink">
      {children}
    </button>
  );
}

function Avatar({ name }: { name: string }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-cite font-sans text-xs font-semibold text-white">
      {initials(name)}
    </span>
  );
}

// A file's next deadline, shown beside it when it is near (two weeks) or missed.
function DeadlineBadge({ matter }: { matter: Matter }) {
  const next = matter.next_deadline;
  if (!next) return null;
  const days = daysUntil(next.due);
  if (days > 14) return null;
  const u = urgency(days);
  const tone = u === "overdue" ? "bg-danger text-white" : u === "later" ? "bg-sheet text-muted" : "bg-caution-soft text-caution";
  return (
    <span title={next.label} className={`shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium tabular-nums ${tone}`}>
      {days < 0 ? t("badgeOverdue") : days === 0 ? t("badgeToday") : t("badgeDays", { n: days })}
    </span>
  );
}

export function Sidebar(props: Props) {
  const { user, chats, matters, activeId, activeMatterId, collapsed, onToggle, onSelect, onNew, onDelete, today } = props;
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DeskHits | null>(null);
  const [menu, setMenu] = useState(false);
  const searchBox = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits(null);
      return;
    }
    const timer = setTimeout(() => api.searchDesk(q).then(setHits).catch(() => setHits({ chats: [], matters: [], documents: [] })), 250);
    return () => clearTimeout(timer);
  }, [query]);

  function openSearch() {
    if (collapsed) onToggle();
    setTimeout(() => searchBox.current?.focus(), 50);
  }

  const menuEl = menu && (
    <UserMenu user={user} today={today} onStyle={props.onStyle}
      onSettings={props.onSettings}
      onLogout={props.onLogout} onClose={() => setMenu(false)}
      className={collapsed ? "bottom-2 left-14" : "bottom-16 left-2"} />
  );

  if (collapsed) {
    return (
      <aside className="relative flex h-full w-14 shrink-0 flex-col items-center gap-1 border-r border-rule bg-desk py-3">
        <RailButton label={t("expandSidebar")} onClick={onToggle}><PanelLeft size={18} /></RailButton>
        <RailButton label={t("newChat")} onClick={onNew}><SquarePen size={18} /></RailButton>
        <RailButton label={t("calendar")} onClick={props.onCalendar}><CalendarDays size={18} /></RailButton>
        <RailButton label={t("myFiles")} onClick={props.onFiles}><FolderOpen size={18} /></RailButton>
        <RailButton label={t("searchDesk")} onClick={openSearch}><Search size={18} /></RailButton>
        <RailButton label={t("matterNew")} onClick={props.onNewMatter}><FolderPlus size={18} /></RailButton>
        <button onClick={() => setMenu((m) => !m)} onMouseDown={(e) => e.stopPropagation()}
          aria-label={t("userMenu")} aria-expanded={menu}
          className="mt-auto rounded-full p-0.5 hover:ring-2 hover:ring-rule">
          <Avatar name={user.name} />
        </button>
        {menuEl}
      </aside>
    );
  }

  const now = new Date();
  const loose = chats.filter((c) => !c.matter_id);
  const openMatters = matters.filter((m) => !m.closed);
  const groups: Array<[Group, ChatSummary[]]> = (["today", "yesterday", "thisWeek", "older"] as Group[])
    .map((g) => [g, loose.filter((c) => groupOf(c.updated_at, now) === g)] as [Group, ChatSummary[]])
    .filter(([, list]) => list.length > 0);

  return (
    <aside className="relative flex h-full w-72 shrink-0 flex-col border-r border-rule bg-desk">
      <div className="flex items-center justify-between px-3 pb-2 pt-3">
        <RailButton label={t("collapseSidebar")} onClick={onToggle}><PanelLeft size={18} /></RailButton>
      </div>
      <div className="space-y-0.5 px-2">
        <button onClick={onNew}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-ink hover:bg-sheet">
          <SquarePen size={17} className="text-muted" /> {t("newChat")}
        </button>
        <button onClick={props.onCalendar} aria-current={props.calendarOpen ? "page" : undefined}
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink ${props.calendarOpen ? "bg-sheet shadow-sm" : "hover:bg-sheet"}`}>
          <CalendarDays size={17} className="text-muted" /> {t("calendar")}
        </button>
        <button onClick={props.onFiles} aria-current={props.filesOpen ? "page" : undefined}
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink ${props.filesOpen ? "bg-sheet shadow-sm" : "hover:bg-sheet"}`}>
          <FolderOpen size={17} className="text-muted" /> {t("myFiles")}
        </button>
        <label className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink focus-within:bg-sheet hover:bg-sheet">
          <Search size={17} className="shrink-0 text-muted" />
          <input ref={searchBox} value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={t("searchChats")} aria-label={t("searchDesk")} title={t("searchDesk")}
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted focus-visible:outline-none" />
          {query && (
            <button onClick={() => setQuery("")} aria-label={t("close")} className="text-faint hover:text-ink">
              <X size={14} />
            </button>
          )}
        </label>
      </div>

      <nav className="mt-3 min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {hits ? (
          <SearchResults hits={hits} onOpenMatter={props.onOpenMatter} onOpenChat={onSelect} />
        ) : (
          <>
          <div className="mb-4">
            <div className="flex items-center justify-between px-3 pb-1 pt-2">
              <p className="text-xs font-medium text-faint">{t("matters")}</p>
              <button onClick={props.onNewMatter} aria-label={t("matterNew")} title={t("matterNew")}
                className="rounded p-0.5 text-faint hover:bg-sheet hover:text-ink">
                <FolderPlus size={15} />
              </button>
            </div>
            {openMatters.length === 0 ? (
              <button onClick={props.onNewMatter} className="w-full rounded-lg px-3 py-1.5 text-left text-sm text-muted hover:bg-sheet">
                {t("matterFirst")}
              </button>
            ) : openMatters.map((m) => (
              <button key={m.id} onClick={() => props.onOpenMatter(m.id)}
                aria-current={m.id === activeMatterId ? "page" : undefined}
                className={`flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-left ${m.id === activeMatterId ? "bg-sheet shadow-sm" : "hover:bg-sheet/70"}`}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{m.client}</span>
                  {m.subject && <span className="block truncate text-xs text-faint">{m.subject}</span>}
                </span>
                <DeadlineBadge matter={m} />
              </button>
            ))}
          </div>
          {loose.length === 0 ? (
            <p className="px-3 py-2 text-sm text-faint">{t("noChats")}</p>
          ) : groups.map(([g, list]) => (
            <div key={g} className="mb-3">
              <p className="px-3 pb-1 pt-2 text-xs font-medium text-faint">{t(g)}</p>
              {list.map((c) => (
                <div key={c.id}
                  className={`group flex items-center rounded-lg ${c.id === activeId ? "bg-sheet shadow-sm" : "hover:bg-sheet/70"}`}>
                  <button onClick={() => onSelect(c.id)} aria-current={c.id === activeId ? "page" : undefined}
                    className="min-w-0 flex-1 truncate px-3 py-1.5 text-left text-sm text-ink">
                    {c.title}
                  </button>
                  <button onClick={() => onDelete(c.id)} aria-label={t("deleteChat")} title={t("deleteChat")}
                    className="mr-1 hidden rounded p-1 text-faint hover:text-danger group-hover:block focus-visible:block">
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          ))}
          </>
        )}
      </nav>

      <div className="border-t border-rule p-2">
        <button onClick={() => setMenu((m) => !m)} onMouseDown={(e) => e.stopPropagation()}
          aria-label={t("userMenu")} aria-expanded={menu}
          className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-sheet">
          <Avatar name={user.name} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink">{user.name}</span>
            <span className="block truncate text-xs text-faint">{user.email}</span>
          </span>
        </button>
      </div>
      {menuEl}
    </aside>
  );
}
