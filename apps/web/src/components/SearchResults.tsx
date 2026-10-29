import type { DecisionHit } from "@/lib/api";
import { t } from "@/lib/i18n";

export function SearchResults({ query, hits }: { query: string; hits: DecisionHit[] | null }) {
  return (
    <section className="max-w-[42rem]">
      <h2 className="font-serif text-xl text-ink">{query}</h2>
      <p className="mt-1 text-sm text-muted">{t("searchHint")}</p>
      {hits === null ? (
        <p className="mt-6 flex items-center gap-2 text-sm text-muted">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cite" />
        </p>
      ) : hits.length === 0 ? (
        <p className="mt-6 text-sm text-muted">{t("searchEmpty")}</p>
      ) : (
        <ol className="mt-6 divide-y divide-rule">
          {hits.map((h) => (
            <li key={h.id} className="py-4">
              <a href={h.url} target="_blank" rel="noreferrer" className="text-[15px] font-medium text-cite hover:underline">
                {h.citation}
              </a>
              <p className="mt-1.5 line-clamp-4 font-serif text-[0.95rem] leading-relaxed text-ink">{h.passage}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
