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
export type ChatSummary = {
  id: string; title: string; updated_at: string; cost_usd?: number; matter_id?: string | null;
};
export type Deadline = {
  id: string; matter_id: string; label: string; due: string; done: boolean; message_id: string | null;
  branch: Branch | null;
};
export type Matter = {
  id: string; client: string; subject: string; opponent: string; court: string; case_no: string;
  notes: string; closed: boolean; updated_at: string; next_deadline: Deadline | null;
};
export type MatterFields = Pick<Matter, "client" | "subject" | "opponent" | "court" | "case_no">;
export type MatterDetail = Matter & {
  chats: Array<{ id: string; title: string; updated_at: string }>;
  documents: StoredFile[];
  drafts: Array<{ id: string; chat_id: string | null; title: string; petition_type: string; updated_at: string }>;
  deadlines: Deadline[];
};
export type CalendarItem = Deadline & { client: string; subject: string };
export type Service = "electronic" | "hearing" | "physical";
export type Branch = "civil" | "criminal" | "enforcement" | "administrative" | "arbitration";
export type PeriodUnit = "day" | "week" | "month" | "year";
export type NoticeStep = { code: string; values: Record<string, string> };
export type NoticeResult = {
  received: string; served: string; due: string; law: string;
  steps: NoticeStep[]; warnings: NoticeStep[]; notes: string[];
};
export type CalendarYear = {
  year: number; covered: boolean; recess_start: string; recess_end: string;
  holidays: Array<{ day: string; name: string; half: boolean }>;
};
export type ComputedDeadline = { label: string; due: string; without_recess: string | null };
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
  detail_cost_usd?: number;
  timings?: { total_s?: number };
  answer?: { clarify?: Array<{ question: string; options: string[] }>; asked?: boolean };
  attachments?: Attachment[];
  trace?: { deadlines_computed?: ComputedDeadline[] };
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
export type TodayStats = {
  answers: number; average_s: number; longest_s: number; cost_usd: number; budget_usd: number;
};
export type StoredFile = {
  id: string; name: string; media_type: string; size: number; origin: "upload" | "generated";
  format: string; kind: string; area: string; readable: boolean; chat_id: string | null; chat_title: string | null;
  draft_id: string | null; folder_id: string | null; matter_id: string | null; created_at: string;
};
export type Folder = { id: string; name: string; parent_id: string | null; created_at: string };
export type FilePatch = {
  name?: string; folder_id?: string; to_top?: boolean; matter_id?: string; no_matter?: boolean;
};
export type FilePreview = { kind: "pdf" | "image" | "document" | "none"; doc?: EditorDoc };
export type Attachment = { id: string; name: string; media_type: string; size: number };
export type FileUsage = { used_bytes: number; quota_bytes: number };
export type HistoryHit = { chat_id: string; title: string; snippet: string };
export type MatterHit = { matter_id: string; client: string; subject: string; closed: boolean; snippet: string };
export type DocumentHit = { file_id: string; name: string; matter_id: string; client: string; snippet: string };
export type DeskHits = { chats: HistoryHit[]; matters: MatterHit[]; documents: DocumentHit[] };

export class ApiError extends Error {
  constructor(public status: number, public detail?: unknown) {
    super(`API ${status}`);
  }
}

async function failure(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {}
  return new ApiError(res.status, detail);
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
const put = (body: unknown) => ({ method: "PUT", body: JSON.stringify(body) });

export type PetitionType = { id: string; name: string };
export type StyleSample = {
  id: string; title: string; petition_type: string | null; area: string; matter: string;
  format: string;
  words: number; created_at: string;
};
export type TypeStyle = {
  name: string; words: number; words_per_sentence: number;
  register: "plain" | "balanced" | "formal"; headings: string[]; closing: string;
  learnt_from: number;
};
export type StyleLength = "short" | "medium" | "long";
export type StyleRegister = "plain" | "balanced" | "formal";
export type StyleProfile = {
  types: Record<string, TypeStyle>; rules: string[];
  preferences: { length_factor: number; register_shift: number;
    length: StyleLength | null; register: StyleRegister | null };
  overall: { pages: number; register: StyleRegister; closing: string | null };
  samples: number;
};
/** The petition as the editor holds it (ProseMirror JSON). */
export type EditorDoc = { type: "doc"; content?: unknown[] };
export type Draft = {
  id: string; format: DraftFormat; file_name: string;
  chat_id: string | null; message_id: string | null; petition_type: string;
  title: string; text: string; doc: EditorDoc;
  updated_at: string;
};
export type DraftAction = "shorter" | "longer" | "plainer" | "formal";
export type DraftFormat = "docx" | "pdf" | "udf";

async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: form, credentials: "include" });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

