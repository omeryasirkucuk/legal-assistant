"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Flag } from "lucide-react";
import { api, API_URL, type ReportContext, type ReportSummary } from "@/lib/api";
import { t } from "@/lib/i18n";

export function ReportButton({ chatId }: { chatId: string | null }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!description.trim() || saving) return;
    setSaving(true);
    setFailed(false);
    try {
      await api.reportProblem(description.trim(), chatId);
      setDescription("");
      setSent(true);
      dialog.current?.close();
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return <>
    {sent && <span role="status" className="self-center text-xs text-verified">{t("reportSuccess")}</span>}
    <button type="button" className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted hover:bg-sheet hover:text-ink"
      onClick={() => { setSent(false); setFailed(false); dialog.current?.showModal(); }}>
      <Flag size={13} />{t("report")}
    </button>
    <dialog ref={dialog} aria-labelledby="report-title" aria-describedby="report-warning"
      onCancel={(e) => { if (saving) e.preventDefault(); }}
      className="m-auto w-[min(94vw,28rem)] rounded-xl border border-rule bg-sheet p-5 text-ink shadow-xl backdrop:bg-black/35">
      <form onSubmit={submit}>
        <h2 id="report-title" className="font-serif text-xl">{t("report")}</h2>
        <p id="report-warning" className="mt-3 text-sm">{t("reportWarning")}</p>
        <p className="mt-1 text-xs text-muted">{t(chatId ? "reportScope" : "reportEmptyScope")}</p>
        <label className="mt-4 block text-sm">{t("reportDescription")}
          <textarea autoFocus required maxLength={5000} rows={4} value={description} disabled={saving}
            onChange={e => setDescription(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-rule bg-paper p-2" />
        </label>
        {failed && <p role="alert" className="mt-2 text-sm text-danger">{t("reportError")}</p>}
        <div className="mt-4 flex justify-end gap-3 text-sm">
          <button type="button" disabled={saving} onClick={() => dialog.current?.close()}>{t("cancel")}</button>
          <button disabled={saving || !description.trim()} className="rounded-md bg-cite px-3 py-2 text-white disabled:opacity-50">{t("reportSend")}</button>
        </div>
      </form>
    </dialog>
  </>;
}

function ReportDetails({ report }: { report: ReportSummary }) {
  const [context, setContext] = useState<ReportContext | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api.reportContext(report.id).then(value => { if (active) setContext(value); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [report.id]);
  return <div className="space-y-3 rounded-lg bg-paper p-3 text-sm">
    <p className="whitespace-pre-wrap break-words font-medium">{report.description}</p>
    {failed && <p role="alert">{t("reportLoadError")}</p>}
    {!context && !failed && <p>{t("loading")}</p>}
    {context && <>
      <h4 className="font-medium">{context.title}</h4>
      {context.messages.map((m, i) => <div key={i}>
        <strong>{t(m.role === "user" ? "reportUser" : "reportAssistant")}</strong>
        <p className="whitespace-pre-wrap break-words">{m.content}</p>
      </div>)}
      {context.files.map(f => <details key={f.id}>
        <summary className="cursor-pointer break-words">{f.name}</summary>
        <a className="text-cite underline" href={`${API_URL}/admin/reports/${report.id}/files/${f.id}`}>{t("reportOpenFile")}</a>
        <p className="whitespace-pre-wrap break-words">{f.text}</p>
      </details>)}
    </>}
  </div>;
}

export function ReportList() {
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  return <details className="mb-4 rounded-lg border border-rule bg-sheet p-3" onToggle={e => {
    if (e.currentTarget.open) {
      setFailed(false);
      api.reports().then(setReports).catch(() => setFailed(true));
    }
  }}>
    <summary className="cursor-pointer font-medium">{t("reportList")}</summary>
    {failed ? <p role="alert">{t("reportLoadError")}</p> : !reports ? <p>{t("loading")}</p>
      : !reports.length && <p className="mt-2 text-sm text-muted">{t("reportEmpty")}</p>}
    {reports?.map(report => <div key={report.id} className="mt-2 border-t border-rule">
      <button aria-expanded={selected === report.id} className="block w-full py-2 text-left text-sm"
        onClick={() => setSelected(selected === report.id ? null : report.id)}>
        <span className="block text-xs text-muted">{report.email} · {new Date(report.created_at).toLocaleString("tr-TR")}</span>
        <span className="block truncate">{report.description}</span>
      </button>
      {selected === report.id && <ReportDetails report={report} />}
    </div>)}
  </details>;
}
