"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AssistantAnswer } from "@/components/AssistantAnswer";
import { StreamingAnswer } from "@/components/StreamingAnswer";
import { Composer, type Mode } from "@/components/Composer";
import { SearchResults } from "@/components/SearchResults";
import { Sidebar } from "@/components/Sidebar";
import { SourceDrawer } from "@/components/SourceDrawer";
import { SettingsPanel } from "@/components/SettingsPanel";
import {
  api,
  ApiError,
  type ChatSummary,
  type DecisionHit,
  type Evidence,
  type Message,
  type SourceText,
  type TodayStats,
  type User,
} from "@/lib/api";
import { t } from "@/lib/i18n";
import { citationOrder } from "@/lib/markers";
import { useChatRuns } from "@/lib/useChatRuns";

type Drawer = { evidence: Evidence; number: number; messageId: string | null };

export default function ChatApp() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setMode] = useState<Mode>("ask");
  const [search, setSearch] = useState<{ query: string; hits: DecisionHit[] | null } | null>(null);
  const [drawer, setDrawer] = useState<Drawer | null>(null);
  const [source, setSource] = useState<SourceText | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [today, setToday] = useState<TodayStats | null>(null);
  const visibleChat = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const runs = useChatRuns({
    onTitle: useCallback((id: string, title: string) =>
      setChats((cs) => cs.map((c) => (c.id === id ? { ...c, title } : c))), []),
    onFinished: useCallback((id: string) => {
      if (visibleChat.current === id) api.messages(id).then(setMessages).catch(() => {});
      api.chats().then(setChats).catch(() => {});
      api.todayStats().then(setToday).catch(() => {});
    }, []),
  });
  const pending = chatId ? runs.pending[chatId] ?? null : null;

  useEffect(() => {
    visibleChat.current = chatId;
  }, [chatId]);

  useEffect(() => {
    api
      .me()
      .then((u) => {
        setUser(u);
        api.todayStats().then(setToday).catch(() => {});
        return api.chats().then(setChats);
      })
      .catch((e) => e instanceof ApiError && e.status === 401 && router.replace("/login"));
  }, [router]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, pending?.question, pending?.lines, pending?.plan, search]);

  const { attach } = runs;
  const openChat = useCallback(async (id: string) => {
    setSearch(null);
    setChatId(id);
    visibleChat.current = id;
    setMessages([]);
    const loaded = await api.messages(id);
    if (visibleChat.current === id) setMessages(loaded);
    attach(id);
  }, [attach]);

  function newChat() {
    setChatId(null);
    visibleChat.current = null;
    setMessages([]);
    setSearch(null);
  }

  async function deleteChat(id: string) {
    runs.stop(id);
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
      visibleChat.current = id;
      setChats((cs) => [chat, ...cs]);
    }
    await runs.ask(id, question);
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

  function openPendingSource(key: string) {
    if (!pending) return;
    const ev = pending.evidence.find((e) => e.key === key);
    if (!ev) return;
    setSource(null);
    setDrawer({ evidence: ev, number: 0, messageId: null });
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
        today={today}
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
                      seconds={m.meta.timings?.total_s}
                      onOpenSource={(k) => openSource(m.evidence, m.content, m.id, k)}
                    />
                  ),
                )}
                {pending && (
                  <>
                    {/* A re-attached answer's question is already among the saved messages. */}
                    {messages[messages.length - 1]?.role !== "user" && <Question text={pending.question} />}
                    {pending.error ? (
                      <p className="text-sm text-danger">
                        {pending.budget ? t("budgetReached") : t("streamError")}
                      </p>
                    ) : (
                      <StreamingAnswer pending={pending} onOpenSource={(k) => openPendingSource(k)} />
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
              onStop={() => chatId && runs.stop(chatId)}
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

function Question({ text }: { text: string }) {
  return (
    <div className="max-w-[42rem] border-l-2 border-ink pl-4">
      <p className="whitespace-pre-wrap text-[15px] font-medium leading-relaxed text-ink">{text}</p>
    </div>
  );
}
