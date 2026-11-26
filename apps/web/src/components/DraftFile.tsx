"use client";

// A petition delivered as a file in the chat: download in the chosen format, other formats,
// and the editor.
import { api, type Draft, type DraftFormat } from "@/lib/api";
import { t } from "@/lib/i18n";

const FORMATS: DraftFormat[] = ["docx", "pdf", "udf"];

export function DraftFile({ draft, onEdit }: { draft: Draft; onEdit: () => void }) {
  return (
    <div className="flex max-w-[42rem] flex-wrap items-center gap-2 sm:flex-nowrap sm:gap-4 rounded-md border border-rule bg-paper px-4 py-3">
      <span className="flex h-12 w-10 shrink-0 items-center justify-center rounded-sm border border-rule font-sans text-[0.65rem] font-semibold uppercase text-cite">
        {draft.format}
      </span>
      <div className="min-w-0 flex-1 basis-[calc(100%-3rem)] sm:basis-auto">
        <p className="truncate text-[15px] text-ink">{draft.file_name}</p>
        <p className="mt-0.5 text-xs text-faint">
          {t("draftOtherFormat")}{" "}
          {FORMATS.filter((f) => f !== draft.format).map((f, i) => (
            <span key={f}>
              {i > 0 && " · "}
              <a href={api.draftFileUrl(draft.id, f)} className="underline hover:text-ink">
                {t(`format_${f}`)}
              </a>
            </span>
          ))}
        </p>
      </div>
      <button onClick={onEdit} className="ml-auto shrink-0 rounded sm:ml-0 border border-rule px-3 py-1.5 text-sm text-ink">
        {t("draftEdit")}
      </button>
      <a href={api.draftFileUrl(draft.id)}
        className="shrink-0 rounded bg-cite px-3 py-1.5 text-sm text-white hover:opacity-90">
        {t("draftDownload")}
      </a>
    </div>
  );
}
