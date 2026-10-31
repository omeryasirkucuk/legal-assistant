"use client";

// Above a chat: the case file it belongs to, as a way back to the file; or, for a chat in no
// file, a quiet control to put it in one.
import { useEffect, useRef, useState } from "react";
import { ChevronLeft, FolderInput } from "lucide-react";
import type { Matter } from "@/lib/api";
import { t } from "@/lib/i18n";

export function ChatMatterBar({ matter, matters, onOpenMatter, onMove }: {
  matter: Matter | null;
  matters: Matter[];
  onOpenMatter: (id: string) => void;
  onMove: (matterId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  if (matter) {
    return (
      <button onClick={() => onOpenMatter(matter.id)}
        className="-ml-1 mb-8 flex items-center gap-1 rounded-md px-1 py-0.5 text-sm text-muted hover:text-cite">
        <ChevronLeft size={15} />
        <span className="font-medium text-ink">{matter.client}</span>
        {matter.subject && <span className="text-faint">, {matter.subject}</span>}
      </button>
    );
  }
  const choices = matters.filter((m) => !m.closed);
  if (!choices.length) return null;
  return (
    <div ref={box} className="relative mb-8 flex justify-end">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted hover:bg-sheet hover:text-ink">
        <FolderInput size={15} /> {t("chatToMatter")}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-xl border border-rule bg-sheet p-1.5 shadow-xl">
          {choices.map((m) => (
            <button key={m.id} role="menuitem" onClick={() => { setOpen(false); onMove(m.id); }}
              className="block w-full rounded-md px-3 py-2 text-left hover:bg-paper">
              <span className="block truncate text-sm text-ink">{m.client}</span>
              {m.subject && <span className="block truncate text-xs text-faint">{m.subject}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
