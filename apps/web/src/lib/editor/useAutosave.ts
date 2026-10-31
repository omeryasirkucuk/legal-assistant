// Saving a draft as the lawyer types, the way online word processors do: a pause in typing
// saves, saves never overlap, a failed save is tried again, and whatever is pending is
// saved when the editor closes or the tab goes away. The style is learnt once, at the end
// of the session, from all its changes (the server reads the change with a model).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Draft, type EditorDoc } from "@/lib/api";

const PAUSE_MS = 1000;
const RETRY_MS = 4000;

export type SaveState = "idle" | "saving" | "saved" | "error";

export function useAutosave(draftId: string, onSaved: (d: Draft) => void) {
  const [state, setState] = useState<SaveState>("idle");
  const pending = useRef<EditorDoc | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflight = useRef<Promise<boolean>>(Promise.resolve(true));
  const changed = useRef(false);                 // anything saved in this session
  const saved = useRef(onSaved);
  saved.current = onSaved;

  const flush = useCallback((keepalive = false): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    inflight.current = inflight.current.then(async () => {
      const doc = pending.current;
      if (!doc) return true;
      pending.current = null;
      setState("saving");
      try {
        const d = await api.saveDraftDoc(draftId, doc, keepalive);
        changed.current = true;
        saved.current(d);
        setState(pending.current ? "saving" : "saved");
        return true;
      } catch {
        pending.current = pending.current ?? doc;
        setState("error");
        timer.current = setTimeout(() => { flush(); }, RETRY_MS);
        return false;
      }
    });
    return inflight.current;
  }, [draftId]);

  const edited = useCallback((doc: EditorDoc) => {
    pending.current = doc;
    setState("saving");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { flush(); }, PAUSE_MS);
  }, [flush]);

  // Closing the editor or leaving the page: save what is pending, then learn once.
  useEffect(() => {
    const finish = () => {
      flush(true).then(() => {
        if (changed.current) {
          changed.current = false;
          api.learnDraft(draftId).catch(() => {});
        }
      });
    };
    window.addEventListener("pagehide", finish);
    return () => {
      window.removeEventListener("pagehide", finish);
      finish();
    };
  }, [draftId, flush]);

  return { state, edited, flush };
}
