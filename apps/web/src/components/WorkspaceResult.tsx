import { api, type WorkspaceSummary } from "@/lib/api";
import { t } from "@/lib/i18n";

type Props = { chatId: string; messageId: string; result: WorkspaceSummary };

function value(text: string, unit: string) {
  if (unit === "date") return text;
  const number = Number(text);
  if (!Number.isFinite(number)) return text;
  const money = unit !== "day" && unit !== "number";
  const translated = new Intl.NumberFormat("tr-TR", money
    ? { maximumFractionDigits: 2, minimumFractionDigits: 2 }
    : { maximumFractionDigits: 10 }).format(number);
  return money ? `${translated} ${unit === "TRY" ? "TL" : unit}` : unit === "day" ? t("workspaceDays", { value: translated }) : translated;
}

export function WorkspaceResult({ chatId, messageId, result }: Props) {
  const downloads = [
    ...result.edits.map((edit, index) => ({
      key: String(index), name: t("workspaceWord", { name: edit.name }),
    })),
    ...(result.format === "xlsx" ? [{ key: "xlsx", name: t("workspaceExcel") }] : []),
  ];
  const hasChanges = result.changes.length > 0 || result.edits.some((edit) => edit.changes.length);
  if (!hasChanges && downloads.length === 0) return null;
  return (
    <div className="space-y-2 text-sm">
      {downloads.map((download) => (
        <a key={download.key} href={api.workspaceOutput(chatId, messageId, download.key)}
          className="block w-fit font-medium text-cite underline decoration-cite/40 underline-offset-2">
          {download.name}
        </a>
      ))}
      {hasChanges && (
        <details className="rounded-md border border-rule px-3 py-2">
          <summary className="cursor-pointer text-cite">
            {t("workspaceChanges", { revision: result.revision })}
          </summary>
          <ul className="mt-2 space-y-1 text-ink">
            {result.changes.map((change, index) => (
              <li key={index}>
                {change.label}. {value(change.before, change.old_unit)} → {value(change.after, change.unit)}
              </li>
            ))}
            {result.edits.flatMap((edit) => edit.changes.map((change, index) => (
              <li key={`${edit.name}-${index}`}>
                {t("workspaceParagraph", { name: edit.name, paragraph: change.paragraph })}.{" "}
                {change.before} → {change.after}
              </li>
            )))}
          </ul>
        </details>
      )}
    </div>
  );
}