export const api = {
  me: () => call<User>("/auth/me"),
  uploadFile: (file: File, folderId?: string | null) => {
    const form = new FormData();
    form.append("file", file);
    if (folderId) form.append("folder_id", folderId);
    return upload<StoredFile>("/files", form);
  },
  files: () => call<StoredFile[]>("/files"),
  fileUsage: () => call<FileUsage>("/files/usage"),
  deleteFile: (id: string) => call<void>(`/files/${id}`, { method: "DELETE" }),
  renameFile: (id: string, name: string) => api.editFileInfo(id, { name }),
  /** Rename, move (folder_id, or to_top), or give to a case (matter_id, or no_matter). */
  editFileInfo: (id: string, patch: FilePatch) =>
    call<StoredFile>(`/files/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  copyFile: (id: string, folderId: string | null) =>
    call<StoredFile>(`/files/${id}/copy`, json({ folder_id: folderId })),
  filePreview: (id: string) => call<FilePreview>(`/files/${id}/preview`),
  folders: () => call<Folder[]>("/folders"),
  createFolder: (name: string, parentId: string | null) =>
    call<Folder>("/folders", json({ name, parent_id: parentId })),
  editFolder: (id: string, patch: { name?: string; parent_id?: string; to_top?: boolean }) =>
    call<Folder>(`/folders/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteFolder: (id: string) => call<void>(`/folders/${id}`, { method: "DELETE" }),
  /** The file in the editor: a petition's draft, or an editable copy of an added document. */
  editFile: (id: string) => call<Draft>(`/drafts/from-file/${id}`, { method: "POST" }),
  fileUrl: (id: string) => `${API_URL}/files/${id}`,
  petitionTypes: () => call<PetitionType[]>("/drafting/types"),
  samples: () => call<StyleSample[]>("/drafting/samples"),
  uploadSample: (file: File, choice?: { replace?: string; keep?: boolean }) => {
    const form = new FormData();
    form.append("file", file);
    if (choice?.replace) form.append("replace", choice.replace);
    if (choice?.keep) form.append("keep", "true");
    return upload<StyleSample>("/drafting/samples", form);
  },
  setSampleType: (id: string, petitionType: string | null) =>
    call<StyleSample>(`/drafting/samples/${id}`, put({ petition_type: petitionType })),
  deleteSample: (id: string) => call<void>(`/drafting/samples/${id}`, { method: "DELETE" }),
  styleProfile: () => call<StyleProfile>("/drafting/profile"),
  chooseStyle: (length: StyleLength | null, register: StyleRegister | null) =>
    call<StyleProfile>("/drafting/profile/style", put({ length, register })),
  memories: () => call<Array<{ id: string; text: string; seen: number; used: boolean }>>("/drafting/memories"),
  deleteMemory: (id: string) => call<void>(`/drafting/memories/${id}`, { method: "DELETE" }),
  resetStyle: () => call<StyleProfile>("/drafting/profile/reset", { method: "POST" }),
  saveRules: (rules: string[]) => call<{ rules: string[] }>("/drafting/profile/rules", put({ rules })),
  drafts: (chatId: string) => call<Draft[]>(`/drafts?chat_id=${chatId}`),
  saveDraft: (id: string, text: string) => call<Draft>(`/drafts/${id}`, put({ text })),
  /** An autosave: kept, the style is learnt once at the end (learnDraft). */
  saveDraftDoc: (id: string, doc: EditorDoc, keepalive = false) =>
    call<Draft>(`/drafts/${id}`, { ...put({ doc, learn: false }), keepalive }),
  /** Editing finished: learn the lawyer's style from the whole session's changes. */
  learnDraft: (id: string) =>
    call<void>(`/drafts/${id}/learn`, { method: "POST", keepalive: true }),
  adjustDraft: (id: string, action: DraftAction, selection?: string) =>
    call<Draft>(`/drafts/${id}/adjust`, json({ action, selection: selection || null })),
  draftFileUrl: (id: string, format?: DraftFormat) =>
    `${API_URL}/drafts/${id}/file${format ? `?format=${format}` : ""}`,
  login: (email: string, password: string) => call<User>("/auth/login", json({ email, password })),
  register: (name: string, email: string, password: string, invite_code: string) =>
    call<User>("/auth/register", json({ name, email, password, invite_code })),
  logout: () => call<void>("/auth/logout", { method: "POST" }),
  chats: () => call<ChatSummary[]>("/chats"),
  createChat: (content: string, matterId?: string | null) =>
    call<ChatSummary>("/chats", json({ content, matter_id: matterId ?? null })),
  moveChat: (chatId: string, matterId: string | null) =>
    call<{ id: string; matter_id: string | null }>(`/chats/${chatId}/matter`, put({ matter_id: matterId })),
  matters: () => call<Matter[]>("/matters"),
  matter: (id: string) => call<MatterDetail>(`/matters/${id}`),
  createMatter: (fields: MatterFields) => call<Matter>("/matters", json(fields)),
  editMatter: (id: string, fields: Partial<Matter>) =>
    call<Matter>(`/matters/${id}`, { method: "PATCH", body: JSON.stringify(fields) }),
  deleteMatter: (id: string) => call<void>(`/matters/${id}`, { method: "DELETE" }),
  addMatterFile: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<StoredFile>(`/matters/${id}/files`, form);
  },
  addDeadline: (matterId: string, label: string, due: string, messageId?: string, branch?: Branch) =>
    call<Deadline>(`/matters/${matterId}/deadlines`, json({ label, due, branch: branch ?? null, message_id: messageId ?? null })),
  editDeadline: (id: string, fields: Partial<Pick<Deadline, "label" | "due" | "done">>) =>
    call<Deadline>(`/deadlines/${id}`, { method: "PATCH", body: JSON.stringify(fields) }),
  deleteDeadline: (id: string) => call<void>(`/deadlines/${id}`, { method: "DELETE" }),
  calendar: () => call<CalendarItem[]>("/deadlines"),
  calculateDeadline: (body: { received: string; service: Service; amount: number; unit: PeriodUnit; branch: Branch }) =>
    call<NoticeResult>("/deadlines/calculate", json(body)),
  holidays: (year: number) => call<CalendarYear>(`/holidays/${year}`),
  deadlinePresets: () => call<DeadlinePreset[]>("/deadlines/presets"),
  renameChat: (id: string, title: string) =>
    call<ChatSummary>(`/chats/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteChat: (id: string) => call<void>(`/chats/${id}`, { method: "DELETE" }),
  messages: (id: string) => call<Message[]>(`/chats/${id}/messages`),
  cancelRun: (id: string) => call<void>(`/chats/${id}/run/cancel`, { method: "POST" }),
  todayStats: () => call<TodayStats>("/chats/stats/today"),
  searchHistory: (q: string) => call<HistoryHit[]>(`/chats/search?q=${encodeURIComponent(q)}`),
  searchMatters: (q: string) =>
    call<Omit<DeskHits, "chats">>(`/matters/search?q=${encodeURIComponent(q)}`),
  /** Chats, case files and their documents at once. */
  searchDesk: async (q: string): Promise<DeskHits> => {
    const [chats, files] = await Promise.all([api.searchHistory(q), api.searchMatters(q)]);
    return { chats, ...files };
  },
  source: (chatId: string, messageId: string, key: string) =>
    call<SourceText>(`/chats/${chatId}/messages/${messageId}/evidence/${key}`),
  llmSettings: () => call<LLMSettings>("/settings/llm"),
  saveLLMSettings: (body: Omit<LLMSettings, "provider" | "is_saved" | "api_key_configured"> &
    { api_key?: string; clear_api_key: boolean }) =>
    call<LLMSettings>("/settings/llm", { method: "PUT", body: JSON.stringify(body) }),
  llmModels: () => call<LLMModel[]>("/settings/llm/models"),
  testLLM: () => call<{ ok: boolean; model: string }>("/settings/llm/test", { method: "POST" }),
};

/** A ready period by kind of work, with the article that sets it. */
export type DeadlinePreset = { label: string; amount: number; unit: PeriodUnit; branch: Branch; citation: string };

export async function fetchHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return res.ok ? ((await res.json()) as Health) : null;
  } catch {
    return null;
  }
}
