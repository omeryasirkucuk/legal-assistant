export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Health = {
  app: string;
  status: "ok" | "degraded";
  database: boolean;
  pgvector: boolean;
};

export type User = { id: string; email: string; name: string; is_admin: boolean };
export type LLMSettings = {
  provider: "openai_compatible";
  is_saved: boolean;
  base_url: string;
  model_main: string;
  model_draft: string;
  model_cheap: string;
  model_judge: string;
  api_key_configured: boolean;
};
export type LLMModel = { id: string; name: string };
export type ChatSummary = { id: string; title: string; updated_at: string };
export type Evidence = { key: string; kind: "decision" | "article"; citation: string; url: string };
export type Issue = { kind: string; severity: "error" | "warning"; paragraph: number; message: string };
export type Claim = {
  sentence: string;
  keys: string[];
  verdict: "supported" | "partial" | "not_supported";
  note: string;
};
export type Checked = { issues: Issue[]; claims: Claim[] };
export type MessageMeta = {
  checked?: Checked;
  repaired?: boolean;
  refused?: boolean;
  cost_usd?: number;
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta: MessageMeta;
  evidence: Evidence[];
  created_at: string;
};
export type SourceText = Evidence & { text: string; fetched_at: string };
export type DecisionHit = { id: string; citation: string; url: string; passage: string };
export type HistoryHit = { chat_id: string; title: string; snippet: string };

export class ApiError extends Error {
  constructor(public status: number) {
    super(`API ${status}`);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) throw new ApiError(res.status);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  me: () => call<User>("/auth/me"),
  login: (email: string, password: string) => call<User>("/auth/login", json({ email, password })),
  register: (name: string, email: string, password: string, invite_code: string) =>
    call<User>("/auth/register", json({ name, email, password, invite_code })),
  logout: () => call<void>("/auth/logout", { method: "POST" }),
  chats: () => call<ChatSummary[]>("/chats"),
  createChat: (content: string) => call<ChatSummary>("/chats", json({ content })),
  renameChat: (id: string, title: string) =>
    call<ChatSummary>(`/chats/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteChat: (id: string) => call<void>(`/chats/${id}`, { method: "DELETE" }),
  messages: (id: string) => call<Message[]>(`/chats/${id}/messages`),
  searchHistory: (q: string) => call<HistoryHit[]>(`/chats/search?q=${encodeURIComponent(q)}`),
  source: (chatId: string, messageId: string, key: string) =>
    call<SourceText>(`/chats/${chatId}/messages/${messageId}/evidence/${key}`),
  searchDecisions: (q: string) =>
    call<DecisionHit[]>(`/search/decisions?q=${encodeURIComponent(q)}`),
  llmSettings: () => call<LLMSettings>("/settings/llm"),
  saveLLMSettings: (body: Omit<LLMSettings, "provider" | "is_saved" | "api_key_configured"> &
    { api_key?: string; clear_api_key: boolean }) =>
    call<LLMSettings>("/settings/llm", { method: "PUT", body: JSON.stringify(body) }),
  llmModels: () => call<LLMModel[]>("/settings/llm/models"),
  testLLM: () => call<{ ok: boolean; model: string }>("/settings/llm/test", { method: "POST" }),
};

export async function fetchHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return res.ok ? ((await res.json()) as Health) : null;
  } catch {
    return null;
  }
}
