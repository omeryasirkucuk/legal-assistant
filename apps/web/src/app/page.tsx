"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AssistantAnswer } from "@/components/AssistantAnswer";
import { Composer, type Mode } from "@/components/Composer";
import { SearchResults } from "@/components/SearchResults";
import { Sidebar } from "@/components/Sidebar";
import { SourceDrawer } from "@/components/SourceDrawer";
import { SettingsPanel } from "@/components/SettingsPanel";
import {
  api,
  ApiError,
  type ChatSummary,
  type Checked,
  type DecisionHit,
  type Evidence,
  type Message,
  type SourceText,
  type User,
} from "@/lib/api";
import { t } from "@/lib/i18n";
import { citationOrder } from "@/lib/markers";
import { askStream } from "@/lib/stream";

type Pending = {
  question: string;
  raw: string;
  evidence: Evidence[];
  status?: string;
  checked?: Checked;
  repaired?: boolean;
  refused?: boolean;
  error?: boolean;
  budget?: boolean;
  plan?: Array<{ label: string; asks: string[] }>;
  atoms?: Record<string, { found: boolean; segments: Array<{ text: string; keys: string[] }> }>;
};

type Drawer = { evidence: Evidence; number: number; messageId: string | null };

export default function ChatApp() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [mode, setMode] = useState<Mode>("ask");
  const [search, setSearch] = useState<{ query: string; hits: DecisionHit[] | null } | null>(null);
  const [drawer, setDrawer] = useState<Drawer | null>(null);
  const [source, setSource] = useState<SourceText | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .me()
      .then((u) => {
        setUser(u);
        return api.chats().then(setChats);
      })
      .catch((e) => e instanceof ApiError && e.status === 401 && router.replace("/login"));
  }, [router]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, pending?.question, pending?.raw, search]);

  const openChat = useCallback(async (id: string) => {
    abort.current?.abort();
    setPending(null);
    setSearch(null);
    setChatId(id);
    setMessages(await api.messages(id));
  }, []);

  function newChat() {
    abort.current?.abort();
    setChatId(null);
    setMessages([]);
    setPending(null);
    setSearch(null);
  }

  async function deleteChat(id: string) {
    await api.deleteChat(id);
    setChats((cs) => cs.filter((c) => c.id !== id));
    if (id === chatId) newChat();
  }

  async function ask(question: string) {
    setSearch(null);
    let id = chatId;
    if (!id) {
      const chat = await api.createChat(question);
      id = chat.id;
      setChatId(id);
      setChats((cs) => [chat, ...cs]);
    }
    const controller = new AbortController();
    abort.current = controller;
    setPending({ question, raw: "", evidence: [] });
    const update = (fn: (p: Pending) => Pending) => setPending((p) => (p ? fn(p) : p));
    try {
      await askStream(
        id,
        question,
        (e) => {
          switch (e.type) {
            case "status":
              return update((p) => ({ ...p, status: e.data.message }));
            case "evidence":
              return update((p) => ({ ...p, evidence: [...p.evidence, e.data] }));
            case "plan":
              return update((p) => ({ ...p, plan: e.data.branches, atoms: {} }));
            case "atom":
              return update((p) => {
                const atoms = { ...(p.atoms ?? {}), [`${e.data.branch}:${e.data.index}`]: e.data };
                return { ...p, atoms, raw: renderProgress(p.plan ?? [], atoms) || p.raw };
              });
            case "delta":
              return update((p) => ({ ...p, raw: p.raw + e.data.text }));
            case "reset":
              return update((p) => ({ ...p, raw: "" }));
            case "checked":
              return update((p) => ({ ...p, checked: e.data }));
            case "final":
              return update((p) => ({
                ...p,
                raw: e.data.text,
                status: undefined,
              }));
            case "saved":
              return;
            case "error":
              throw new Error("answer failed");
          }
        },
        controller.signal,
      );
      setMessages(await api.messages(id));
      setPending(null);
      api.chats().then(setChats);
    } catch (err) {
      const budget = err instanceof ApiError && err.status === 429;
      if (!controller.signal.aborted) update((p) => ({ ...p, error: true, budget, status: undefined }));
      else setPending(null);
    }
  }

  async function runSearch(query: string) {
    setSearch({ query, hits: null });
    try {
      const hits = await api.searchDecisions(query);
      setSearch({ query, hits });
    } catch {
      setSearch({ query, hits: [] });
    }
  }

  function openSource(evidence: Evidence[], raw: string, messageId: string | null, key: string) {
    const ev = evidence.find((e) => e.key === key);
    if (!ev) return;
    setSource(null);
    setDrawer({ evidence: ev, number: citationOrder(raw).indexOf(key) + 1, messageId });
    if (messageId && chatId) api.source(chatId, messageId, key).then(setSource).catch(() => {});
  }

  if (!user) return null;

  const empty = !messages.length && !pending && !search;

  return (
    <div className="flex h-full">
      <Sidebar
        user={user}
        chats={chats}
        activeId={chatId}
        onSelect={openChat}
        onNew={newChat}
        onDelete={deleteChat}
        onLogout={() => api.logout().then(() => router.replace("/login"))}
        onSettings={() => setSettingsOpen(true)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[64rem] px-6 pb-10 pt-10 xl:px-12">
            {empty && (
              <div className="mt-[18vh] max-w-[38rem]">
                <h1 className="font-serif text-3xl text-ink">{t("emptyTitle")}</h1>
                <p className="mt-3 text-[15px] leading-relaxed text-muted">{t("emptyBody")}</p>
              </div>
            )}

            {search ? (
              <SearchResults query={search.query} hits={search.hits} />
            ) : (
              <div className="space-y-12">
                {messages.map((m) =>
                  m.role === "user" ? (
                    <Question key={m.id} text={m.content} />
                  ) : (
                    <AssistantAnswer
                      key={m.id}
                      raw={m.content}
                      evidence={m.evidence}
                      checked={m.meta.checked}
                      repaired={m.meta.repaired}
                      refused={m.meta.refused}
                      onOpenSource={(k) => openSource(m.evidence, m.content, m.id, k)}
                    />
                  ),
                )}
                {pending && (
                  <>
                    <Question text={pending.question} />
                    {pending.error ? (
                      <p className="text-sm text-danger">
                        {pending.budget ? t("budgetReached") : t("streamError")}
                      </p>
                    ) : (
                      <AssistantAnswer
                        raw={pending.raw}
                        evidence={pending.evidence}
                        checked={pending.checked}
                        streaming
                        status={pending.status}
                        onOpenSource={(k) => openSource(pending.evidence, pending.raw, null, k)}
                      />
                    )}
                  </>
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        <div className="mx-auto w-full max-w-[64rem] px-6 pb-5 xl:px-12">
          <div className="max-w-[42rem]">
            <Composer
              mode={mode}
              onModeChange={(m) => {
                setMode(m);
                if (m === "ask") setSearch(null);
              }}
              busy={!!pending && !pending.error}
              onSubmit={(text) => (mode === "ask" ? ask(text) : runSearch(text))}
              onStop={() => abort.current?.abort()}
            />
          </div>
        </div>
      </main>

      <SourceDrawer
        evidence={drawer?.evidence ?? null}
        number={drawer?.number ?? 0}
        source={source}
        onClose={() => setDrawer(null)}
      />
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}

function renderProgress(
  plan: Array<{ label: string; asks: string[] }>,
  atoms: Record<string, { found: boolean; segments: Array<{ text: string; keys: string[] }> }>,
): string {
  return plan.flatMap((branch, branchIndex) => {
    const answers = branch.asks.flatMap((_, atomIndex) => {
      const atom = atoms[`${branchIndex}:${atomIndex}`];
      if (!atom) return [];
      if (!atom.found) return ["kaynaklarda bulunamadı"];
      const text = atom.segments.map((segment) =>
        segment.text + segment.keys.map((key) => ` [[${key}]]`).join(""),
      ).join("").trim();
      return text ? [text] : [];
    });
    return answers.length ? [`- ${branch.label}: ${answers.join(" ")}`] : [];
  }).join("\n");
}

function Question({ text }: { text: string }) {
  return (
    <div className="max-w-[42rem] border-l-2 border-ink pl-4">
      <p className="whitespace-pre-wrap text-[15px] font-medium leading-relaxed text-ink">{text}</p>
    </div>
  );
}
