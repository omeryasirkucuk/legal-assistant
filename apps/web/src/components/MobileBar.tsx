"use client";

// A phone's top bar: the drawer (sidebar) on the left, where the lawyer is in the middle,
// a new chat on the right. Hidden from md up, where the sidebar sits beside the page.
import { Menu, SquarePen } from "lucide-react";
import { t } from "@/lib/i18n";

export function MobileBar({ title, onMenu, onNew }: {
  title: string; onMenu: () => void; onNew: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex items-center gap-1 border-b border-rule bg-paper/95 px-2 py-1.5 backdrop-blur md:hidden">
      <button onClick={onMenu} aria-label={t("openMenu")}
        className="flex h-10 w-10 items-center justify-center rounded-lg text-ink hover:bg-sheet">
        <Menu size={20} />
      </button>
      <p className="min-w-0 flex-1 truncate text-center text-sm font-medium text-ink">{title}</p>
      <button onClick={onNew} aria-label={t("newChat")}
        className="flex h-10 w-10 items-center justify-center rounded-lg text-ink hover:bg-sheet">
        <SquarePen size={19} />
      </button>
    </header>
  );
}
