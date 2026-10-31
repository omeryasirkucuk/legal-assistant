"use client";

// What can be done with the selected files and folders at once. Copying and giving to a
// case apply to files; folders are moved or deleted with what they hold.
import { Copy, FolderInput, Scale, Trash2, X } from "lucide-react";
import { t } from "@/lib/i18n";

export function SelectionBar({ count, files, busy, onMove, onCopy, onMatter, onDelete, onClear }: {
  count: number; files: number; busy: boolean;
  onMove: () => void; onCopy: () => void; onMatter: () => void; onDelete: () => void; onClear: () => void;
}) {
  const action = "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm hover:bg-white/10 disabled:opacity-40";
  return (
    <div role="toolbar" aria-label={t("selectionActions")}
      className="sticky top-3 z-20 mt-4 flex flex-wrap items-center gap-1 rounded-xl bg-ink px-3 py-1.5 text-white shadow-lg">
      <button onClick={onClear} aria-label={t("selectionClear")} title={t("selectionClear")}
        className="rounded-md p-1 text-white/70 hover:bg-white/10 hover:text-white"><X size={16} /></button>
      <span className="mr-auto pl-1 text-sm">{t("selectionCount", { n: count })}</span>
      <button disabled={busy} onClick={onMove} className={action}><FolderInput size={15} /> {t("fileMove")}</button>
      <button disabled={busy || !files} onClick={onCopy} className={action}><Copy size={15} /> {t("fileCopy")}</button>
      <button disabled={busy || !files} onClick={onMatter} className={action}><Scale size={15} /> {t("fileGiveMatter")}</button>
      <button disabled={busy} onClick={onDelete} className={`${action} text-[#ffb4a8]`}><Trash2 size={15} /> {t("fileDelete")}</button>
    </div>
  );
}
