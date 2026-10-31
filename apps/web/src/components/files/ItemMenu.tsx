"use client";

// The "⋯" menu of a file or folder: a short list of actions in a small popover.
import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { t } from "@/lib/i18n";

// `phoneOnly`: an action the row shows as its own button where there is room (sm and up).
export type MenuItem = { label: string; onSelect: () => void; danger?: boolean; phoneOnly?: boolean };

/** `className` places the menu (it must set a position, e.g. "absolute right-1 top-1"). */
export function ItemMenu({ items, className = "" }: { items: MenuItem[]; className?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div ref={box} className={className || "relative"}>
      <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }} aria-label={t("moreActions")} aria-expanded={open}
        className="rounded-md p-1.5 text-muted hover:bg-sheet hover:text-ink pointer-coarse:p-2.5">
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-30 mt-1 w-48 rounded-xl border border-rule bg-sheet p-1 shadow-lg">
          {items.map((it) => (
            <button key={it.label} role="menuitem" onClick={(e) => { e.stopPropagation(); setOpen(false); it.onSelect(); }}
              className={`block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-paper pointer-coarse:py-2.5 ${it.danger ? "text-danger" : "text-ink"} ${it.phoneOnly ? "sm:hidden" : ""}`}>
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
