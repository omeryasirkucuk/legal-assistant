"use client";

import { useEffect, useState } from "react";
import type { Evidence } from "@/lib/api";
import { t } from "@/lib/i18n";
import { citationOrder } from "@/lib/markers";
import { linesText, type Pending } from "@/lib/pending";
import type { AnswerLine } from "@/lib/stream";
import { AnswerProgress } from "./AnswerProgress";
import { AssistantAnswer, Chip, SourceNote } from "./AssistantAnswer";

const WORDS_PER_TICK = 2;
const TICK_MS = 35;

// A line as it arrives: words appear in order, then its citation chips.
function RevealLine({ line, number, byKey, onOpen }: {
  line: AnswerLine;
  number: (key: string) => number;
  byKey: Map<string, Evidence>;
  onOpen: (key: string) => void;
}) {
  const words = line.text.split(" ");
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (shown >= words.length) return;
    const timer = setTimeout(() => setShown((n) => n + WORDS_PER_TICK), TICK_MS);
    return () => clearTimeout(timer);
  }, [shown, words.length]);
  const done = shown >= words.length;
  const colon = line.text.indexOf(":");
  const text = words.slice(0, shown).join(" ");
  return (
    <li>
      {colon > 0 && text.length > colon ? (
        <>
          <span className="font-medium">{text.slice(0, colon + 1)}</span>
          {text.slice(colon + 1)}
        </>
      ) : (
        text
      )}
      {done &&
        line.keys.filter((k) => byKey.has(k)).map((k) => (
          <Chip key={k} n={number(k)} label={byKey.get(k)!.citation} onClick={() => onOpen(k)} />
        ))}
    </li>
  );
}

// The answer while it is being written: progress on top, then one row per case of the plan.
// A case shows its name until its line is ready; lines only ever get added.
export function StreamingAnswer({ pending, onOpenSource }: {
  pending: Pending;
  onOpenSource: (key: string) => void;
}) {
  // A written answer arrives as text: shown as it is written, citation chips at the end.
  if (!pending.plan.length) {
    const raw = pending.finalText ?? pending.text;
    return (
      <div>
        <div className="@4xl:max-w-[42rem]">
          <AnswerProgress steps={pending.steps} startedAt={pending.startedAt} />
        </div>
        {raw && (
          <AssistantAnswer raw={raw} evidence={pending.evidence} checked={pending.checked}
            streaming={pending.finalText === undefined} onOpenSource={onOpenSource} />
        )}
      </div>
    );
  }
  const byKey = new Map(pending.evidence.map((e) => [e.key, e]));
  const order = citationOrder(linesText(pending)).filter((k) => byKey.has(k));
  const number = (key: string) => order.indexOf(key) + 1;

  return (
    <div className="grid gap-x-10 @4xl:grid-cols-[minmax(0,42rem)_15rem]">
      <div className="min-w-0">
        <AnswerProgress steps={pending.steps} startedAt={pending.startedAt} />
        {pending.plan.length > 0 && (
          <ul className="answer answer-short text-ink">
            {pending.plan.map((branch, i) =>
              pending.lines[i] ? (
                <RevealLine key={i} line={pending.lines[i]} number={number} byKey={byKey}
                  onOpen={onOpenSource} />
              ) : (
                <li key={i} className="text-faint">
                  <span className="font-medium">{branch.label}</span>
                  <span className="ml-2 animate-pulse text-sm">{t("branchPending")}</span>
                </li>
              ),
            )}
          </ul>
        )}
      </div>
      <aside className="hidden @4xl:block" aria-label={t("sources")}>
        <ol className="sticky top-6 space-y-3 border-l border-rule pl-5">
          {order.map((key) => (
            <SourceNote key={key} n={number(key)} evidence={byKey.get(key)!} onOpen={onOpenSource} />
          ))}
          {pending.evidence.length > 0 && (
            <li className="pt-1 text-xs text-faint">
              {t("sourcesFound", { count: pending.evidence.length })}
            </li>
          )}
        </ol>
      </aside>
    </div>
  );
}
