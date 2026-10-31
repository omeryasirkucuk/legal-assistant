"use client";

// My files as a page: every file the lawyer added and every petition made for them, in the
// lawyer's folders, as a list or as icons. Files are added here (button or drop; each is read
// and labelled like any attachment), previewed in the app, edited (a petition's own draft, or
// an editable copy of an added document, so the original stays), renamed, moved, given to a
// case (so its chats use it as material), downloaded or deleted; several at once when
// selected (moved, copied, given to a case, deleted).
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, FolderPlus, LayoutGrid, List, Upload } from "lucide-react";
import { useConfirm } from "@/components/ConfirmDialog";
import { FileFilters, matches, NO_PICKS, valueName, type Picks } from "@/components/FileFilters";
import { FilePreview } from "@/components/files/FilePreview";
import { FileRow, FileTile, FolderRow, FolderTile, dropTarget, type Item } from "@/components/files/FileItems";
import { SelectionBar } from "@/components/files/SelectionBar";
import { useSelection } from "@/components/files/useSelection";
import type { MenuItem } from "@/components/files/ItemMenu";
import { PickDialog, folderChoices, matterChoices, type Choice } from "@/components/files/PickDialog";
import { api, ApiError, type Draft, type FileUsage, type Folder, type Matter, type StoredFile } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { t } from "@/lib/i18n";

type Filter = "all" | "upload" | "generated";
type Layout = "list" | "grid";
type Picking = { kind: "moveFile" | "moveFolder" | "matter"; id: string }
  | { kind: "moveMany" | "copyMany" | "matterMany" } | null;

const EDITABLE = new Set(["word", "udf", "pdf", "text"]);
const canEdit = (f: StoredFile) => f.draft_id !== null || (f.readable && EDITABLE.has(f.format));

function useLayout(): [Layout, (l: Layout) => void] {
  const [layout, setLayout] = useState<Layout>("list");
  useEffect(() => {
    try { if (localStorage.getItem("filesLayout") === "grid") setLayout("grid"); } catch {}
  }, []);
  return [layout, (l) => {
    setLayout(l);
    try { localStorage.setItem("filesLayout", l); } catch {}
  }];
}

