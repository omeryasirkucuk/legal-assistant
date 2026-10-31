"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AssistantAnswer } from "@/components/AssistantAnswer";
import { StreamingAnswer } from "@/components/StreamingAnswer";
import { Composer } from "@/components/Composer";
import { Sidebar } from "@/components/Sidebar";
import { SourceDrawer } from "@/components/SourceDrawer";
import { DraftFile } from "@/components/DraftFile";
import { DraftPanel } from "@/components/DraftPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { StylePanel } from "@/components/StylePanel";
import { FilesView } from "@/components/FilesView";
import { UsageMeter } from "@/components/UsageMeter";
import { CalendarView } from "@/components/CalendarView";
import { MatterSuggest } from "@/components/MatterSuggest";
import { ChatMatterBar } from "@/components/ChatMatterBar";
import { DeadlineSuggest } from "@/components/DeadlineSuggest";
import { MatterForm } from "@/components/MatterForm";
import { MatterView } from "@/components/MatterView";
import type { AskOptions } from "@/lib/stream";
import {
  api,
  ApiError,
  type ChatSummary,
  type Evidence,
  type Message,
  type SourceText,
  type TodayStats,
  type User,
  type Draft,
  type Attachment,
  type Deadline,
  type Matter,
  type MatterFields,
} from "@/lib/api";
import { FileText } from "lucide-react";
import { formatUsd } from "@/lib/format";
import { t } from "@/lib/i18n";
import { mentionedMatters } from "@/lib/matterMatch";
import { citationOrder } from "@/lib/markers";
import { useChatRuns } from "@/lib/useChatRuns";

type Drawer = { evidence: Evidence; number: number; messageId: string | null };
// What the main area shows: a chat (or a new one), a case file, or the calendar.
type View = "chat" | "matter" | "calendar" | "files";

