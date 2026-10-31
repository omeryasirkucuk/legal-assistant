// LLM spend as shown to the lawyer: US dollars, Turkish number format, enough decimals to
// tell a cheap answer from an expensive one.
const usd = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

export function formatUsd(value: number): string {
  return `${usd.format(value)}\u00a0$`; // no-break space: the amount and "$" stay together
}

/** Bytes in the units a lawyer reads: KB, MB, GB (Turkish decimals). */
export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1;
  return `${value.toLocaleString("tr-TR", { maximumFractionDigits: digits })} ${units[unit]}`;
}
