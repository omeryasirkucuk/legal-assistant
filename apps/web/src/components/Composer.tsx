"use client";

import { useRef, useState } from "react";
import { t } from "@/lib/i18n";

export type Mode = "ask" | "search";

type Props = {
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  busy: boolean;
  onSubmit: (text: string) => void;
  onStop: () => void;
};

export function Composer({ mode, onModeChange, busy, onSubmit, onStop }: Props) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  function send() {
    const value = text.trim();
    if (!value || busy) return;
    onSubmit(value);
    setText("");
    if (area.current) area.current.style.height = "";
  }

  return (
    <div className="rounded-xl border border-rule bg-sheet shadow-[0_1px_0_rgba(27,36,51,0.04)] focus-within:border-faint">
      <textarea
        ref={area}
        value={text}
        rows={2}
        onChange={(e) => {
          setText(e.target.value);
          e.target.style.height = "";
          e.target.style.height = `${Math.min(e.target.scrollHeight, 240)}px`;
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
          }
        }}
        placeholder={mode === "ask" ? t("askPlaceholder") : t("searchPlaceholder")}
        aria-label={mode === "ask" ? t("modeAsk") : t("modeSearch")}
        className="block w-full resize-none bg-transparent px-4 pt-3 text-[15px] leading-relaxed outline-none placeholder:text-faint"
      />
      <div className="flex items-center justify-between px-2 pb-2">
        <div role="radiogroup" className="flex rounded-md bg-paper p-0.5 text-sm">
          {(["ask", "search"] as const).map((m) => (
            <button
              key={m}
              role="radio"
              aria-checked={mode === m}
              onClick={() => onModeChange(m)}
              className={`rounded px-3 py-1 ${mode === m ? "bg-sheet font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}
            >
              {m === "ask" ? t("modeAsk") : t("modeSearch")}
            </button>
          ))}
        </div>
        {busy ? (
          <button onClick={onStop} className="rounded-md px-3 py-1.5 text-sm text-muted hover:text-ink">
            {t("stop")}
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!text.trim()}
            className="rounded-md bg-ink px-4 py-1.5 text-sm font-medium text-white disabled:opacity-30"
          >
            {t("send")}
          </button>
        )}
      </div>
    </div>
  );
}
