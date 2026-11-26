"use client";

// The "⋯" menu of a file or folder: a short list of actions in a small popover.
import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { t } from "@/lib/i18n";

// `phoneOnly`: an action the row shows as its own button where there is room (sm and up).
export type MenuItem = { label: string; onSelect: () => void; danger?: boolean; phoneOnly?: boolean };

/** `className` places the trigger relative to its file or folder. */
export function ItemMenu({ items, className = "" }: { items: MenuItem[]; className?: string }) {
  const [position, setPosition] = useState<{ left: number; width: number; maxHeight: number; top?: number; bottom?: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  function toggle(button: HTMLButtonElement) {
    if (position) {
      setPosition(null);
      return;
    }
    const gutter = 8;
    const viewportWidth = document.documentElement.clientWidth;
    const width = Math.min(192, viewportWidth - 2 * gutter);
    const rect = button.getBoundingClientRect();
    const height = window.visualViewport?.height ?? window.innerHeight;
    const offset = window.visualViewport?.offsetTop ?? 0;
    const roomBelow = height + offset - rect.bottom - 2 * gutter;
    const roomAbove = rect.top - offset - 2 * gutter;
    const left = Math.max(gutter, Math.min(rect.right - width, viewportWidth - width - gutter));
    setPosition(roomBelow >= 240 || roomBelow >= roomAbove
      ? { left, width, top: rect.bottom + gutter, maxHeight: Math.max(0, roomBelow) }
      : { left, width, bottom: window.innerHeight - rect.top + gutter, maxHeight: Math.max(0, roomAbove) });
  }

  useEffect(() => {
    if (!position) return;
    menu.current?.focus({ preventScroll: true });
    const close = () => setPosition(null);
    const away = (e: MouseEvent) => {
      if (!trigger.current?.contains(e.target as Node) && !menu.current?.contains(e.target as Node)) close();
    };
    const scroll = (e: Event) => { if (e.target !== menu.current) close(); };
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      close();
      trigger.current?.focus();
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", close);
    };
  }, [position]);

  return (
    <div className={className || "relative"}>
      <button ref={trigger} onClick={(e) => { e.stopPropagation(); toggle(e.currentTarget); }}
        aria-label={t("moreActions")} aria-expanded={!!position}
        className="rounded-md p-1.5 text-muted hover:bg-sheet hover:text-ink pointer-coarse:p-2.5">
        <MoreHorizontal size={16} />
      </button>
      {position && createPortal(
        <div ref={menu} role="menu" tabIndex={-1} style={position}
          className="fixed z-30 overflow-y-auto overscroll-y-contain rounded-xl border border-rule bg-sheet p-1 shadow-lg">
          {items.map((it) => (
            <button key={it.label} role="menuitem" onClick={(e) => { e.stopPropagation(); setPosition(null); trigger.current?.focus({ preventScroll: true }); it.onSelect(); }}
              className={`block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-paper pointer-coarse:py-2.5 ${it.danger ? "text-danger" : "text-ink"} ${it.phoneOnly ? "sm:hidden" : ""}`}>
              {it.label}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
