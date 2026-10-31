"use client";

// What the sidebar search found, in three groups: case files (by their details and notes),
// documents in them (by name or text), and chats. Matches are marked in each snippet.
import { FileText, Folder, MessageSquare } from "lucide-react";
import type { DeskHits } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";

function Marked({ text }: { text: string }) {
  return (
    <span className="mt-0.5 line-clamp-2 block text-xs text-muted">
      {text.split(/<<|>>/).map((part, i) =>
        i % 2 ? <mark key={i} className="bg-cite-soft text-ink">{part}</mark> : part,
      )}
    </span>
  );
}

function Group({ title, children }: { title: MessageKey; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <p className="px-3 pb-1 pt-2 text-xs font-medium text-faint">{t(title)}</p>
      {children}
    </div>
  );
}

const row = "flex w-full gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-sheet";

export function SearchResults({ hits, onOpenMatter, onOpenChat }: {
  hits: DeskHits;
  onOpenMatter: (id: string) => void;
  onOpenChat: (id: string) => void;
}) {
  if (!hits.matters.length && !hits.documents.length && !hits.chats.length) {
    return <p className="px-3 py-2 text-sm text-faint">{t("noSearchResults")}</p>;
  }
  return (
    <>
      {hits.matters.length > 0 && (
        <Group title="matters">
          {hits.matters.map((m) => (
            <button key={m.matter_id} onClick={() => onOpenMatter(m.matter_id)} className={row}>
              <Folder size={14} className="mt-0.5 shrink-0 text-faint" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">
                  {m.client}{m.closed && <span className="ml-1.5 text-xs text-faint">{t("matterClosedTag")}</span>}
                </span>
                <Marked text={m.snippet} />
              </span>
            </button>
          ))}
        </Group>
      )}
      {hits.documents.length > 0 && (
        <Group title="searchDocuments">
          {hits.documents.map((d) => (
            <button key={d.file_id} onClick={() => onOpenMatter(d.matter_id)} className={row}>
              <FileText size={14} className="mt-0.5 shrink-0 text-faint" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{d.name}</span>
                <span className="block truncate text-xs text-faint">{d.client}</span>
                <Marked text={d.snippet} />
              </span>
            </button>
          ))}
        </Group>
      )}
      {hits.chats.length > 0 && (
        <Group title="searchChatsGroup">
          {hits.chats.map((h) => (
            <button key={h.chat_id} onClick={() => onOpenChat(h.chat_id)} className={row}>
              <MessageSquare size={14} className="mt-0.5 shrink-0 text-faint" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{h.title}</span>
                <Marked text={h.snippet} />
              </span>
            </button>
          ))}
        </Group>
      )}
    </>
  );
}
