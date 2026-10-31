"use client";

// A petition draft in the editor: beside the chat, or as a page of its own (opened from
// My files). Formatted like a word processor, changed with the four buttons (the whole
// petition or the selected part), saved as the lawyer types, and downloaded as Word, PDF or
// UDF. The buttons, and the session's edits once it ends, teach the lawyer's style.
import { useCallback, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";
import { ArrowLeft, Check, CloudOff, Download, Loader2, Maximize2, X } from "lucide-react";
import { PetitionEditor, selectedText } from "@/components/PetitionEditor";
import { api, type Draft, type DraftAction, type DraftFormat, type EditorDoc } from "@/lib/api";
import { useAutosave } from "@/lib/editor/useAutosave";
import { t } from "@/lib/i18n";

const ACTIONS: Array<[DraftAction, "draftShorter" | "draftLonger" | "draftPlainer" | "draftFormal"]> = [
  ["shorter", "draftShorter"], ["longer", "draftLonger"],
  ["plainer", "draftPlainer"], ["formal", "draftFormal"],
];
const FORMATS: DraftFormat[] = ["docx", "pdf", "udf"];
const FORMAT_NAMES: Record<string, string> = { docx: "Word", pdf: "PDF", udf: "UDF" };

export function DraftPanel({ draft, onClose, onChange, onExpand, page = false }: {
  draft: Draft; onClose: () => void; onChange: (d: Draft) => void;
  onExpand?: () => void;                // beside the chat: open it as a page
  page?: boolean;                       // a page of its own instead of beside the chat
}) {
  const [doc, setDoc] = useState<EditorDoc>(draft.doc);
  const [version, setVersion] = useState(0);         // remounts the editor after a rewrite
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const editor = useRef<Editor | null>(null);
  const onReady = useCallback((e: Editor) => { editor.current = e; }, []);
  const autosave = useAutosave(draft.id, onChange);

  function edited(next: EditorDoc) {
    setDoc(next);
    autosave.edited(next);
  }

  async function run(work: () => Promise<Draft>, reload = false) {
    setBusy(true);
    setFailed(false);
    try {
      const updated = await work();
      onChange(updated);
      if (reload) {
        setDoc(updated.doc);
        setVersion((v) => v + 1);
      }
      return updated;
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  async function adjust(action: DraftAction) {
    const selection = editor.current ? selectedText(editor.current) : "";
    // Pending edits are saved first, so the selection is found in the stored text.
    if (!(await autosave.flush())) return;
    await run(() => api.adjustDraft(draft.id, action, selection || undefined), true);
  }

  async function download(fmt: DraftFormat) {
    if (!(await autosave.flush())) return;
    window.location.href = api.draftFileUrl(draft.id, fmt);
  }

  const saveText = { idle: "", saving: t("draftSaving"), saved: t("draftSaved"), error: t("draftSaveFailed") }[autosave.state];
  const status = busy ? t("draftWorking") : failed ? t("draftAdjustFailed") : t("draftSelectionHint");

  return (
    <aside className={`flex h-full w-full shrink-0 flex-col bg-paper ${page ? "" : "max-w-2xl border-l border-rule"}`}>
      <header className="flex items-center gap-3 border-b border-rule px-5 py-3">
        {page && (
          <button onClick={onClose} aria-label={t("back")} className="rounded-md p-1 text-muted hover:bg-sheet hover:text-ink">
            <ArrowLeft size={18} />
          </button>
        )}
        <h2 className="min-w-0 flex-1 truncate font-serif text-lg text-ink">{draft.title || t("draft")}</h2>
        <span aria-live="polite" className={`flex items-center gap-1.5 text-sm ${autosave.state === "error" ? "text-danger" : "text-faint"}`}>
          {autosave.state === "saving" && <Loader2 size={14} className="animate-spin" />}
          {autosave.state === "saved" && <Check size={14} className="text-verified" />}
          {autosave.state === "error" && <CloudOff size={14} />}
          {saveText}
        </span>
        <div className="flex items-center rounded-lg border border-rule">
          <Download size={14} className="ml-2.5 text-muted" aria-hidden />
          {FORMATS.map((f) => (
            <button key={f} disabled={busy} onClick={() => download(f)} title={t("draftDownloadAs", { format: FORMAT_NAMES[f] })}
              className="px-2.5 py-1.5 text-sm text-ink hover:bg-sheet disabled:opacity-50">
              {FORMAT_NAMES[f]}
            </button>
          ))}
        </div>
        {!page && onExpand && (
          <button onClick={onExpand} aria-label={t("draftExpand")} title={t("draftExpand")}
            className="rounded-md p-1 text-faint hover:bg-sheet hover:text-ink">
            <Maximize2 size={17} />
          </button>
        )}
        {!page && (
          <button onClick={onClose} aria-label={t("close")} className="rounded-md p-1 text-faint hover:bg-sheet hover:text-ink">
            <X size={18} />
          </button>
        )}
      </header>
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-5 py-2 text-sm">
        {ACTIONS.map(([action, label]) => (
          <button key={action} disabled={busy} onClick={() => adjust(action)}
            className="rounded-full border border-rule px-3 py-1 text-ink hover:border-cite hover:text-cite disabled:opacity-50">
            {t(label)}
          </button>
        ))}
        <span className={`ml-auto text-xs ${failed ? "text-danger" : "text-faint"}`} aria-live="polite">{status}</span>
      </div>
      <PetitionEditor key={version} doc={doc} disabled={busy} onChange={edited} onReady={onReady} />
    </aside>
  );
}
