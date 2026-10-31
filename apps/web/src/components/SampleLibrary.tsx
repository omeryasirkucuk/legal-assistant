"use client";

// The lawyer's own petitions, to learn their style from. Many files of different formats can
// be added at once (picked or dropped); the server has the model read each (its petition
// type, area of law and matter) and refuses what would teach a wrong style (a decision, a
// copy, a scan with no text). The list is grouped by petition type, and a wrongly sorted one is fixed in place.
import { useRef, useState } from "react";
import { Check, FileText, Loader2, RefreshCw, Upload, X } from "lucide-react";
import { api, ApiError, type PetitionType, type StyleSample } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";

const ACCEPT = ".docx,.udf,.pdf,.odt,.rtf,.txt";
const ERRORS = ["duplicate", "not_petition", "no_text", "unreadable", "unsupported", "too_short"];

type Result = {
  key: string; name: string; state: "reading" | "added" | "failed" | "similar"; note: string;
  file?: File; similarId?: string;    // an edited copy of a sample: the lawyer chooses
};

function errorNote(err: unknown): string {
  const detail = err instanceof ApiError ? err.detail : undefined;
  const code = typeof detail === "string" && ERRORS.includes(detail) ? detail : "other";
  return t(`sampleError_${code}` as MessageKey);
}

function similarTo(err: unknown): { id: string; title: string } | null {
  const d = err instanceof ApiError ? err.detail : undefined;
  return d && typeof d === "object" && (d as { code?: string }).code === "similar"
    ? (d as { id: string; title: string }) : null;
}

