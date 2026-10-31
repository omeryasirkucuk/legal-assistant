"use client";

// Answers in progress, per chat. Switching chats only stops watching; the answer keeps running
// on the server and is picked up again (from its first event) when the chat is opened again.
import { useCallback, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { applyEvent, startPending, type Pending } from "./pending";
import { askStream, followRun, type AskOptions, type StreamEvent } from "./stream";

type Callbacks = {
  onTitle: (chatId: string, title: string) => void;
  onFinished: (chatId: string) => void;
};

export function useChatRuns({ onTitle, onFinished }: Callbacks) {
  const [pending, setPending] = useState<Record<string, Pending>>({});
  const watching = useRef<Record<string, AbortController>>({});

  const update = useCallback((chatId: string, fn: (p: Pending) => Pending | null) => {
    setPending((all) => {
      const current = all[chatId];
      if (!current) return all;
      const next = fn(current);
      const copy = { ...all };
      if (next) copy[chatId] = next;
      else delete copy[chatId];
      return copy;
    });
  }, []);

  const consume = useCallback((chatId: string) => (e: StreamEvent) => {
    if (e.type === "title") return onTitle(e.data.chat_id, e.data.title);
    if (e.type === "error") return update(chatId, (p) => ({ ...p, error: true, unavailable: !!e.data.unavailable }));
    if (e.type === "cancelled") return update(chatId, () => null);
    // A re-attached run starts with no local state; its first event creates it.
    setPending((all) => ({ ...all, [chatId]: applyEvent(all[chatId] ?? startPending(""), e) }));
  }, [onTitle, update]);

  const watch = useCallback(async (chatId: string,
    open: (signal: AbortSignal) => Promise<boolean>) => {
    watching.current[chatId]?.abort();
    const controller = new AbortController();
    watching.current[chatId] = controller;
    try {
      const ran = await open(controller.signal);
      if (controller.signal.aborted || !ran) return;
      setPending((all) => {
        if (all[chatId]?.error) return all;
        const copy = { ...all };
        delete copy[chatId];
        return copy;
      });
      onFinished(chatId);
    } catch (err) {
      if (controller.signal.aborted) return;
      const budget = err instanceof ApiError && err.status === 429;
      update(chatId, (p) => ({ ...p, error: true, budget }));
    } finally {
      if (watching.current[chatId] === controller) delete watching.current[chatId];
    }
  }, [onFinished, update]);

  const ask = useCallback((chatId: string, question: string, options: AskOptions = {}) => {
    setPending((all) => ({ ...all, [chatId]: startPending(question) }));
    return watch(chatId, (signal) =>
      askStream(chatId, question, consume(chatId), signal, options).then(() => true));
  }, [consume, watch]);

  // Picks up an answer still running on the server, if any.
  const attach = useCallback((chatId: string) => {
    if (watching.current[chatId]) return;
    return watch(chatId, (signal) => followRun(chatId, consume(chatId), signal));
  }, [consume, watch]);

  // Stops the answer on the server; the unanswered question is removed there, so the chat is
  // reloaded once the cancel has gone through.
  const stop = useCallback((chatId: string) => {
    watching.current[chatId]?.abort();
    update(chatId, () => null);
    api.cancelRun(chatId).catch(() => {}).finally(() => onFinished(chatId));
  }, [onFinished, update]);

  return { pending, ask, attach, stop };
}
