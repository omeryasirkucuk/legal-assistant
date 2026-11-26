"use client";

// A file shown inside the app: a PDF in the browser's viewer, an image as itself, and any
// other readable document (Word, UDF, text, a petition) as an A4 page. Browsers download
// Word and UDF files instead of showing them, which is why this exists.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { generateHTML } from "@tiptap/core";
import type { JSONContent } from "@tiptap/react";
import { Download, PenLine, X } from "lucide-react";
import { EXTENSIONS } from "@/components/PetitionEditor";
import { api, type FilePreview as Preview, type StoredFile } from "@/lib/api";
import { t } from "@/lib/i18n";

export function FilePreview({ file, onClose, onEdit }: {
  file: StoredFile; onClose: () => void; onEdit?: () => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    api.filePreview(file.id).then(setPreview).catch(() => setPreview({ kind: "none" }));
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [file.id, onClose]);

  const inline = `${api.fileUrl(file.id)}?inline=true`;
  return createPortal(
    <div className="viewport-overlay fixed inset-0 z-50 flex flex-col bg-ink/40" role="dialog" aria-modal="true" aria-label={file.name}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="mx-auto flex h-full w-full max-w-5xl flex-col sm:px-4 sm:py-6" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <header className="flex shrink-0 items-center gap-1 border-b border-rule bg-sheet px-2 py-2 sm:gap-3 sm:rounded-t-2xl sm:px-5 sm:py-3">
          <h2 className="min-w-0 flex-1 truncate font-serif text-lg text-ink">{file.name}</h2>
          {onEdit && (
            <button onClick={onEdit} aria-label={t("fileEdit")}
              className="flex min-h-10 shrink-0 items-center gap-1.5 rounded-lg border border-rule px-2.5 sm:px-3 text-sm text-ink hover:border-cite hover:text-cite">
              <PenLine size={14} /> <span className="hidden sm:inline">{t("fileEdit")}</span>
            </button>
          )}
          <a href={api.fileUrl(file.id)} aria-label={t("fileDownload")} title={t("fileDownload")}
            className="shrink-0 rounded-md p-2.5 sm:p-1.5 text-muted hover:bg-paper hover:text-ink"><Download size={17} /></a>
          <button onClick={onClose} aria-label={t("close")} className="shrink-0 rounded-md p-2.5 sm:p-1.5 text-muted hover:bg-paper hover:text-ink">
            <X size={18} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain bg-desk sm:rounded-b-2xl">
          {!preview && <p className="p-8 text-sm text-faint">{t("fileOpening")}</p>}
          {preview?.kind === "pdf" && <iframe src={inline} title={file.name} className="h-full w-full bg-sheet" />}
          {preview?.kind === "image" && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={inline} alt={file.name} className="mx-auto max-h-full max-w-full p-6 object-contain" />
          )}
          {preview?.kind === "document" && preview.doc && (
            <div className="px-2 py-3 sm:px-4 sm:py-6">
              <div className="petition-sheet"
                dangerouslySetInnerHTML={{ __html: generateHTML(preview.doc as JSONContent, EXTENSIONS) }} />
            </div>
          )}
          {preview?.kind === "none" && <p className="p-8 text-sm text-muted">{t("filePreviewNone")}</p>}
        </div>
      </div>
    </div>,
    document.body,
  );
}
