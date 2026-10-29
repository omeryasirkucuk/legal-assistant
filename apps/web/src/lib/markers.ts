// Turns the model's raw answer (with [[E3]] markers and <quote ref="E3"> tags) into Markdown
// whose citations are links to "#cite-E3"; the Markdown renderer swaps those for chips.

const MARKER = /\[\[(E\d+)\]\]/g;
const QUOTE = /<quote\s+ref="(E\d+)"\s*>([\s\S]*?)<\/quote>(\s*\[\[\1\]\])?/g;
// While streaming, a marker or quote tag can arrive in pieces; hide the unfinished tail.
const PARTIAL_TAIL = /(\[\[?E?\d*\]?$|<quote[^>]*$|<\/?q?u?o?t?e?$)/;

export function citationOrder(raw: string): string[] {
  const order: string[] = [];
  for (const m of raw.matchAll(/\[\[(E\d+)\]\]|<quote\s+ref="(E\d+)"/g)) {
    const key = m[1] ?? m[2];
    if (!order.includes(key)) order.push(key);
  }
  return order;
}

export function toMarkdown(raw: string, streaming = false): string {
  let text = streaming ? raw.replace(PARTIAL_TAIL, "") : raw;
  if (streaming) {
    // An opened quote without its closing tag: show the text so far as a plain quotation.
    text = text.replace(/<quote\s+ref="(E\d+)"\s*>([^<]*)$/, "“$2");
  }
  text = text.replace(QUOTE, (_m, key: string, body: string) => `“${body.trim()}”[${key}](#cite-${key})`);
  return text.replace(MARKER, (_m, key: string) => `[${key}](#cite-${key})`);
}

// Answers are written as <short>…</short><detail>…</detail> (see prompts/tr/answer_system.md).
// While streaming, a section may be open without its closing tag yet.
export function splitSections(raw: string): { short: string | null; detail: string } {
  const text = raw.replace(/<\/?(s|sh|sho|shor|d|de|det|deta|detai)?$/, "");
  const short = /<short>([\s\S]*?)(?:<\/short>|$)/.exec(text);
  if (!short) return { short: null, detail: text };
  const detail = /<detail>([\s\S]*?)(?:<\/detail>|$)/.exec(text);
  return { short: short[1].trim(), detail: detail ? detail[1].trim() : "" };
}
