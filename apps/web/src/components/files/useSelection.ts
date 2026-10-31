// Selecting files and folders in My files: tick boxes, Cmd/Ctrl-click to add or remove,
// Shift-click for a range of what is shown, Cmd/Ctrl+A for all of it, Esc to clear. A
// selected item drags the whole selection.
import { useEffect, useState } from "react";
import type { Item } from "@/components/files/FileItems";

const key = (i: Item) => `${i.kind}:${i.id}`;

export function useSelection(visible: Item[], resetOn: unknown[]) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<string | null>(null);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setSelected(new Set()); setAnchor(null); }, resetOn);

  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "Escape") setSelected(new Set());
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a" && visible.length) {
        e.preventDefault();
        setSelected(new Set(visible.map(key)));
      }
    };
    document.addEventListener("keydown", keys);
    return () => document.removeEventListener("keydown", keys);
  });

  function toggle(it: Item, e: React.MouseEvent) {
    const k = key(it);
    const next = new Set(selected);
    if (e.shiftKey && anchor) {
      const keys = visible.map(key);
      const [a, b] = [keys.indexOf(anchor), keys.indexOf(k)].sort((x, y) => x - y);
      if (a >= 0) keys.slice(a, b + 1).forEach((x) => next.add(x));
      else next.add(k);
    } else if (next.has(k)) next.delete(k);
    else next.add(k);
    setSelected(next);
    setAnchor(k);
  }

  const items = (): Item[] => [...selected].map((k) => {
    const [kind, id] = k.split(":");
    return { kind: kind as Item["kind"], id };
  });

  return {
    count: selected.size,
    has: (it: Item) => selected.has(key(it)),
    toggle,
    items,
    files: () => items().filter((i) => i.kind === "file"),
    clear: () => setSelected(new Set()),
    dragItems: (it: Item) => () => (selected.has(key(it)) ? items() : [it]),
  };
}
