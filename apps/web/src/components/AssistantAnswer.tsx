"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Checked, Evidence } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import { t } from "@/lib/i18n";
import { citationOrder, groupCitations, splitSections, toMarkdown } from "@/lib/markers";

type Props = {
  raw: string;
  evidence: Evidence[];
  checked?: Checked;
  streaming?: boolean;
  status?: string;
  repaired?: boolean;
  refused?: boolean;
  seconds?: number;
  cost?: number;
  asked?: boolean;                 // asked for facts before drafting a petition
  onOpenSource: (key: string) => void;
  draftAction?: React.ReactNode;   // shown under a petition answer: opens its draft
};

export function Chip({ n, onClick, label }: { n: number; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] -translate-y-px items-center justify-center rounded bg-cite-soft px-1 align-middle font-sans text-[0.7rem] font-semibold text-cite hover:bg-cite hover:text-white"
    >
      {n}
    </button>
  );
}

export function AssistantAnswer(props: Props) {
  const { evidence, checked, streaming, status, repaired, refused, seconds, cost,
    asked, onOpenSource, draftAction } = props;
  const raw = streaming ? props.raw : groupCitations(props.raw);
  const byKey = new Map(evidence.map((e) => [e.key, e]));
  const order = citationOrder(raw).filter((k) => byKey.has(k));
  const number = (key: string) => order.indexOf(key) + 1;

  const renderText = (text: string, className: string) => (
    <div className={className}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const key = href?.startsWith("#cite-") ? href.slice(6) : null;
            if (key && byKey.has(key)) {
              return (
                <Chip n={number(key)} label={byKey.get(key)!.citation} onClick={() => onOpenSource(key)} />
              );
            }
            if (key) return null;
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-cite underline">
                {children}
              </a>
            );
          },
        }}
      >
        {toMarkdown(text, streaming)}
      </Markdown>
    </div>
  );

  return (
    <div className="grid gap-x-10 @4xl:grid-cols-[minmax(0,42rem)_15rem]">
      <div className="min-w-0">
        {refused ? (
          <p className="text-muted">{t("refused")}</p>
        ) : (
          <Sections raw={raw} renderText={renderText} />
        )}

        {streaming && status && (
          <p className="mt-4 flex items-center gap-2 text-sm text-muted" aria-live="polite">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cite" />
            {status}
          </p>
        )}

        {!streaming && draftAction && <div className="mt-4">{draftAction}</div>}

        {!streaming && seconds !== undefined && (
          <p className="mt-4 text-xs text-faint">
            {cost !== undefined
              ? t("answeredInCost", { seconds: Math.round(seconds), cost: formatUsd(cost) })
              : t("answeredIn", { seconds: Math.round(seconds) })}
          </p>
        )}

        {!streaming && !refused && !asked && checked && (
          <Verification checked={checked} repaired={repaired} number={number} />
        )}

        {/* Narrow screens: sources follow the answer instead of sitting in the margin. */}
        {order.length > 0 && (
          <ol className="mt-6 space-y-2 border-t border-rule pt-4 @4xl:hidden">
            {order.map((key) => (
              <SourceNote key={key} n={number(key)} evidence={byKey.get(key)!} onOpen={onOpenSource} />
            ))}
          </ol>
        )}
      </div>

      <aside className="hidden @4xl:block" aria-label={t("sources")}>
        <ol className="sticky top-6 space-y-3 border-l border-rule pl-5">
          {order.map((key) => (
            <SourceNote key={key} n={number(key)} evidence={byKey.get(key)!} onOpen={onOpenSource} />
          ))}
          {evidence.length > 0 && (
            <li className="pt-1 text-xs text-faint">{t("sourcesFound", { count: evidence.length })}</li>
          )}
        </ol>
      </aside>
    </div>
  );
}

export function SourceNote({ n, evidence, onOpen }: { n: number; evidence: Evidence; onOpen: (k: string) => void }) {
  return (
    <li>
      <button onClick={() => onOpen(evidence.key)} className="group flex gap-2 text-left">
        <span className="mt-0.5 font-sans text-xs font-semibold text-cite">{n}</span>
        <span className="text-[0.8125rem] leading-snug text-muted group-hover:text-ink">
          {evidence.citation}
        </span>
      </button>
    </li>
  );
}

function Verification({
  checked,
  repaired,
  number,
}: {
  checked: Checked;
  repaired?: boolean;
  number: (key: string) => number;
}) {
  const [open, setOpen] = useState(false);
  const errors = checked.issues.filter((i) => i.severity === "error");
  const partial = checked.claims.filter((c) => c.verdict !== "supported");
  const tone = errors.length ? "danger" : partial.length ? "caution" : "verified";
  const summary = errors.length
    ? t("unverified", { count: errors.length + partial.length })
    : partial.length
      ? t("verifiedWithWarnings", { count: partial.length })
      : t("verified");
  const colors = {
    verified: "bg-verified-soft text-verified",
    caution: "bg-caution-soft text-caution",
    danger: "bg-[#f6e3e3] text-danger",
  }[tone];

  return (
    <div className={`mt-6 rounded-md px-3 py-2 text-sm ${colors}`}>
      <div className="flex items-start justify-between gap-4">
        <p>
          {summary}
          {repaired && <span className="block text-xs opacity-80">{t("repaired")}</span>}
        </p>
        {(errors.length > 0 || partial.length > 0) && (
          <button onClick={() => setOpen(!open)} className="shrink-0 underline-offset-2 hover:underline">
            {open ? t("hideDetails") : t("showDetails")}
          </button>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-2 border-t border-current/15 pt-2 text-ink">
          {errors.map((i, idx) => (
            <li key={`e${idx}`}>{i.message}</li>
          ))}
          {partial.map((c, idx) => (
            <li key={`c${idx}`}>
              <span className="font-serif italic">&ldquo;{c.sentence}&rdquo;</span>{" "}
              <span className="text-muted">
                [{c.keys.map(number).filter((n) => n > 0).join(", ")}] {c.note}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Sections({
  raw,
  renderText,
}: {
  raw: string;
  renderText: (text: string, className: string) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const { short, detail } = splitSections(raw);
  // Older answers (and any answer that ignores the format) render as one body.
  if (short === null) return renderText(detail, "answer text-ink");
  return (
    <div>
      {renderText(short, "answer answer-short text-ink")}
      {detail && (
        <div className="mt-5">
          <button
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            className="text-sm font-medium text-cite underline-offset-2 hover:underline"
          >
            {open ? t("detailClose") : t("detailOpen")}
          </button>
          {open && <div className="mt-3 border-l border-rule pl-4">{renderText(detail, "answer text-ink")}</div>}
        </div>
      )}
    </div>
  );
}
