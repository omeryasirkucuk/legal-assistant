"use client";

// The last answer's questions with one-click options, docked to the top of the message box
// as part of it: one question at a time on one line, its options as compact choices below.
// Choosing marks an option and moves on to the next unanswered question; the counter steps
// back and forth. Whatever is chosen is sent together with what the lawyer types.
import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import { t } from "@/lib/i18n";

export type Clarification = { question: string; options: string[] };
export type Picks = Record<string, string>;

/** The chosen options as lines of the message ("Question? Answer"). */
export function picksText(items: Clarification[], picks: Picks): string {
  return items.filter((i) => picks[i.question]).map((i) => `${i.question} ${picks[i.question]}`).join("\n");
}

const ADVANCE_MS = 200;

export function AnswerChoices({ items, picks, onPicks, onWithout, onClose }: {
  items: Clarification[];
  picks: Picks;
  onPicks: (picks: Picks) => void;
  onWithout?: () => void;           // the answer asked for facts before drafting
  onClose: () => void;
}) {
  const [at, setAt] = useState(0);     // the parent keys this by answer, so it restarts
  const item = items[Math.min(at, items.length - 1)] as Clarification | undefined;
  const many = items.length > 1;

  function choose(option: string) {
    if (!item) return;
    const next = { ...picks };
    if (next[item.question] === option) delete next[item.question];
    else next[item.question] = option;
    onPicks(next);
    if (next[item.question]) {
      const following = items.findIndex((q, i) => i > at && !next[q.question]);
      if (following >= 0) setTimeout(() => setAt(following), ADVANCE_MS);
    }
  }

  const step = "flex h-6 w-6 items-center justify-center rounded-md text-faint hover:bg-sheet hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent";

  return (
    <section aria-label={t("choicesLabel")} className="rounded-t-2xl border-b border-rule bg-paper/70 px-4 pb-3 pt-2.5">
      <div className="flex items-center gap-2">
        <p className="min-w-0 flex-1 text-[14px] font-medium leading-snug text-ink">
          {item?.question}
        </p>
        {many && (
          <div className="flex shrink-0 items-center text-xs tabular-nums text-faint">
            <button onClick={() => setAt(at - 1)} disabled={at === 0} aria-label={t("choicesPrev")} className={step}>
              <ChevronLeft size={14} />
            </button>
            <span className="w-8 text-center">{at + 1}/{items.length}</span>
            <button onClick={() => setAt(at + 1)} disabled={at >= items.length - 1} aria-label={t("choicesNext")} className={step}>
              <ChevronRight size={14} />
            </button>
          </div>
        )}
        <button onClick={onClose} aria-label={t("close")} className={`${step} -mr-1.5 shrink-0`}>
          <X size={14} />
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label={item?.question}>
        {item?.options.map((option) => {
          const on = picks[item.question] === option;
          return (
            <button key={option} role="radio" aria-checked={on} onClick={() => choose(option)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[13px] transition-colors ${
                on ? "border-ink bg-ink text-white" : "border-rule bg-sheet text-ink hover:border-faint"
              }`}>
              {on && <Check size={13} strokeWidth={2.5} />}
              {option}
            </button>
          );
        })}
        {onWithout && (
          <button onClick={onWithout}
            className="ml-auto h-8 rounded-lg px-2 text-[13px] text-muted underline-offset-2 hover:text-ink hover:underline">
            {t("writeWithoutButton")}
          </button>
        )}
      </div>
    </section>
  );
}
