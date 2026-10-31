// The answer being streamed, built up from server-sent events. Nothing shown is taken back:
// steps only advance, sources and lines are only added.
import type { Checked, Evidence } from "./api";
import type { AnswerLine, Step, StreamEvent } from "./stream";

export type Pending = {
  question: string;
  startedAt: number;
  steps: Step[];
  plan: Array<{ label: string; asks: string[] }>;
  lines: Record<number, AnswerLine>;
  evidence: Evidence[];
  checked?: Checked;
  text: string;          // the answer as it is written (delta events)
  finalText?: string;
  error?: boolean;
  budget?: boolean;
};

export function startPending(question: string, startedAt = Date.now()): Pending {
  return { question, startedAt, steps: [], plan: [], lines: {}, evidence: [], text: "" };
}

function withStep(steps: Step[], step: Step): Step[] {
  const i = steps.findIndex((s) => s.name === step.name);
  if (i < 0) return [...steps, step];
  const next = steps.slice();
  next[i] = step;
  return next;
}

export function applyEvent(p: Pending, e: StreamEvent): Pending {
  switch (e.type) {
    case "question":
      return { ...p, question: e.data.content, startedAt: e.data.started_at };
    case "step":
      return { ...p, steps: withStep(p.steps, e.data) };
    case "evidence":
      return p.evidence.some((x) => x.key === e.data.key) ? p : { ...p, evidence: [...p.evidence, e.data] };
    case "plan":
      return { ...p, plan: e.data.branches };
    case "line":
      return { ...p, lines: { ...p.lines, [e.data.branch]: e.data } };
    case "checked":
      return { ...p, checked: e.data };
    case "delta":
      return { ...p, text: p.text + e.data.text };
    case "final":
      return { ...p, finalText: e.data.text, checked: e.data.checked ?? p.checked };
    default:
      return p;
  }
}

// The streamed short answer as message text, branches in plan order, so citation numbers
// are assigned the same way as for a saved message.
export function linesText(p: Pending): string {
  return p.plan
    .map((_, i) => p.lines[i])
    .filter((l): l is AnswerLine => !!l)
    .map((l) => `- ${l.text}${l.keys.map((k) => ` [[${k}]]`).join("")}`)
    .join("\n");
}
