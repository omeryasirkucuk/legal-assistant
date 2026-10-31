// Dates of deadlines as a lawyer reads them: "7 Eyl Pzt", and how many days are left.

const DAY_MS = 86_400_000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** A YYYY-MM-DD date as a local date (not shifted by the time zone). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Days from today to the date; negative when it has passed. */
export function daysUntil(iso: string, now = new Date()): number {
  return Math.round((startOfDay(parseDay(iso)) - startOfDay(now)) / DAY_MS);
}

export type Urgency = "overdue" | "today" | "soon" | "later";

export function urgency(days: number): Urgency {
  return days < 0 ? "overdue" : days === 0 ? "today" : days <= 3 ? "soon" : "later";
}

export function formatDay(iso: string, style: "short" | "long" = "short"): string {
  return parseDay(iso).toLocaleDateString("tr-TR", style === "short"
    ? { day: "numeric", month: "short", weekday: "short" }
    : { day: "numeric", month: "long", year: "numeric", weekday: "long" });
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
