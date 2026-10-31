"use client";

// The message box: text, attachments (button, drag and drop anywhere, or paste), how much
// work the answer gets, and send/stop. What the message asks for (an answer, a list of
// decisions, a petition) is understood from the message itself, so there is no mode switch.
// Attachments upload as soon as they are added, so sending only links them to the message.
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, ChevronDown, FileText, Gauge, Loader2, Paperclip, Square, X } from "lucide-react";
import { AnswerChoices, picksText, type Clarification, type Picks } from "@/components/AnswerChoices";
import { api, ApiError, type StoredFile } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { t } from "@/lib/i18n";

export type Power = "fast" | "balanced" | "deep";
const POWERS: Power[] = ["fast", "balanced", "deep"];

type Pending = { key: string; name: string; file?: StoredFile; error?: string };

type Props = {
  followUp?: FollowUp;          // the last answer's questions with options, answered from here
  busy: boolean;
  onSubmit: (text: string, fileIds: string[], power: Power) => void;
  onStop: () => void;
  footer?: React.ReactNode;    // beside the box, below it (the usage meter)
  placeholder?: string;        // in a case file: asking in that file
};

function usePower(): [Power, (p: Power) => void] {
  const [power, setPower] = useState<Power>("balanced");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("power");
      if (saved && POWERS.includes(saved as Power)) setPower(saved as Power);
    } catch {}
  }, []);
  return [power, (p) => {
    setPower(p);
    try {
      localStorage.setItem("power", p);
    } catch {}
  }];
}

export type FollowUp = { key: string; items: Clarification[]; asked: boolean };

