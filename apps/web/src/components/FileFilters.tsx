"use client";

// Narrowing My files by format, kind of document and area of law. Each list offers only
// what the lawyer's files contain, with how many files each choice would leave.
import { ChevronDown } from "lucide-react";
import type { StoredFile } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";

export type Facet = "format" | "kind" | "area";
export type Picks = Record<Facet, string>;
export const NO_PICKS: Picks = { format: "", kind: "", area: "" };

const FACETS: { facet: Facet; label: MessageKey }[] = [
  { facet: "format", label: "filterFormat" },
  { facet: "kind", label: "filterKind" },
  { facet: "area", label: "filterArea" },
];

export const valueName = (facet: Facet, value: string) => t(`${facet}_${value}` as MessageKey);

export function matches(file: StoredFile, picks: Picks, skip?: Facet): boolean {
  return FACETS.every(({ facet }) => facet === skip || !picks[facet] || file[facet] === picks[facet]);
}

export function FileFilters({ files, picks, onChange }: {
  files: StoredFile[]; picks: Picks; onChange: (picks: Picks) => void;
}) {
  return (
    <div className="mx-7 mt-4 grid grid-cols-3 gap-2">
      {FACETS.map(({ facet, label }) => {
        // Counts follow the other choices, so a number always means "this many would show".
        const counts = new Map<string, number>();
        for (const f of files) {
          if (matches(f, picks, facet)) counts.set(f[facet], (counts.get(f[facet]) ?? 0) + 1);
        }
        const options = [...counts.entries()]
          .sort(([a, x], [b, y]) => Number(a === "other") - Number(b === "other") || y - x);
        if (picks[facet] && !counts.has(picks[facet])) options.push([picks[facet], 0]);
        return (
          <label key={facet} className="min-w-0">
            <span className="mb-1 block text-xs text-muted">{t(label)}</span>
            <span className="relative block">
              <select value={picks[facet]} onChange={(e) => onChange({ ...picks, [facet]: e.target.value })}
                className={`w-full appearance-none truncate rounded-lg border bg-sheet py-1.5 pl-2.5 pr-7 text-sm outline-none focus-visible:border-cite ${picks[facet] ? "border-cite text-ink" : "border-rule text-muted"}`}>
                <option value="">{t("filterAny")}</option>
                {options.map(([value, n]) => (
                  <option key={value} value={value}>{valueName(facet, value)} ({n})</option>
                ))}
              </select>
              <ChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-faint" />
            </span>
          </label>
        );
      })}
    </div>
  );
}
