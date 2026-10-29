import { API_URL, ApiError, type Checked, type Evidence } from "./api";

// Server-sent events from POST /chats/{id}/messages (see legal_api/agent/answer.py).
export type StreamEvent =
  | { type: "question"; data: { id: string } }
  | { type: "status"; data: { message: string } }
  | { type: "plan"; data: { branches: Array<{ label: string; asks: string[] }> } }
  | { type: "evidence"; data: Evidence }
  | { type: "atom"; data: { branch: number; index: number; ask: string; found: boolean;
                              segments: Array<{ text: string; keys: string[] }> } }
  | { type: "delta"; data: { text: string } }
  | { type: "reset"; data: Record<string, never> }
  | { type: "checked"; data: Checked }
  | { type: "final"; data: { text: string; cost_usd: number; timings: Record<string, number> } }
  | { type: "saved"; data: { id: string } }
  | { type: "error"; data: Record<string, never> };

export async function askStream(
  chatId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/chats/${chatId}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status);

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