export function SampleLibrary({ types, samples, onChanged }: {
  types: PetitionType[]; samples: StyleSample[]; onChanged: () => Promise<void>;
}) {
  const [results, setResults] = useState<Result[]>([]);
  const [over, setOver] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const busy = results.some((r) => r.state === "reading");
  const kindName = (id: string | null) =>
    types.find((x) => x.id === id)?.name ?? t("petitionKindUnknown");

  async function add(list: FileList | File[]) {
    const files = Array.from(list);
    const batch = files.map((f, i) => ({ key: `${Date.now()}-${i}`, name: f.name, state: "reading" as const, note: "" }));
    setResults(batch);
    // One at a time: each is read, sorted and measured on the server.
    for (const [i, file] of files.entries()) {
      const update = await send(file);
      setResults((all) => all.map((r) => (r.key === batch[i].key ? { ...r, ...update } : r)));
    }
    await onChanged();
  }

  async function send(file: File, choice?: { replace?: string; keep?: boolean }): Promise<Partial<Result>> {
    try {
      const s = await api.uploadSample(file, choice);
      const about = s.matter ? `${kindName(s.petition_type)}, ${s.matter}` : kindName(s.petition_type);
      return { state: "added", note: t("sampleAdded", { kind: about }), file: undefined };
    } catch (err) {
      const similar = similarTo(err);
      if (similar) {
        return { state: "similar", note: t("sampleSimilar", { title: similar.title }), file, similarId: similar.id };
      }
      return { state: "failed", note: errorNote(err) };
    }
  }

  async function decide(r: Result, choice: { replace?: string; keep?: boolean }) {
    if (!r.file) return;
    setResults((all) => all.map((x) => (x.key === r.key ? { ...x, state: "reading" } : x)));
    const update = await send(r.file, choice);
    setResults((all) => all.map((x) => (x.key === r.key ? { ...x, ...update } : x)));
    await onChanged();
  }

  async function retype(s: StyleSample, petitionType: string) {
    await api.setSampleType(s.id, petitionType || null);
    await onChanged();
  }

  const groups = [...types.map((x) => x.id), null]
    .map((id) => ({ id, items: samples.filter((s) => s.petition_type === id) }))
    .filter((g) => g.items.length > 0);
  const added = results.filter((r) => r.state === "added").length;
  const skipped = results.filter((r) => r.state === "failed").length;
  const waiting = results.some((r) => r.state === "similar");

  return (
    <div>
      <button type="button" onClick={() => picker.current?.click()} disabled={busy}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (e.dataTransfer.files.length) add(e.dataTransfer.files);
        }}
        className={`mt-4 flex w-full flex-col items-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 text-center disabled:opacity-60 ${over ? "border-cite bg-cite-soft" : "border-rule hover:border-faint"}`}>
        {busy ? <Loader2 size={20} className="animate-spin text-faint" /> : <Upload size={20} className="text-cite" />}
        <span className="text-sm font-medium text-ink">{t("dropPetitionsHere")}</span>
        <span className="text-xs leading-relaxed text-faint">{t("dropPetitionHint")}</span>
      </button>
      <input ref={picker} type="file" multiple accept={ACCEPT} className="sr-only"
        onChange={(e) => { if (e.target.files?.length) add(e.target.files); e.target.value = ""; }} />

      {results.length > 0 && (
        <div className="mt-3 rounded-lg bg-paper px-3 py-2">
          {!busy && <p className="mb-1 text-xs text-muted">
            {t("samplesUploaded", { added, skipped })}{waiting && ` ${t("samplesWaiting")}`}
          </p>}
          <ul className="space-y-1">
            {results.map((r) => (
              <li key={r.key} className="flex items-start gap-2 text-xs">
                {r.state === "reading" ? <Loader2 size={13} className="mt-0.5 shrink-0 animate-spin text-faint" />
                  : r.state === "added" ? <Check size={13} className="mt-0.5 shrink-0 text-verified" />
                    : r.state === "similar" ? <RefreshCw size={13} className="mt-0.5 shrink-0 text-cite" />
                    : <X size={13} className="mt-0.5 shrink-0 text-danger" />}
                <span className="min-w-0">
                  <span className="block truncate text-ink">{r.name}</span>
                  <span className={r.state === "failed" ? "text-danger" : r.state === "similar" ? "text-ink" : "text-faint"}>
                    {r.state === "reading" ? t("sampleReading") : r.note}
                  </span>
                  {r.state === "similar" && (
                    <span className="mt-1 flex gap-2">
                      <button onClick={() => decide(r, { replace: r.similarId })}
                        className="rounded bg-cite px-2 py-0.5 text-white">{t("sampleReplace")}</button>
                      <button onClick={() => decide(r, { keep: true })}
                        className="rounded border border-rule px-2 py-0.5 text-ink hover:bg-sheet">{t("sampleKeepBoth")}</button>
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {samples.length === 0 && <p className="mt-4 text-sm text-faint">{t("noSamples")}</p>}
      {groups.map((g) => (
        <section key={g.id ?? "unknown"} className="mt-4">
          <h4 className="px-2 text-xs font-medium text-muted">{kindName(g.id)} ({g.items.length})</h4>
          <ul className="mt-1 space-y-0.5">
            {g.items.map((s) => (
              <li key={s.id} className="group flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-paper">
                <FileText size={16} className="shrink-0 text-cite" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{s.title}</span>
                  <span className="block truncate text-xs text-faint">
                    {s.area === "other" ? t("otherAreaShort") : t(`area_${s.area}` as MessageKey)}
                    {s.matter && ` · ${s.matter}`}
                    {" · "}{t(`format_${s.format}` as MessageKey)}
                  </span>
                </span>
                <select value={s.petition_type ?? ""} onChange={(e) => retype(s, e.target.value)}
                  aria-label={t("sampleTypeLabel")}
                  className="max-w-[9rem] rounded border border-transparent bg-transparent py-0.5 text-xs text-muted hover:border-rule focus-visible:border-cite">
                  <option value="">{t("petitionKindUnknown")}</option>
                  {types.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                </select>
                <button onClick={() => api.deleteSample(s.id).then(onChanged)}
                  className="text-xs text-faint opacity-0 hover:text-danger group-hover:opacity-100 focus-visible:opacity-100">
                  {t("sampleRemove")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
