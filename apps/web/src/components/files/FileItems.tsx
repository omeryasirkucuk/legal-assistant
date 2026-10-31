"use client";

// Files and folders of My files, as list rows or as icon tiles. Files and folders can be
// dragged onto a folder (or the path above) to move them, several at once when selected; a
// folder opens on click, a file opens its preview; Cmd/Ctrl- or Shift-click selects.
import { useEffect, useRef, useState } from "react";
import { Check, Download, Eye, FileText, Folder as FolderIcon, PenLine, Scale } from "lucide-react";
import { ItemMenu, type MenuItem } from "@/components/files/ItemMenu";
import { api, type Folder, type StoredFile } from "@/lib/api";
import { t } from "@/lib/i18n";

/** Files and folders dragged within the page (several when a selection is dragged). */
export const DRAG_ITEMS = "application/x-legal-items";
export type Item = { kind: "file" | "folder"; id: string };

/** What can be dropped on a folder: files and folders from this page. */
export function dropTarget(onDrop: (items: Item[]) => void) {
  return {
    onDragOver: (e: React.DragEvent) => {
      if (e.dataTransfer.types.includes(DRAG_ITEMS)) {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
      }
    },
    onDrop: (e: React.DragEvent) => {
      const raw = e.dataTransfer.getData(DRAG_ITEMS);
      if (!raw) return;
      e.preventDefault();
      e.stopPropagation();
      onDrop(JSON.parse(raw) as Item[]);
    },
  };
}

function dragging(items: () => Item[]) {
  return {
    draggable: true,
    onDragStart: (e: React.DragEvent) => {
      e.dataTransfer.setData(DRAG_ITEMS, JSON.stringify(items()));
      e.dataTransfer.effectAllowed = "move";
    },
  };
}

/** The tick box of a selectable item: shown on hover, and always while anything is selected. */
function Tick({ selected, selecting, onToggle, label, className = "" }: {
  selected: boolean; selecting: boolean; onToggle: (e: React.MouseEvent) => void; label: string; className?: string;
}) {
  return (
    <button role="checkbox" aria-checked={selected} aria-label={label} onClick={(e) => { e.stopPropagation(); onToggle(e); }}
      className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded border ${
        selected ? "border-cite bg-cite text-white" : "border-faint bg-sheet text-transparent hover:border-ink"} ${
        selected || selecting ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100"} ${className}`}>
      <Check size={12} strokeWidth={3} />
    </button>
  );
}

/** A click on an item: with Cmd/Ctrl or Shift, or while selecting, it selects; else it opens. */
function clickOrSelect(selecting: boolean, onToggle: (e: React.MouseEvent) => void, open: () => void) {
  return (e: React.MouseEvent) => {
    if (selecting || e.metaKey || e.ctrlKey || e.shiftKey) {
      e.preventDefault();
      onToggle(e);
    } else open();
  };
}

function useDropHighlight() {
  const [over, setOver] = useState(false);
  return {
    over,
    bind: {
      onDragEnter: (e: React.DragEvent) => {
        if (e.dataTransfer.types.includes(DRAG_ITEMS)) setOver(true);
      },
      onDragLeave: (e: React.DragEvent) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false);
      },
      onDropCapture: () => setOver(false),
    },
  };
}

const FORMAT_BADGE: Record<string, string> = { word: "DOCX", pdf: "PDF", udf: "UDF", image: "IMG", text: "TXT", spreadsheet: "XLS", email: "EML" };

/** A file's name with an inline rename (the extension stays). */
export function FileName({ file, renaming, onDone, className = "" }: {
  file: StoredFile; renaming: boolean; onDone: (name: string | null) => void; className?: string;
}) {
  const dot = file.name.lastIndexOf(".");
  const base = dot > 0 ? file.name.slice(0, dot) : file.name;
  const ext = dot > 0 ? file.name.slice(dot) : "";
  const [value, setValue] = useState(base);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) {
      setValue(base);
      setTimeout(() => box.current?.select(), 0);
    }
  }, [renaming, base]);

  if (!renaming) return <span className={`truncate text-ink ${className}`} title={file.name}>{file.name}</span>;
  const finish = () => onDone(value.trim() && value.trim() !== base ? value.trim() : null);
  return (
    <span className="flex min-w-0 items-baseline gap-0.5" onClick={(e) => e.stopPropagation()}>
      <input ref={box} value={value} onChange={(e) => setValue(e.target.value)} onBlur={finish}
        onKeyDown={(e) => { if (e.key === "Enter") finish(); if (e.key === "Escape") onDone(null); }}
        aria-label={t("fileRename")}
        className="min-w-0 flex-1 rounded border border-cite bg-sheet px-1.5 py-0.5 text-sm text-ink outline-none" />
      <span className="text-sm text-faint">{ext}</span>
    </span>
  );
}