export function Composer({ followUp, busy, onSubmit, onStop, footer, placeholder }: Props) {
  const [text, setText] = useState("");
  const [picks, setPicks] = useState<Picks>({});
  const [closed, setClosed] = useState<string | null>(null);   // key of the dismissed questions
  const choices = followUp && closed !== followUp.key
    && (followUp.items.length > 0 || followUp.asked) ? followUp : null;
  const picked = choices ? picksText(choices.items, picks) : "";
  const [files, setFiles] = useState<Pending[]>([]);
  const [dragging, setDragging] = useState(false);
  const [powerOpen, setPowerOpen] = useState(false);
  const [power, setPower] = usePower();
  const area = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const uploading = files.some((f) => !f.file && !f.error);

  function add(list: FileList | File[]) {
    for (const file of Array.from(list)) {
      const key = `${file.name}-${file.size}-${Math.random()}`;
      setFiles((all) => [...all, { key, name: file.name || "yapistirilan" }]);
      api.uploadFile(file)
        .then((stored) => setFiles((all) => all.map((f) => (f.key === key ? { ...f, file: stored } : f))))
        .catch((err) => {
          const error = err instanceof ApiError && err.status === 507 ? t("attachFull")
            : err instanceof ApiError && err.status === 413 ? t("attachTooLarge", { name: file.name })
              : t("attachFailed", { name: file.name });
          setFiles((all) => all.map((f) => (f.key === key ? { ...f, error } : f)));
        });
    }
  }

  // Files dropped anywhere on the page come here.
  useEffect(() => {
    let depth = 0;
    // Not over an open panel ("learn from me" takes its own files).
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files")
      && !(e.target instanceof Element && e.target.closest('[role="dialog"]'));
    const enter = (e: DragEvent) => { if (hasFiles(e)) { depth += 1; setDragging(true); } };
    const leave = (e: DragEvent) => { if (hasFiles(e)) { depth -= 1; if (depth <= 0) setDragging(false); } };
    const over = (e: DragEvent) => { if (hasFiles(e)) e.preventDefault(); };
    const drop = (e: DragEvent) => {
      // Any drop ends the drag, also one a panel took, so the overlay never stays up.
      depth = 0;
      setDragging(false);
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer?.files.length) add(e.dataTransfer.files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, []);

  // New questions come with a new answer: earlier choices are cleared.
  useEffect(() => setPicks({}), [followUp?.key]);

  function send(lead = "") {
    const value = [lead, picked, text.trim()].filter(Boolean).join("\n");
    if (!value || busy || uploading) return;
    onSubmit(value, files.flatMap((f) => (f.file ? [f.file.id] : [])), power);
    setText("");
    setFiles([]);
    setPicks({});
    if (area.current) area.current.style.height = "";
  }

  return (
    <div>
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-cite/10">
          <div className="rounded-2xl border-2 border-dashed border-cite bg-sheet px-10 py-8 text-center">
            <Paperclip className="mx-auto text-cite" size={28} />
            <p className="mt-2 text-[15px] text-ink">{t("attachHint")}</p>
          </div>
        </div>
      )}
      <div className="rounded-2xl border border-rule bg-sheet shadow-[0_1px_2px_rgba(27,36,51,0.06)] focus-within:border-faint">
        {choices && (
          <AnswerChoices key={choices.key} items={choices.items} picks={picks} onPicks={setPicks}
            onWithout={choices.asked ? () => send(t("writeWithout")) : undefined}
            onClose={() => setClosed(choices.key)} />
        )}
        {files.length > 0 && (
          <ul className="flex flex-wrap gap-2 px-3 pt-3">
            {files.map((f) => (
              <li key={f.key} title={f.error ?? f.name}
                className={`flex max-w-[16rem] items-center gap-2 rounded-lg border px-2 py-1.5 text-sm ${f.error ? "border-danger/40 text-danger" : "border-rule text-ink"}`}>
                {f.file || f.error ? <FileText size={15} className="shrink-0 text-cite" />
                  : <Loader2 size={15} className="shrink-0 animate-spin text-faint" />}
                <span className="min-w-0 truncate">{f.name}</span>
                {f.file && <span className="shrink-0 text-xs text-faint">{formatBytes(f.file.size)}</span>}
                <button onClick={() => setFiles((all) => all.filter((x) => x.key !== f.key))}
                  aria-label={t("removeAttachment")} className="shrink-0 text-faint hover:text-ink">
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <textarea
          ref={area}
          value={text}
          rows={2}
          onChange={(e) => {
            setText(e.target.value);
            e.target.style.height = "";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 240)}px`;
          }}
          onPaste={(e) => {
            if (e.clipboardData.files.length) {
              e.preventDefault();
              add(e.clipboardData.files);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={placeholder ?? t("askPlaceholder")}
          aria-label={t("messageLabel")}
          className="block w-full resize-none bg-transparent px-4 pt-3 text-[15px] leading-relaxed outline-none placeholder:text-faint focus-visible:outline-none"
        />
        <div className="flex items-center gap-1 px-2 pb-2">
          <button onClick={() => picker.current?.click()} aria-label={t("attach")} title={t("attach")}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-paper hover:text-ink">
            <Paperclip size={17} />
          </button>
          <input ref={picker} type="file" multiple className="sr-only"
            onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />

          <div className="relative">
              <button onClick={() => setPowerOpen((o) => !o)} onMouseDown={(e) => e.stopPropagation()}
                aria-expanded={powerOpen} aria-label={t("power")}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:bg-paper hover:text-ink">
                <Gauge size={15} /> {t(`power_${power}`)} <ChevronDown size={14} />
              </button>
              {powerOpen && (
                <PowerMenu value={power} onPick={(p) => { setPower(p); setPowerOpen(false); }}
                  onClose={() => setPowerOpen(false)} />
              )}
          </div>

          <span className="flex-1" />
          {busy ? (
            <button onClick={onStop} aria-label={t("stopAnswer")} title={t("stopAnswer")}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-white">
              <Square size={12} fill="currentColor" />
            </button>
          ) : (
            <button onClick={() => send()} disabled={(!text.trim() && !picked) || uploading}
              aria-label={t("sendMessage")} title={t("sendMessage")}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-cite text-white disabled:bg-rule disabled:text-faint">
              <ArrowUp size={17} />
            </button>
          )}
        </div>
      </div>
      {footer && <div className="mt-1.5 flex justify-end">{footer}</div>}
    </div>
  );
}

function PowerMenu({ value, onPick, onClose }: { value: Power; onPick: (p: Power) => void; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const away = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && onClose();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [onClose]);
  return (
    <div ref={box} role="menu"
      className="absolute bottom-full left-0 z-30 mb-2 w-72 rounded-xl border border-rule bg-sheet p-1.5 shadow-xl">
      {POWERS.map((p) => (
        <button key={p} role="menuitemradio" aria-checked={p === value} onClick={() => onPick(p)}
          className="flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left hover:bg-paper">
          <span className="mt-0.5 w-4 shrink-0 text-cite">{p === value && <Check size={15} />}</span>
          <span>
            <span className="block text-sm font-medium text-ink">{t(`power_${p}`)}</span>
            <span className="block text-xs leading-relaxed text-muted">{t(`power_${p}_hint`)}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
