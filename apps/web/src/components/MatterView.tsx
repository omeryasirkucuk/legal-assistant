"use client";

// A case file: whose it is and where it stands, its chats, its documents and petitions, its
// deadlines and the lawyer's notes, in one place. The message box below starts a chat in
// this file (the page handles it); every answer in the file knows its facts.
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileText, MessageSquare, MoreHorizontal, PenLine, Upload } from "lucide-react";
import { DeadlinePanel } from "@/components/DeadlinePanel";
import { MatterForm } from "@/components/MatterForm";
import { api, ApiError, type MatterDetail, type MatterFields } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { t } from "@/lib/i18n";

function relative(iso: string): string {
  return new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "long" });
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-10 first:mt-0">
      <div className="flex items-baseline justify-between border-b border-rule pb-2">
        <h2 className="font-serif text-lg text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function MatterView({ matterId, onOpenChat, onOpenDraft, onChanged, onDeleted }: {
  matterId: string;
  onOpenChat: (id: string) => void;
  onOpenDraft: (chatId: string) => void;
  onChanged: () => void;        // the file's summary changed (sidebar refreshes)
  onDeleted: () => void;
}) {
  const [m, setM] = useState<MatterDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [menu, setMenu] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [notes, setNotes] = useState("");
  const [uploadError, setUploadError] = useState("");
  const picker = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const detail = await api.matter(matterId);
    setM(detail);
    setNotes(detail.notes);
  }, [matterId]);

  useEffect(() => {
    setM(null);
    load().catch(() => {});
  }, [load]);

  if (!m) return <div className="mt-[18vh] text-center text-sm text-faint">{t("loading")}</div>;

  async function saveFields(fields: MatterFields) {
    await api.editMatter(matterId, fields);
    setEditing(false);
    await load();
    onChanged();
  }

  async function saveNotes() {
    if (!m || notes === m.notes) return;
    await api.editMatter(matterId, { notes });
    await load();
  }

  async function upload(files: FileList) {
    setUploadError("");
    for (const f of Array.from(files)) {
      try {
        await api.addMatterFile(matterId, f);
      } catch (err) {
        setUploadError(err instanceof ApiError && err.status === 507 ? t("attachFull") : t("attachFailed", { name: f.name }));
      }
    }
    await load();
  }

  async function remove() {
    if (!confirmDelete) return setConfirmDelete(true);
    await api.deleteMatter(matterId);
    onDeleted();
  }

  const meta = [m.court, m.case_no && t("caseNoShort", { no: m.case_no }), m.opponent && t("opponentShort", { name: m.opponent })]
    .filter(Boolean) as string[];

  return (
    <div className="pb-10">
      <header className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="font-serif text-[2rem] leading-tight text-ink">{m.client}</h1>
          {m.subject && <p className="mt-1 text-[17px] text-muted">{m.subject}</p>}
          {meta.length > 0 ? (
            <p className="mt-3 text-sm text-faint">{meta.join("  ·  ")}</p>
          ) : (
            <button onClick={() => setEditing(true)} className="mt-3 text-sm text-cite hover:underline">{t("matterAddDetails")}</button>
          )}
        </div>
        <div className="relative shrink-0">
          <button onClick={() => { setMenu((x) => !x); setConfirmDelete(false); }} aria-label={t("matterMenu")}
            className="rounded-lg p-2 text-muted hover:bg-sheet hover:text-ink">
            <MoreHorizontal size={18} />
          </button>
          {menu && (
            <div role="menu" className="absolute right-0 z-20 mt-1 w-56 rounded-xl border border-rule bg-sheet p-1.5 shadow-xl">
              <button role="menuitem" onClick={() => { setMenu(false); setEditing(true); }}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-ink hover:bg-paper">
                <PenLine size={15} className="text-muted" /> {t("matterEdit")}
              </button>
              <button role="menuitem" onClick={remove}
                className={`flex w-full rounded-md px-3 py-2 text-left text-sm ${confirmDelete ? "bg-danger text-white" : "text-danger hover:bg-paper"}`}>
                {confirmDelete ? t("matterDeleteConfirm") : t("matterDelete")}
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="min-w-0">
          <Section title={t("matterChats")}>
            {m.chats.length === 0 ? (
              <p className="py-3 text-sm text-faint">{t("matterNoChats")}</p>
            ) : (
              <ul className="divide-y divide-rule">
                {m.chats.map((c) => (
                  <li key={c.id}>
                    <button onClick={() => onOpenChat(c.id)}
                      className="flex w-full items-center gap-3 py-2.5 text-left hover:text-cite">
                      <MessageSquare size={15} className="shrink-0 text-faint" />
                      <span className="min-w-0 flex-1 truncate text-[15px] text-ink hover:text-cite">{c.title}</span>
                      <span className="shrink-0 text-xs text-faint">{relative(c.updated_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={t("matterDocuments")} action={
            <button onClick={() => picker.current?.click()} className="flex items-center gap-1.5 text-sm text-cite hover:underline">
              <Upload size={14} /> {t("matterAddDocument")}
            </button>}>
            <input ref={picker} type="file" multiple className="sr-only"
              onChange={(e) => { if (e.target.files?.length) upload(e.target.files); e.target.value = ""; }} />
            {uploadError && <p className="mt-2 text-sm text-danger">{uploadError}</p>}
            {m.drafts.length === 0 && m.documents.length === 0 ? (
              <p className="py-3 text-sm text-faint">{t("matterNoDocuments")}</p>
            ) : (
              <ul className="divide-y divide-rule">
                {m.drafts.map((d) => (
                  <li key={d.id}>
                    <button onClick={() => d.chat_id && onOpenDraft(d.chat_id)}
                      className="flex w-full items-center gap-3 py-2.5 text-left">
                      <PenLine size={15} className="shrink-0 text-verified" />
                      <span className="min-w-0 flex-1 truncate text-[15px] text-ink">{d.title}</span>
                      <span className="shrink-0 text-xs text-faint">{t("matterPetition")} · {relative(d.updated_at)}</span>
                    </button>
                  </li>
                ))}
                {m.documents.filter((f) => f.origin === "upload").map((f) => (
                  <li key={f.id} className="flex items-center gap-3 py-2.5">
                    <FileText size={15} className="shrink-0 text-cite" />
                    <span className="min-w-0 flex-1 truncate text-[15px] text-ink">{f.name}</span>
                    <span className="shrink-0 text-xs text-faint">{formatBytes(f.size)}</span>
                    <a href={api.fileUrl(f.id)} aria-label={t("fileDownload")}
                      className="rounded p-1 text-faint hover:text-ink"><Download size={14} /></a>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        <aside className="space-y-8 self-start rounded-2xl bg-desk p-5 lg:sticky lg:top-6">
          <DeadlinePanel matterId={m.id} deadlines={m.deadlines} onChanged={() => { load(); onChanged(); }} />
          <div className="border-t border-rule pt-5">
            <label htmlFor="matter-notes" className="text-xs text-muted">{t("matterNotes")}</label>
            <textarea id="matter-notes" value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes}
              rows={6} placeholder={t("matterNotesHint")}
              className="mt-1.5 w-full resize-y rounded-lg border border-transparent bg-sheet/70 p-2.5 text-sm leading-relaxed text-ink outline-none placeholder:text-faint focus:border-rule focus:bg-sheet" />
          </div>
        </aside>
      </div>

      {editing && (
        <MatterForm initial={{ client: m.client, subject: m.subject, opponent: m.opponent, court: m.court, case_no: m.case_no }}
          onSave={saveFields} onClose={() => setEditing(false)} />
      )}
    </div>
  );
}
