"use client";

import { useEffect, useState } from "react";
import { t, type MessageKey } from "@/lib/i18n";
import type { Step, StepName } from "@/lib/stream";

const LABELS: Record<StepName, [MessageKey, MessageKey]> = {
  understand: ["stepUnderstand", "stepUnderstandDone"],
  analyse: ["stepAnalyse", "stepAnalyseDone"],
  caselaw: ["stepCaselaw", "stepCaselawDone"],
  calculate: ["stepCalculate", "stepCalculateDone"],
  write: ["stepWrite", "stepWriteDone"],
  search: ["stepSearch", "stepSearchDone"],
  screen: ["stepScreen", "stepScreenDone"],
  references: ["stepReferences", "stepReferencesDone"],
  plan: ["stepPlan", "stepPlanDone"],
  answer: ["stepAnswer", "stepAnswerDone"],
  compose: ["stepCompose", "stepComposeDone"],
};

function label(step: Step): string {
  const [active, done] = LABELS[step.name];
  return t(step.state === "done" ? done : active, {
    count: step.count ?? step.issues ?? 0, done: step.done ?? 0, branches: step.branches ?? 0,
  });
}

// What the assistant is doing right now, with a running clock, so it is always visible that
// work is going on and where it stands.
export function AnswerProgress({ steps, startedAt }: { steps: Step[]; startedAt: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));

  return (
    <div className="mb-6 rounded-md border border-rule bg-sheet px-4 py-3" aria-live="polite">
      <div className="flex items-center justify-between text-xs text-faint">
        <span className="flex items-center gap-2">
          <span className="heartbeat h-1.5 w-1.5 rounded-full bg-cite" />
          {steps.length ? label(steps[steps.length - 1]) : t("stepUnderstand")}
        </span>
        <span className="tabular-nums">{t("elapsed", { seconds })}</span>
      </div>
      {steps.length > 0 && (
        <ol className="mt-2 space-y-1 text-[13px]">
          {steps.map((step) => (
            <li key={step.name} className="flex items-center gap-2">
              <span
                aria-hidden
                className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${
                  step.state === "done" ? "bg-verified-soft text-verified" : "bg-cite-soft text-cite"
                }`}
              >
                {step.state === "done" ? "✓" : <span className="heartbeat h-1.5 w-1.5 rounded-full bg-cite" />}
              </span>
              <span className={step.state === "done" ? "text-muted" : "text-ink"}>{label(step)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
