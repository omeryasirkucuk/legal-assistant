// UI strings live in the repo-level locales/ directory so all Turkish copy stays in one place.
import tr from "../../../../locales/tr/common.json";

export type MessageKey = keyof typeof tr;

export function t(key: MessageKey, values?: Record<string, string | number>): string {
  let text: string = tr[key];
  for (const [name, value] of Object.entries(values ?? {})) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}
