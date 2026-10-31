"use client";

// Asked before sending, when a message outside any file names one: ask it with that file
// (its details and documents go with it, and the chat moves into the file) or without.
// When several files are named they are listed for the lawyer to pick; none is guessed.
import { FolderOpen } from "lucide-react";
import type { Matter } from "@/lib/api";
import { t } from "@/lib/i18n";

export function MatterSuggest({ question, candidates, onWith, onWithout }: {
  question: string;                 // the held message, shown so the lawyer sees what waits
  candidates: Matter[];
  onWith: (m: Matter) => void;
  onWithout: () => void;
}) {
  const one = candidates.length === 1 ? candidates[0] : null;
  return (
    <div role="dialog" aria-label={t("matterSuggestTitle")}
      className="mb-2 rounded-xl border border-rule bg-sheet px-4 py-3 shadow-sm">
      <p className="mb-2 line-clamp-2 border-l-2 border-rule pl-2.5 text-sm text-muted">{question}</p>
      <p className="flex items-center gap-2 text-sm text-ink">
        <FolderOpen size={15} className="shrink-0 text-cite" />
        {one ? t("matterSuggestOne", { client: one.client }) : t("matterSuggestMany")}
      </p>
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        {candidates.map((m) => (
          <button key={m.id} onClick={() => onWith(m)} autoFocus={m === candidates[0]}
            className="rounded-lg bg-ink px-3 py-1.5 text-sm text-white hover:brightness-110">
            {one ? t("matterSuggestWith") : `${m.client}${m.subject ? `, ${m.subject}` : ""}`}
          </button>
        ))}
        <button onClick={onWithout}
          className="rounded-lg border border-rule px-3 py-1.5 text-sm text-ink hover:bg-paper">
          {t("matterSuggestWithout")}
        </button>
      </div>
    </div>
  );
}