type FileProps = {
  file: StoredFile;
  about: string;                // "Dilekçe · Aile"
  meta: string;                 // size and date
  matterName: string | null;    // the case it is used in
  renaming: boolean;
  onRenamed: (name: string | null) => void;
  onPreview: () => void;
  onEdit: (() => void) | null;
  onOpenChat: (() => void) | null;
  menu: MenuItem[];
  selected: boolean;
  selecting: boolean;           // anything is selected
  onToggle: (e: React.MouseEvent) => void;
  dragItems: () => Item[];
};

export function FileRow(p: FileProps) {
  const icon = "rounded-md p-1.5 text-muted hover:bg-sheet hover:text-ink";
  return (
    <li {...dragging(p.dragItems)} className={`group -mx-2 flex items-center gap-3 rounded-lg px-2 py-3 ${p.selected ? "bg-cite-soft" : ""}`}>
      <Tick selected={p.selected} selecting={p.selecting} onToggle={p.onToggle} label={p.file.name} />
      <FileText size={18} className={`shrink-0 ${p.file.origin === "generated" ? "text-verified" : "text-cite"}`} />
      <span className="min-w-0 flex-1">
        <button onClick={clickOrSelect(p.selecting, p.onToggle, p.onPreview)} disabled={p.renaming} className="block max-w-full text-left">
          <FileName file={p.file} renaming={p.renaming} onDone={p.onRenamed} className="block text-[15px] hover:underline" />
        </button>
        <span className="block truncate text-xs text-faint">
          {p.about && <span className="text-muted">{p.about} · </span>}
          {p.meta}
          {p.matterName && <span className="text-cite"> · <Scale size={11} className="inline -translate-y-px" /> {p.matterName}</span>}
          {p.onOpenChat && p.file.chat_title && (
            <>
              {" · "}
              <button onClick={p.onOpenChat} className="underline-offset-2 hover:text-ink hover:underline">
                {t("fileFromChat", { title: p.file.chat_title })}
              </button>
            </>
          )}
        </span>
      </span>
      {p.onEdit && (
        <button onClick={p.onEdit}
          className="flex items-center gap-1.5 rounded-lg border border-rule px-2.5 py-1 text-sm text-ink hover:border-cite hover:text-cite">
          <PenLine size={14} /> {t("fileEdit")}
        </button>
      )}
      <button onClick={p.onPreview} aria-label={t("fileOpen")} title={t("fileOpen")} className={icon}><Eye size={16} /></button>
      <a href={api.fileUrl(p.file.id)} aria-label={t("fileDownload")} title={t("fileDownload")} className={icon}><Download size={16} /></a>
      <ItemMenu items={p.menu} />
    </li>
  );
}

export function FileTile(p: FileProps) {
  const badge = FORMAT_BADGE[p.file.format] ?? p.file.name.split(".").pop()?.toUpperCase() ?? "";
  return (
    <li {...dragging(p.dragItems)} className={`group relative flex flex-col rounded-xl border p-3 ${
      p.selected ? "border-cite bg-cite-soft" : "border-transparent hover:border-rule hover:bg-sheet"}`}>
      <Tick selected={p.selected} selecting={p.selecting} onToggle={p.onToggle} label={p.file.name} className="absolute left-2 top-2" />
      <button onClick={clickOrSelect(p.selecting, p.onToggle, p.onPreview)} disabled={p.renaming} className="flex flex-col items-center text-center" aria-label={p.file.name}>
        <span className="relative flex h-20 w-16 items-start justify-end rounded-md border border-rule bg-sheet shadow-sm">
          <FileText size={26} strokeWidth={1.4} className={`absolute inset-0 m-auto ${p.file.origin === "generated" ? "text-verified" : "text-cite"}`} />
          <span className="mt-1.5 mr-[-6px] rounded bg-ink px-1 py-px text-[9px] font-medium tracking-wide text-white">{badge}</span>
        </span>
      </button>
      <span className="mt-2 min-w-0 text-center">
        <FileName file={p.file} renaming={p.renaming} onDone={p.onRenamed} className="line-clamp-2 block break-words text-[13px] leading-snug" />
        <span className="mt-0.5 block truncate text-[11px] text-faint">{p.about || p.meta}</span>
        {p.matterName && <span className="block truncate text-[11px] text-cite">{p.matterName}</span>}
      </span>
      <ItemMenu className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100"
        items={[...(p.onEdit ? [{ label: t("fileEdit"), onSelect: p.onEdit }] : []), ...p.menu]} />
    </li>
  );
}

