import { API_URL, ApiError, type Checked, type Evidence } from "./api";

export type StepName = "understand" | "analyse" | "search" | "screen" | "references"
  | "caselaw" | "plan" | "answer" | "write" | "compose" | "calculate";
export type Step = { name: StepName; state: "active" | "done"; count?: number; done?: number;
  branches?: number; issues?: number };
// One line of the short answer: a branch's gists joined, with the sources they cite.
export type AnswerLine = { branch: number; text: string; keys: string[] };

// Server-sent events from POST /chats/{id}/messages (see legal_api/agent/answer.py).
export type StreamEvent =
  | { type: "question"; data: { id: string; content: string; started_at: number } }
  | { type: "cancelled"; data: Record<string, never> }
  | { type: "status"; data: { message: string } }
  | { type: "plan"; data: { branches: Array<{ label: string; asks: string[] }> } }
  | { type: "evidence"; data: Evidence }
  | { type: "atom"; data: { branch: number; index: number; ask: string; found: boolean;
                              segments: Array<{ text: string; keys: string[] }> } }
  | { type: "delta"; data: { text: string } }
  | { type: "reset"; data: Record<string, never> }
  | { type: "checked"; data: Checked }
  | { type: "final"; data: { text: string; checked?: Checked; cost_usd: number;
      timings: Record<string, number> } }
  | { type: "saved"; data: { id: string } }
  | { type: "route"; data: { kind: "new" | "reformat" | "followup" } }
  | { type: "step"; data: Step }
  | { type: "line"; data: AnswerLine }
  | { type: "title"; data: { chat_id: string; title: string } }
  | { type: "error"; data: Record<string, never> };

async function readEvents(res: Response, onEvent: (event: StreamEvent) => void): Promise<void> {
  if (!res.body) throw new ApiError(res.status);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const type = /^event: (.+)$/m.exec(block)?.[1];
      const data = /^data: (.+)$/m.exec(block)?.[1];
      if (type && data) onEvent({ type, data: JSON.parse(data) } as StreamEvent);
    }
  }
}

// Asks a question. The answer runs on the server; closing this stream does not stop it.
export type AskOptions = { fileIds?: string[]; power?: string };

export async function askStream(
  chatId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  options: AskOptions = {},
): Promise<void> {
  const res = await fetch(`${API_URL}/chats/${chatId}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, file_ids: options.fileIds ?? [], power: options.power }),
    signal,
  });
  if (!res.ok) throw new ApiError(res.status);
  await readEvents(res, onEvent);
}

// Follows the chat's running answer from its first event. False when nothing is running.
export async function followRun(
  chatId: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<boolean> {
  const res = await fetch(`${API_URL}/chats/${chatId}/run`, { credentials: "include", signal });
  if (res.status === 204) return false;
  if (!res.ok) throw new ApiError(res.status);
  await readEvents(res, onEvent);
  return true;
}
