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
    <div className="fixed inset-0 z-50 flex flex-col bg-ink/40" role="dialog" aria-modal="true" aria-label={file.name}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="mx-auto flex h-full w-full max-w-5xl flex-col py-6 px-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <header className="flex items-center gap-3 rounded-t-2xl border-b border-rule bg-sheet px-5 py-3">
          <h2 className="min-w-0 flex-1 truncate font-serif text-lg text-ink">{file.name}</h2>
          {onEdit && (
            <button onClick={onEdit}
              className="flex items-center gap-1.5 rounded-lg border border-rule px-3 py-1.5 text-sm text-ink hover:border-cite hover:text-cite">
              <PenLine size={14} /> {t("fileEdit")}
            </button>
          )}
          <a href={api.fileUrl(file.id)} aria-label={t("fileDownload")} title={t("fileDownload")}
            className="rounded-md p-1.5 text-muted hover:bg-paper hover:text-ink"><Download size={17} /></a>
          <button onClick={onClose} aria-label={t("close")} className="rounded-md p-1.5 text-muted hover:bg-paper hover:text-ink">
            <X size={18} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-b-2xl bg-desk">
          {!preview && <p className="p-8 text-sm text-faint">{t("fileOpening")}</p>}
          {preview?.kind === "pdf" && <iframe src={inline} title={file.name} className="h-full w-full bg-sheet" />}
          {preview?.kind === "image" && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={inline} alt={file.name} className="mx-auto max-h-full max-w-full p-6 object-contain" />
          )}
          {preview?.kind === "document" && preview.doc && (
            <div className="px-4 py-6">
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
