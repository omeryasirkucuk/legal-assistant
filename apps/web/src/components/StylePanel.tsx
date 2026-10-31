"use client";

// My writing style: how the lawyer's petitions are written, in plain words. Length and language
// are picked from three choices each (or left to be learnt); the lawyer's own petitions and
// written wishes teach the rest.
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { SampleLibrary } from "@/components/SampleLibrary";
import {
  api,
  type PetitionType,
  type StyleLength,
  type StyleProfile,
  type StyleRegister,
  type StyleSample,
} from "@/lib/api";
import { t } from "@/lib/i18n";

const LENGTHS: StyleLength[] = ["short", "medium", "long"];
const REGISTERS: StyleRegister[] = ["plain", "balanced", "formal"];

function Choice<T extends string>({ label, value, options, name, onPick }: {
  label: string; value: T | null; options: T[]; name: (v: T | "auto") => string;
  onPick: (v: T | null) => void;
}) {
  const all: Array<T | "auto"> = ["auto", ...options];
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-ink">{label}</p>
      <div role="radiogroup" aria-label={label} className="grid grid-cols-2 gap-1 rounded-lg bg-desk p-1 sm:grid-cols-4">
        {all.map((o) => {
          const on = (o === "auto" && value === null) || o === value;
          return (
            <button key={o} role="radio" aria-checked={on}
              onClick={() => onPick(o === "auto" ? null : o)}
              className={`rounded-md px-2 py-1.5 text-sm ${on ? "bg-sheet font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
              {name(o)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function StylePanel({ onClose }: { onClose: () => void }) {
  const [types, setTypes] = useState<PetitionType[]>([]);
  const [samples, setSamples] = useState<StyleSample[]>([]);
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [wishes, setWishes] = useState("");
  const [status, setStatus] = useState<"idle" | "saved">("idle");
  const [learnt, setLearnt] = useState<Array<{ id: string; text: string; used: boolean }>>([]);
  const [reset, setReset] = useState<"idle" | "confirm" | "done">("idle");

  async function reload() {
    const [s, p, m] = await Promise.all([api.samples(), api.styleProfile(), api.memories()]);
    setSamples(s);
    setLearnt(m);
    setProfile(p);
    setWishes(p.rules.join("\n"));
  }

  useEffect(() => {
    api.petitionTypes().then(setTypes).catch(() => {});
    reload().catch(() => {});
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function choose(length: StyleLength | null, register: StyleRegister | null) {
    setProfile(await api.chooseStyle(length, register));
  }

  const prefs = profile?.preferences;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/20"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section role="dialog" aria-modal="true" aria-labelledby="style-title"
        className="flex h-full w-full max-w-lg flex-col overflow-y-auto bg-sheet shadow-2xl">
        <header className="flex items-start justify-between gap-4 px-7 pb-2 pt-7">
          <div>
            <h2 id="style-title" className="font-serif text-2xl text-ink">{t("myPetitions")}</h2>
            <p className="mt-2 text-[15px] leading-relaxed text-muted">{t("styleIntro")}</p>
          </div>
          <button onClick={onClose} aria-label={t("close")} className="rounded-md p-1.5 text-faint hover:bg-paper hover:text-ink">
            <X size={18} />
          </button>
        </header>

        {profile && prefs && (
          <div className="space-y-6 px-7 py-6">
            <p className="rounded-lg bg-cite-soft px-4 py-3 text-[15px] leading-relaxed text-ink">
              {t("styleNow", {
                pages: profile.overall.pages.toLocaleString("tr-TR"),
                register: t(`registerWord_${profile.overall.register}`),
              })}
              {profile.overall.closing && t("styleNowClosing", { closing: profile.overall.closing })}
            </p>
            <Choice label={t("styleLength")} value={prefs.length} options={LENGTHS}
              name={(v) => t(`length_${v}`)} onPick={(v) => choose(v, prefs.register)} />
            <Choice label={t("styleLanguage")} value={prefs.register} options={REGISTERS}
              name={(v) => t(`register_${v}`)} onPick={(v) => choose(prefs.length, v)} />
            <p className="text-xs leading-relaxed text-faint">{t("styleAutoHint")}</p>
          </div>
        )}

        <div className="border-t border-rule px-7 py-6">
          <h3 className="font-serif text-lg text-ink">{t("ownPetitions")}</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">{t("ownPetitionsHint")}</p>

          <SampleLibrary types={types} samples={samples} onChanged={reload} />
        </div>

        <div className="border-t border-rule px-7 py-6">
          <h3 className="font-serif text-lg text-ink">{t("wishes")}</h3>
          <textarea value={wishes} onChange={(e) => { setWishes(e.target.value); setStatus("idle"); }}
            rows={4} placeholder={t("wishesHint")}
            className="mt-3 w-full rounded-md border border-rule bg-sheet p-3 text-sm leading-relaxed text-ink placeholder:text-faint" />
          <button onClick={async () => { await api.saveRules(wishes.split("\n")); await reload(); setStatus("saved"); }}
            className="mt-2 rounded-md border border-rule px-3 py-1.5 text-sm text-ink hover:bg-paper">
            {status === "saved" ? t("saved") : t("saveWishes")}
          </button>
        </div>
        <div className="border-t border-rule px-7 py-6">
          <h3 className="font-serif text-lg text-ink">{t("learnt")}</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">{t("learntHint")}</p>
          <ul className="mt-3 space-y-1">
            {learnt.length === 0 && <li className="text-sm text-faint">{t("learntNone")}</li>}
            {learnt.map((m) => (
              <li key={m.id} className="group flex items-start gap-3 rounded-md px-2 py-2 hover:bg-paper">
                <span className="min-w-0 flex-1 text-sm leading-relaxed text-ink">
                  {m.text}
                  <span className={`ml-2 text-xs ${m.used ? "text-verified" : "text-faint"}`}>
                    {m.used ? t("learntUsed") : t("learntWaiting")}
                  </span>
                </span>
                <button onClick={() => api.deleteMemory(m.id).then(reload)}
                  className="shrink-0 text-xs text-faint opacity-0 hover:text-danger group-hover:opacity-100 focus-visible:opacity-100">
                  {t("learntRemove")}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="border-t border-rule px-7 py-6">
          <button
            onClick={async () => {
              if (reset !== "confirm") return setReset("confirm");
              setProfile(await api.resetStyle());
              await reload();
              setReset("done");
            }}
            onBlur={() => reset === "confirm" && setReset("idle")}
            className={`rounded-md border px-3 py-1.5 text-sm ${reset === "confirm" ? "border-danger bg-danger text-white" : "border-rule text-danger hover:bg-paper"}`}>
            {reset === "confirm" ? t("resetStyleConfirm") : reset === "done" ? t("resetDone") : t("resetStyle")}
          </button>
          <p className="mt-2 text-xs leading-relaxed text-faint">{t("resetStyleHint")}</p>
        </div>
      </section>
    </div>
  );
}