export default function ChatApp() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [drawer, setDrawer] = useState<Drawer | null>(null);
  const [source, setSource] = useState<SourceText | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [styleOpen, setStyleOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [matters, setMatters] = useState<Matter[]>([]);
  const [view, setView] = useState<View>("chat");
  const [matterId, setMatterId] = useState<string | null>(null);   // the file being worked in
  const [matterDeadlines, setMatterDeadlines] = useState<Deadline[]>([]);
  const [newMatterOpen, setNewMatterOpen] = useState(false);
  const [matterVersion, setMatterVersion] = useState(0);         // reloads the file page
  const [held, setHeld] = useState<{ question: string; options: AskOptions; candidates: Matter[] } | null>(null);
  const declined = useRef(new Set<string>());                    // chats asked "without the file"

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem("sidebar") === "collapsed");
    } catch {}
  }, []);

  function toggleSidebar() {
    setCollapsed((c) => {
      try {
        localStorage.setItem("sidebar", c ? "open" : "collapsed");
      } catch {}
      return !c;
    });
  }
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [openDraft, setOpenDraft] = useState<Draft | null>(null);
  const [draftPage, setDraftPage] = useState(false);   // the draft fills the page instead of the side
  const [today, setToday] = useState<TodayStats | null>(null);
  const visibleChat = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const runs = useChatRuns({
    onTitle: useCallback((id: string, title: string) =>
      setChats((cs) => cs.map((c) => (c.id === id ? { ...c, title } : c))), []),
    onFinished: useCallback((id: string) => {
      if (visibleChat.current === id) {
        api.messages(id).then(setMessages).catch(() => {});
        api.drafts(id).then(setDrafts).catch(() => {});
      }
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
        api.matters().then(setMatters).catch(() => {});
        return api.chats().then(setChats);
      })
      .catch((e) => e instanceof ApiError && e.status === 401 && router.replace("/login"));
  }, [router]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, pending?.question, pending?.lines, pending?.plan]);

  const { attach } = runs;
  const refreshMatters = useCallback(() => {
    api.matters().then(setMatters).catch(() => {});
    setMatterVersion((v) => v + 1);
  }, []);

  // The deadlines of the file the open chat belongs to, to tell which suggestions are added.
  useEffect(() => {
    if (!matterId) return setMatterDeadlines([]);
    api.matter(matterId).then((m) => setMatterDeadlines(m.deadlines)).catch(() => {});
  }, [matterId, matterVersion]);

  function openMatter(id: string) {
    setView("matter");
    setMatterId(id);
    setChatId(null);
    visibleChat.current = null;
    setMessages([]);
    setDrafts([]);
    setOpenDraft(null);
    setDraftPage(false);
  }

  function openFiles() {
    setView("files");
    setChatId(null);
    visibleChat.current = null;
    setMessages([]);
    setOpenDraft(null);
    setDraftPage(false);
  }

  function editDraftPage(d: Draft) {
    setOpenDraft(d);
    setDraftPage(true);
  }

  function closeDraftPage() {
    setDraftPage(false);
    // Opened from My files: back to it; opened beside a chat: back beside it.
    if (view === "files") setOpenDraft(null);
  }

  function openCalendar() {
    setView("calendar");
    setChatId(null);
    visibleChat.current = null;
    setMessages([]);
  }

  async function createMatter(fields: MatterFields) {
    const m = await api.createMatter(fields);
    setNewMatterOpen(false);
    setMatters((all) => [m, ...all]);
    openMatter(m.id);
  }

  async function moveChat(id: string, toMatter: string) {
    await api.moveChat(id, toMatter);
    setChats((cs) => cs.map((c) => (c.id === id ? { ...c, matter_id: toMatter } : c)));
    setMatterId(toMatter);
    refreshMatters();
  }

  const openChat = useCallback(async (id: string) => {
    setView("chat");
    setChatId(id);
    visibleChat.current = id;
    setMessages([]);
    setDrafts([]);
    setOpenDraft(null);
    setDraftPage(false);
    const [loaded, chatDrafts] = await Promise.all([api.messages(id), api.drafts(id)]);
    if (visibleChat.current === id) {
      setMessages(loaded);
      setDrafts(chatDrafts);
    }
    attach(id);
  }, [attach]);

  // A held question belongs to the chat it was typed in.
  useEffect(() => { setHeld(null); }, [chatId, view]);

  // A chat opened from anywhere works in its file, if it has one.
  useEffect(() => {
    if (view !== "chat" || !chatId) return;
    const c = chats.find((x) => x.id === chatId);
    if (c) setMatterId(c.matter_id ?? null);
  }, [view, chatId, chats]);

  function newChat() {
    setView("chat");
    setMatterId(null);
    setChatId(null);
    setDrafts([]);
    setOpenDraft(null);
    setDraftPage(false);
    visibleChat.current = null;
    setMessages([]);
  }

  async function deleteChat(id: string) {
    runs.stop(id);
    await api.deleteChat(id);
    setChats((cs) => cs.filter((c) => c.id !== id));
    if (id === chatId) newChat();
  }

  async function ask(question: string, options: AskOptions = {}) {
    // A message outside any file that names one: ask first whether to use it.
    const named = !matterId && !declined.current.has(chatId ?? "") ? mentionedMatters(question, matters) : [];
    if (named.length) {
      setHeld({ question, options, candidates: named });
      return;
    }
    await send(question, options, matterId);
  }

  async function answerHeld(m: Matter | null) {
    if (!held) return;
    const { question, options } = held;
    setHeld(null);
    if (m && chatId) await moveChat(chatId, m.id);
    if (m && !chatId) setMatterId(m.id);
    const id = await send(question, options, m ? m.id : null);
    if (!m) declined.current.add(id);
  }

  async function send(question: string, options: AskOptions, inMatter: string | null): Promise<string> {
    let id = chatId;
    if (!id) {
      // Asked from a file's page (or a chat in a file): the new chat belongs to that file.
      const chat = await api.createChat(question, inMatter);
      id = chat.id;
      setView("chat");
      setChatId(id);
      visibleChat.current = id;
      setChats((cs) => [chat, ...cs]);
      if (inMatter) refreshMatters();
    }
    await runs.ask(id, question, options);
    return id;
  }

  function changeDraft(d: Draft) {
    setOpenDraft(d);
    setDrafts((all) => all.map((x) => (x.id === d.id ? d : x)));
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

  const empty = view === "chat" && !messages.length && !pending;
  const currentMatter = matters.find((m) => m.id === matterId) ?? null;
  const lastAnswer = [...messages].reverse().find((m) => m.role === "assistant");
  const draftOf = (messageId: string) => drafts.find((d) => d.message_id === messageId);
  // A saved question with nothing under it: its answer failed or the server restarted.
  const last = messages[messages.length - 1];
  const unanswered = !pending && last?.role === "user" ? last.content : null;
  const chatCost = messages.reduce(
    (sum, m) => sum + (m.meta.cost_usd ?? 0) + (m.meta.detail_cost_usd ?? 0), 0);

  return (
    <div className="flex h-full">
      <Sidebar
        user={user}
        chats={chats}
        matters={matters}
        activeId={chatId}
        activeMatterId={view === "matter" ? matterId : null}
        calendarOpen={view === "calendar"}
        onOpenMatter={openMatter}
        onNewMatter={() => setNewMatterOpen(true)}
        onCalendar={openCalendar}
        onSelect={openChat}
        onNew={newChat}
        onDelete={deleteChat}
        onLogout={() => api.logout().then(() => router.replace("/login"))}
        onSettings={() => setSettingsOpen(true)}
        onStyle={() => setStyleOpen(true)}
        onFiles={openFiles}
        filesOpen={view === "files"}
        collapsed={collapsed}
        onToggle={toggleSidebar}
        today={today}
      />

      {/* One scrolling area holds the text and, pinned to its bottom, the composer: both use
          the same column whatever the scrollbar does, and the composer's menus are not cut. */}
      {openDraft && draftPage ? (
        <main className="flex min-w-0 flex-1 flex-col">
          <DraftPanel key={`page-${openDraft.id}`} draft={openDraft} page onClose={closeDraftPage} onChange={changeDraft} />
        </main>
      ) : (
      <main className="@container flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="flex-1">
          <div className="mx-auto w-full max-w-[64rem] px-6 pb-16 pt-10 @4xl:px-12">
            {view === "matter" && matterId && (
              <MatterView key={`${matterId}-${matterVersion}`} matterId={matterId} onOpenChat={openChat}
                onOpenDraft={openChat} onChanged={refreshMatters}
                onDeleted={() => { refreshMatters(); newChat(); }} />
            )}
            {view === "calendar" && <CalendarView onOpenMatter={openMatter} />}
            {view === "files" && <FilesView onOpenChat={openChat} onEdit={editDraftPage} matters={matters} />}
            {view === "chat" && chatId && (
              <ChatMatterBar matter={currentMatter} matters={matters} onOpenMatter={openMatter}
                onMove={(m) => moveChat(chatId, m)} />
            )}
            {empty && (
              <div className="mt-[18vh] max-w-[38rem]">
                <h1 className="font-serif text-3xl text-ink">{t("emptyTitle")}</h1>
                <p className="mt-3 text-[15px] leading-relaxed text-muted">{t("emptyBody")}</p>
              </div>
            )}

            <div className="space-y-12">
                {messages.map((m) =>
                  m.role === "user" ? (
                    <Question key={m.id} text={m.content} attachments={m.meta.attachments} />
                  ) : (
                    <AssistantAnswer
                      key={m.id}
                      raw={m.content}
                      evidence={m.evidence}
                      checked={m.meta.checked}
                      repaired={m.meta.repaired}
                      refused={m.meta.refused}
                      seconds={m.meta.timings?.total_s}
                      cost={m.meta.cost_usd !== undefined
                        ? m.meta.cost_usd + (m.meta.detail_cost_usd ?? 0) : undefined}
                      asked={m.meta.answer?.asked}
                      onOpenSource={(k) => openSource(m.evidence, m.content, m.id, k)}
                      draftAction={(draftOf(m.id) || (matterId && m.meta.trace?.deadlines_computed?.length)) && (
                        <>
                          {draftOf(m.id) && (
                            <DraftFile draft={draftOf(m.id)!} onEdit={() => setOpenDraft(draftOf(m.id) ?? null)} />
                          )}
                          {matterId && m.meta.trace?.deadlines_computed?.length ? (
                            <DeadlineSuggest matterId={matterId} messageId={m.id}
                              computed={m.meta.trace.deadlines_computed} existing={matterDeadlines}
                              onAdded={refreshMatters} />
                          ) : null}
                        </>
                      )}
                    />
                  ),
                )}
                {pending && (
                  <>
                    {/* A re-attached answer's question is already among the saved messages. */}
                    {messages[messages.length - 1]?.role !== "user" && <Question text={pending.question} />}
                    {pending.error ? (
                      <Unanswered
                        text={pending.budget ? t("budgetReached") : t("streamError")}
                        onRetry={pending.budget ? undefined : () => ask(pending.question)}
                      />
                    ) : (
                      <StreamingAnswer pending={pending} onOpenSource={(k) => openPendingSource(k)} />
                    )}
                  </>
                )}
                {unanswered && (
                  <Unanswered text={t("unanswered")} onRetry={() => ask(unanswered)} />
                )}
            </div>
            {chatCost > 0 && !pending && (
              <p className="mt-10 max-w-[42rem] border-t border-rule pt-3 text-xs text-faint">
                {t("chatCost", { cost: formatUsd(chatCost) })}
              </p>
            )}
            <div ref={bottom} className="scroll-mb-48" />
          </div>
        </div>

        {/* Shares the message column's width and left edge; a fade marks where the scrolling
            text passes under it. */}
        {view !== "calendar" && view !== "files" && (
        <div className="sticky bottom-0 z-10">
        <div className="mx-auto grid w-full max-w-[64rem] gap-x-10 bg-paper px-6 pb-4 @4xl:grid-cols-[minmax(0,42rem)_15rem] @4xl:px-12">
          <div className="relative">
            <div className="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-paper to-transparent" />
            {held && (
              <MatterSuggest question={held.question} candidates={held.candidates} onWith={(m) => answerHeld(m)} onWithout={() => answerHeld(null)} />
            )}
            <Composer
              followUp={lastAnswer && !pending ? {
                key: lastAnswer.id, items: lastAnswer.meta.answer?.clarify ?? [],
                asked: !!lastAnswer.meta.answer?.asked,
              } : undefined}
              busy={!!pending && !pending.error}
              onSubmit={(text, fileIds, power) => ask(text, { fileIds, power })}
              placeholder={view === "matter" && currentMatter ? t("askInMatter", { client: currentMatter.client }) : undefined}
              footer={<UsageMeter today={today} onOpenFiles={openFiles} />}
              onStop={() => chatId && runs.stop(chatId)}
            />
          </div>
        </div>
        </div>
        )}
      </main>
      )}

      <SourceDrawer
        evidence={drawer?.evidence ?? null}
        number={drawer?.number ?? 0}
        source={source}
        onClose={() => setDrawer(null)}
      />
      {openDraft && !draftPage && (
        <DraftPanel key={openDraft.id} draft={openDraft} onClose={() => setOpenDraft(null)}
          onExpand={() => setDraftPage(true)} onChange={changeDraft} />
      )}
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
      {styleOpen && <StylePanel onClose={() => setStyleOpen(false)} />}
      {newMatterOpen && <MatterForm onSave={createMatter} onClose={() => setNewMatterOpen(false)} />}
    </div>
  );
}

function Question({ text, attachments }: { text: string; attachments?: Attachment[] }) {
  return (
    <div className="max-w-[42rem] border-l-2 border-ink pl-4">
      {attachments && attachments.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2">
          {attachments.map((a) => (
            <li key={a.id}>
              <a href={api.fileUrl(a.id)} title={a.name}
                className="flex max-w-[16rem] items-center gap-2 rounded-lg border border-rule bg-sheet px-2 py-1 text-sm text-ink hover:border-faint">
                <FileText size={14} className="shrink-0 text-cite" />
                <span className="truncate">{a.name}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="whitespace-pre-wrap text-[15px] font-medium leading-relaxed text-ink">{text}</p>
    </div>
  );
}

function Unanswered({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-3 text-sm text-danger">
      <p>{text}</p>
      {onRetry && (
        <button onClick={onRetry} className="rounded border border-rule px-2 py-1 text-ink hover:bg-paper">
          {t("askAgain")}
        </button>
      )}
    </div>
  );
}