type FolderProps = {
  folder: Folder;
  count: number;
  renaming: boolean;
  onRenamed: (name: string | null) => void;
  onOpen: () => void;
  onDropItems: (items: Item[]) => void;
  menu: MenuItem[];
  selected: boolean;
  selecting: boolean;
  onToggle: (e: React.MouseEvent) => void;
  dragItems: () => Item[];
};

function FolderName({ folder, renaming, onDone, className = "" }: {
  folder: Folder; renaming: boolean; onDone: (name: string | null) => void; className?: string;
}) {
  const [value, setValue] = useState(folder.name);
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (renaming) {
      setValue(folder.name);
      setTimeout(() => box.current?.select(), 0);
    }
  }, [renaming, folder.name]);
  if (!renaming) return <span className={`truncate text-ink ${className}`}>{folder.name}</span>;
  const finish = () => onDone(value.trim() && value.trim() !== folder.name ? value.trim() : null);
  return (
    <input ref={box} value={value} onChange={(e) => setValue(e.target.value)} onBlur={finish} onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => { if (e.key === "Enter") finish(); if (e.key === "Escape") onDone(null); }}
      aria-label={t("folderRename")}
      className="min-w-0 rounded border border-cite bg-sheet px-1.5 py-0.5 text-sm text-ink outline-none" />
  );
}

export function FolderRow(p: FolderProps) {
  const { over, bind } = useDropHighlight();
  return (
    <li {...dragging(p.dragItems)} {...bind} {...dropTarget(p.onDropItems)}
      className={`group -mx-2 flex items-center gap-3 rounded-lg px-2 py-3 ${over ? "bg-cite-soft ring-1 ring-cite" : p.selected ? "bg-cite-soft" : ""}`}>
      <Tick selected={p.selected} selecting={p.selecting} onToggle={p.onToggle} label={p.folder.name} />
      <FolderIcon size={18} className="shrink-0 fill-caution-soft text-caution" />
      <button onClick={clickOrSelect(p.selecting, p.onToggle, p.onOpen)} disabled={p.renaming} className="min-w-0 flex-1 text-left">
        <FolderName folder={p.folder} renaming={p.renaming} onDone={p.onRenamed} className="block text-[15px] hover:underline" />
        <span className="block text-xs text-faint">{t("folderCount", { n: p.count })}</span>
      </button>
      <ItemMenu items={p.menu} />
    </li>
  );
}

export function FolderTile(p: FolderProps) {
  const { over, bind } = useDropHighlight();
  return (
    <li {...dragging(p.dragItems)} {...bind} {...dropTarget(p.onDropItems)}
      className={`group relative flex flex-col items-center rounded-xl border p-3 ${over || p.selected ? "border-cite bg-cite-soft" : "border-transparent hover:border-rule hover:bg-sheet"}`}>
      <Tick selected={p.selected} selecting={p.selecting} onToggle={p.onToggle} label={p.folder.name} className="absolute left-2 top-2" />
      <button onClick={clickOrSelect(p.selecting, p.onToggle, p.onOpen)} disabled={p.renaming} aria-label={p.folder.name} className="flex h-20 items-center">
        <FolderIcon size={56} strokeWidth={1.2} className="fill-caution-soft text-caution" />
      </button>
      <span className="mt-2 min-w-0 max-w-full text-center">
        <FolderName folder={p.folder} renaming={p.renaming} onDone={p.onRenamed} className="line-clamp-2 block break-words text-[13px] leading-snug" />
        <span className="block text-[11px] text-faint">{t("folderCount", { n: p.count })}</span>
      </span>
      <ItemMenu className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100" items={p.menu} />
    </li>
  );
}