export function FilesView({ onOpenChat, onEdit, matters }: {
  onOpenChat: (id: string) => void;
  onEdit: (draft: Draft) => void;
  matters: Matter[];
}) {
  const [files, setFiles] = useState<StoredFile[] | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [usage, setUsage] = useState<FileUsage | null>(null);
  const [here, setHere] = useState<string | null>(null);          // the open folder
  const [filter, setFilter] = useState<Filter>("all");
  const [picks, setPicks] = useState<Picks>(NO_PICKS);
  const [layout, setLayout] = useLayout();
  const [preview, setPreview] = useState<StoredFile | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);  // a file or folder id
  const [picking, setPicking] = useState<Picking>(null);
  const [uploading, setUploading] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDialog, confirm] = useConfirm();
  const [dropping, setDropping] = useState(false);
  const [working, setWorking] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const [f, d, u] = await Promise.all([api.files(), api.folders(), api.fileUsage()]);
    setFiles(f);
    setFolders(d);
    setUsage(u);
  }, []);

  useEffect(() => { reload().catch(() => setFiles([])); }, [reload]);

  async function add(list: FileList | File[]) {
    const all = Array.from(list);
    if (!all.length) return;
    setNotice(null);
    setUploading(all.length);
    let failed = 0;
    for (const f of all) {
      try {
        await api.uploadFile(f, here);
      } catch (e) {
        failed++;
        if (e instanceof ApiError && e.status === 507) setNotice(t("attachFull"));
      }
      setUploading((n) => n - 1);
    }
    if (failed && !notice) setNotice(t("filesAddFailed", { n: failed }));
    await reload();
  }

  async function edit(f: StoredFile) {
    try {
      onEdit(await api.editFile(f.id));
    } catch {
      setNotice(t("fileEditFailed"));
    }
  }

  async function move(items: Item[], to: string | null) {
    let refused = false;
    for (const it of items) {
      if (it.kind === "file") await api.editFileInfo(it.id, to ? { folder_id: to } : { to_top: true });
      else if (it.id !== to) {
        try {
          await api.editFolder(it.id, to ? { parent_id: to } : { to_top: true });
        } catch {
          refused = true;
        }
      }
    }
    if (refused) setNotice(t("folderMoveInside"));
    await reload();
  }

  async function bulk(work: () => Promise<void>) {
    setWorking(true);
    try {
      await work();
    } finally {
      setWorking(false);
      selection.clear();
      await reload();
    }
  }

  async function deleteSelected() {
    const items = selection.items();
    if (!(await confirm(t("selectionDeleteAsk", { n: items.length })))) return;
    await bulk(async () => {
      for (const it of items) {
        if (it.kind === "file") await api.deleteFile(it.id).catch(() => {});
        else await api.deleteFolder(it.id).catch(() => {});
      }
    });
  }

  async function picked(c: Choice) {
    const p = picking;
    setPicking(null);
    if (!p) return;
    if (p.kind === "matter") {
      await api.editFileInfo(p.id, c.id ? { matter_id: c.id } : { no_matter: true });
      await reload();
    } else if (p.kind === "moveFile" || p.kind === "moveFolder") {
      await move([{ kind: p.kind === "moveFile" ? "file" : "folder", id: p.id }], c.id);
    } else if (p.kind === "moveMany") {
      await bulk(() => move(selection.items(), c.id));
    } else if (p.kind === "copyMany") {
      await bulk(async () => {
        for (const it of selection.files()) {
          try {
            await api.copyFile(it.id, c.id);
          } catch (e) {
            if (e instanceof ApiError && e.status === 507) { setNotice(t("attachFull")); break; }
          }
        }
      });
    } else if (p.kind === "matterMany") {
      await bulk(async () => {
        for (const it of selection.files()) {
          await api.editFileInfo(it.id, c.id ? { matter_id: c.id } : { no_matter: true });
        }
      });
    }
  }

  async function newFolder() {
    const f = await api.createFolder(t("folderNewName"), here);
    await reload();
    setRenaming(f.id);
  }

  // Path to the open folder, from the top.
  const path: Folder[] = [];
  for (let at = folders.find((f) => f.id === here); at; at = folders.find((f) => f.id === at!.parent_id)) path.unshift(at);

  const inTab = (files ?? []).filter((f) => filter === "all" || f.origin === filter);
  const filtering = Object.values(picks).some(Boolean) || filter !== "all";
  // While filtering, files are found in every folder; otherwise the open folder is shown.
  const shownFiles = inTab.filter((f) => matches(f, picks) && (filtering || f.folder_id === here));
  const shownFolders = filtering ? [] : folders.filter((f) => f.parent_id === here);
  const countIn = (id: string) => (files ?? []).filter((f) => f.folder_id === id).length
    + folders.filter((f) => f.parent_id === id).length;
  const about = (f: StoredFile) => [f.kind !== "other" && valueName("kind", f.kind),
    f.area !== "other" && valueName("area", f.area)].filter(Boolean).join(" · ");
  const date = (iso: string) => new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" });
  const matterName = (id: string | null) => matters.find((m) => m.id === id)?.client ?? null;
  const share = usage ? usage.used_bytes / usage.quota_bytes : 0;

  const fileMenu = (f: StoredFile): MenuItem[] => [
    { label: t("fileRename"), onSelect: () => setRenaming(f.id) },
    { label: t("fileMove"), onSelect: () => setPicking({ kind: "moveFile", id: f.id }) },
    { label: f.matter_id ? t("fileChangeMatter") : t("fileGiveMatter"), onSelect: () => setPicking({ kind: "matter", id: f.id }) },
    { label: t("fileDelete"), danger: true, onSelect: async () => {
      if (await confirm(t("fileDeleteAsk", { name: f.name }))) { await api.deleteFile(f.id); await reload(); }
    } },
  ];
  const folderMenu = (d: Folder): MenuItem[] => [
    { label: t("folderRename"), onSelect: () => setRenaming(d.id) },
    { label: t("fileMove"), onSelect: () => setPicking({ kind: "moveFolder", id: d.id }) },
    { label: t("folderDelete"), danger: true, onSelect: async () => {
      if (await confirm(t("folderDeleteAsk", { name: d.name }))) { await api.deleteFolder(d.id); await reload(); }
    } },
  ];

  // The items in the order they are shown, for Shift ranges and select-all.
  const visible: Item[] = [...shownFolders.map((d) => ({ kind: "folder" as const, id: d.id })),
    ...shownFiles.map((f) => ({ kind: "file" as const, id: f.id }))];
  const selection = useSelection(visible, [here, filter, picks]);
  const selecting = selection.count > 0;

  const fileProps = (f: StoredFile) => ({
    file: f, about: about(f), meta: `${formatBytes(f.size)} · ${date(f.created_at)}`,
    matterName: matterName(f.matter_id), renaming: renaming === f.id,
    onRenamed: async (name: string | null) => {
      setRenaming(null);
      if (name) { await api.renameFile(f.id, name); await reload(); }
    },
    onPreview: () => setPreview(f),
    onEdit: canEdit(f) ? () => edit(f) : null,
    onOpenChat: f.chat_id ? () => onOpenChat(f.chat_id!) : null,
    menu: fileMenu(f),
    selected: selection.has({ kind: "file", id: f.id }), selecting,
    onToggle: (e: React.MouseEvent) => selection.toggle({ kind: "file", id: f.id }, e),
    dragItems: selection.dragItems({ kind: "file", id: f.id }),
  });
  const folderProps = (d: Folder) => ({
    folder: d, count: countIn(d.id), renaming: renaming === d.id,
    onRenamed: async (name: string | null) => {
      setRenaming(null);
      if (name) { await api.editFolder(d.id, { name }); await reload(); }
    },
    onOpen: () => setHere(d.id),
    onDropItems: (items: Item[]) => move(items.filter((i) => i.id !== d.id), d.id),
    menu: folderMenu(d),
    selected: selection.has({ kind: "folder", id: d.id }), selecting,
    onToggle: (e: React.MouseEvent) => selection.toggle({ kind: "folder", id: d.id }, e),
    dragItems: selection.dragItems({ kind: "folder", id: d.id }),
  });

  const pickingFile = picking && "id" in picking && picking.kind !== "moveFolder" ? (files ?? []).find((f) => f.id === picking.id) : null;
  const pickingFolder = picking && "id" in picking && picking.kind === "moveFolder" ? folders.find((f) => f.id === picking.id) : null;
  const empty = files !== null && shownFiles.length === 0 && shownFolders.length === 0;

  return (
    <div className="relative pb-12"
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDropping(true); } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropping(false); }}
      onDrop={(e) => { if (e.dataTransfer.files.length) { e.preventDefault(); setDropping(false); add(e.dataTransfer.files); } }}>
      {confirmDialog}
      {dropping && (
        <div className="pointer-events-none absolute -inset-4 z-20 flex items-center justify-center rounded-2xl border-2 border-dashed border-cite bg-cite-soft/80">
          <p className="font-serif text-xl text-cite">{t("filesDropHere", { place: path.at(-1)?.name ?? t("myFiles") })}</p>
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-xl">
          <h1 className="font-serif text-[2rem] leading-tight text-ink">{t("myFiles")}</h1>
          <p className="mt-1 text-[15px] leading-relaxed text-muted">{t("filesIntro")}</p>
        </div>
        {usage && (
          <div className="w-56">
            <div className="h-1.5 overflow-hidden rounded-full bg-rule">
              <div className="h-full rounded-full bg-verified" style={{ width: `${Math.max(0.5, Math.min(100, share * 100))}%` }} />
            </div>
            <p className="mt-1.5 text-xs text-muted">
              {t("usageStorage", { used: formatBytes(usage.used_bytes), quota: formatBytes(usage.quota_bytes) })}
            </p>
          </div>
        )}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2 sm:mt-8 sm:gap-3">
        <nav aria-label={t("folderPath")} className="flex min-w-0 flex-wrap items-center gap-1 text-[15px] max-sm:basis-full sm:flex-1">
          {[null, ...path].map((d, i) => {
            const id = d ? d.id : null;
            const last = i === path.length;
            return (
              <span key={id ?? "top"} className="flex items-center gap-1">
                {i > 0 && <ChevronRight size={14} className="text-faint" />}
                <button onClick={() => setHere(id)} {...dropTarget((items) => move(items, id))}
                  aria-current={last ? "page" : undefined}
                  className={`rounded-md px-1.5 py-0.5 ${last ? "font-medium text-ink" : "text-muted hover:bg-sheet hover:text-ink"}`}>
                  {d ? d.name : t("myFiles")}
                </button>
              </span>
            );
          })}
        </nav>
        <button onClick={newFolder}
          className="flex items-center gap-1.5 rounded-lg border border-rule px-3 py-1.5 text-sm text-ink hover:bg-sheet">
          <FolderPlus size={15} /> {t("folderNew")}
        </button>
        <button onClick={() => input.current?.click()}
          className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-sm text-white hover:brightness-110">
          <Upload size={15} /> {uploading ? t("filesAdding", { n: uploading }) : t("filesAdd")}
        </button>
        <input ref={input} type="file" multiple hidden onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />
        <div role="radiogroup" aria-label={t("filesLayout")} className="ml-auto flex rounded-lg bg-desk p-0.5">
          {([["list", List, "filesAsList"], ["grid", LayoutGrid, "filesAsIcons"]] as const).map(([l, Icon, key]) => (
            <button key={l} role="radio" aria-checked={layout === l} onClick={() => setLayout(l)} aria-label={t(key)} title={t(key)}
              className={`rounded-md p-1.5 ${layout === l ? "bg-sheet text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
              <Icon size={16} />
            </button>
          ))}
        </div>
      </div>
      {notice && <p className="mt-3 text-sm text-danger">{notice}</p>}

      <div role="tablist" className="mt-5 flex gap-1 border-b border-rule">
        {(["all", "upload", "generated"] as Filter[]).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${filter === f ? "border-cite text-ink" : "border-transparent text-muted hover:text-ink"}`}>
            {t(f === "all" ? "filesAll" : f === "upload" ? "filesUploaded" : "filesGenerated")}
          </button>
        ))}
      </div>
      {files && files.length > 0 && (
        <div className="-mx-7 max-w-3xl"><FileFilters files={inTab} picks={picks} onChange={setPicks} /></div>
      )}
      {filtering && <p className="mt-3 text-xs text-faint">{t("filesFilteringAll")}</p>}

      {empty && (
        <button onClick={() => input.current?.click()}
          className="mt-6 flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-rule px-6 py-12 text-center hover:border-cite">
          <Upload size={22} className="text-muted" />
          <span className="text-[15px] text-ink">{filtering ? t("filtersNone") : t("filesEmptyHere")}</span>
          {!filtering && <span className="text-sm text-muted">{t("filesEmptyHint")}</span>}
        </button>
      )}

      {selecting && (
        <SelectionBar count={selection.count} files={selection.files().length} busy={working}
          onMove={() => setPicking({ kind: "moveMany" })} onCopy={() => setPicking({ kind: "copyMany" })}
          onMatter={() => setPicking({ kind: "matterMany" })} onDelete={deleteSelected}
          onClear={selection.clear} />
      )}

      {layout === "list" ? (
        <ul className="mt-2 divide-y divide-rule">
          {shownFolders.map((d) => <FolderRow key={d.id} {...folderProps(d)} />)}
          {shownFiles.map((f) => <FileRow key={f.id} {...fileProps(f)} />)}
        </ul>
      ) : (
        <ul className="mt-5 grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-2">
          {shownFolders.map((d) => <FolderTile key={d.id} {...folderProps(d)} />)}
          {shownFiles.map((f) => <FileTile key={f.id} {...fileProps(f)} />)}
        </ul>
      )}

      {preview && (
        <FilePreview file={preview} onClose={() => setPreview(null)}
          onEdit={canEdit(preview) ? () => { const f = preview; setPreview(null); edit(f); } : undefined} />
      )}
      {picking && ("id" in picking ? (pickingFile || pickingFolder) : true) && (
        <PickDialog
          title={picking.kind === "matter" || picking.kind === "matterMany" ? t("fileGiveMatter")
            : picking.kind === "copyMany" ? t("fileCopyTo") : t("fileMove")}
          choices={picking.kind === "matter" ? matterChoices(matters, pickingFile?.matter_id ?? null)
            : picking.kind === "matterMany" ? matterChoices(matters, null)
            : folderChoices(folders, pickingFolder?.id)}
          current={picking.kind === "matter" ? pickingFile?.matter_id ?? null
            : picking.kind === "moveFile" ? pickingFile?.folder_id ?? null
            : picking.kind === "moveFolder" ? pickingFolder?.parent_id ?? null : undefined}
          onPick={picked} onClose={() => setPicking(null)} />
      )}
    </div>
  );
}
