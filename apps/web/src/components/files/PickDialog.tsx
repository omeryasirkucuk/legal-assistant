"use client";

// A small dialog to choose where something goes: a folder (shown as a tree, with the top
// level first) or a case. The current place is marked and cannot be chosen again.
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Folder as FolderIcon, FolderOpen, Scale, X } from "lucide-react";
import type { Folder, Matter } from "@/lib/api";
import { t } from "@/lib/i18n";

export type Choice = { id: string | null; label: string; depth: number; kind: "folder" | "top" | "matter" | "none" };

/** Folders as an indented tree under the top level, leaving out `skip` and what it holds. */
export function folderChoices(folders: Folder[], skip?: string): Choice[] {
  const out: Choice[] = [{ id: null, label: t("myFiles"), depth: 0, kind: "top" }];
  const walk = (parent: string | null, depth: number) => {
    for (const f of folders.filter((x) => x.parent_id === parent)) {
      if (f.id === skip) continue;
      out.push({ id: f.id, label: f.name, depth, kind: "folder" });
      walk(f.id, depth + 1);
    }
  };
  walk(null, 1);
  return out;
}

export function matterChoices(matters: Matter[], current: string | null): Choice[] {
  const open = matters.filter((m) => !m.closed);
  const out: Choice[] = open.map((m) => ({ id: m.id, label: m.subject ? `${m.client}, ${m.subject}` : m.client, depth: 0, kind: "matter" }));
  if (current) out.push({ id: null, label: t("fileRemoveFromMatter"), depth: 0, kind: "none" });
  return out;
}

export function PickDialog({ title, choices, current, onPick, onClose }: {
  title: string; choices: Choice[];
  current: string | null | undefined;     // undefined: nothing is marked (copying, several items)
  onPick: (c: Choice) => void; onClose: () => void;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/25 px-4 pt-[14vh]"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className="w-full max-w-sm rounded-2xl border border-rule bg-paper p-4 shadow-xl">
        <div className="mb-2 flex items-center justify-between px-1">
          <h2 className="font-serif text-lg text-ink">{title}</h2>
          <button onClick={onClose} aria-label={t("close")} className="rounded-md p-1 text-muted hover:bg-sheet hover:text-ink"><X size={16} /></button>
        </div>
        {choices.length === 0 && <p className="px-1 py-2 text-sm text-faint">{t("pickNothing")}</p>}
        <ul className="max-h-[50vh] overflow-y-auto">
          {choices.map((c) => {
            const here = c.id === current && c.kind !== "none";
            const Icon = c.kind === "matter" ? Scale : c.kind === "top" ? FolderOpen : FolderIcon;
            return (
              <li key={`${c.kind}-${c.id}`}>
                <button disabled={here} onClick={() => onPick(c)} style={{ paddingLeft: `${0.75 + c.depth * 1.1}rem` }}
                  className={`flex w-full items-center gap-2 rounded-lg py-2 pr-3 text-left text-sm ${
                    here ? "text-faint" : c.kind === "none" ? "text-danger hover:bg-sheet" : "text-ink hover:bg-sheet"}`}>
                  {c.kind !== "none" && <Icon size={15} className="shrink-0 text-muted" />}
                  <span className="truncate">{c.label}</span>
                  {here && <span className="ml-auto text-xs">{t("pickHere")}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>,
    document.body,
  );
}
