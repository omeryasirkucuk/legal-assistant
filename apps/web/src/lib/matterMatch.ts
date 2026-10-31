// Which case files a message names, by exact mention only: a client's full name (at least
// two words, every word in order) or a file's case number. Nothing is guessed from topic
// or similarity, so a message is never tied to a file the lawyer did not name.
import type { Matter } from "@/lib/api";

function norm(s: string): string {
  return ` ${s.toLocaleLowerCase("tr-TR").replace(/[^\p{L}\p{N}/]+/gu, " ").replace(/\s+/g, " ").trim()} `;
}

function caseNumber(s: string): string | null {
  const m = s.match(/(\d{4})\s*\/\s*(\d+)/);
  return m ? `${m[1]}/${Number(m[2])}` : null;
}

function names(text: string, m: Matter): boolean {
  const client = norm(m.client).trim();
  return client.split(" ").length >= 2 && norm(text).includes(` ${client} `);
}

function numbers(text: string, m: Matter): boolean {
  const own = m.case_no ? caseNumber(m.case_no) : null;
  if (!own) return false;
  return [...text.matchAll(/(\d{4})\s*\/\s*(\d+)/g)].some(([, y, n]) => `${y}/${Number(n)}` === own);
}

export function mentionedMatters(text: string, matters: Matter[]): Matter[] {
  return matters.filter((m) => !m.closed && (names(text, m) || numbers(text, m)));
}
