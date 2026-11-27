"use client";

// A phone's top bar: the drawer (sidebar) on the left, where the lawyer is in the middle,
// a new chat on the right. Hidden from lg up, where the sidebar sits beside the page.
import { Menu, SquarePen } from "lucide-react";
import { Brand } from "@/components/Brand";
import { t } from "@/lib/i18n";

export function MobileBar({ title, onMenu, onNew }: {
  title: string; onMenu: () => void; onNew: () => void;
}) {
  return (
    <header className="z-20 flex h-14 shrink-0 items-center gap-1 border-b border-rule bg-paper/95 px-2 py-1.5 backdrop-blur lg:hidden">
      <button onClick={onMenu} aria-label={t("openMenu")}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-ink hover:bg-sheet">
        <Menu size={20} />
      </button>
      <Brand compact />
      <p className="min-w-0 flex-1 truncate text-center text-sm font-medium text-ink">{title}</p>
      <button onClick={onNew} aria-label={t("newChat")}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-ink hover:bg-sheet">
        <SquarePen size={19} />
      </button>
    </header>
  );
}
