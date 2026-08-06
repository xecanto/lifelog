/** Formatting helpers for facet dates and amounts. */

/**
 * Parse a facet `due_at` (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`) in local time.
 *
 * `new Date("2026-08-05")` parses as UTC midnight, which renders as the 4th
 * for anyone west of Greenwich — an off-by-one day on every reminder. Parsing
 * the parts by hand keeps the date the user actually meant.
 */
export function parseLocalDate(value: string): Date {
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = (timePart ?? "").split(":").map(Number);
  return new Date(year, (month || 1) - 1, day || 1, hour || 0, minute || 0);
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Whole days from today to `value`. Negative means overdue. */
export function daysUntil(value: string, now = new Date()): number {
  return Math.round((startOfDay(parseLocalDate(value)) - startOfDay(now)) / 86_400_000);
}

export function hasTime(value: string): boolean {
  return value.includes("T");
}

export function formatDue(value: string): string {
  const date = parseLocalDate(value);
  const datePart = date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
  if (!hasTime(value)) return datePart;
  return `${datePart}, ${date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
}

export function relativeDue(value: string): string {
  const days = daysUntil(value);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  if (days < 0) return `${Math.abs(days)} days ago`;
  if (days < 14) return `in ${days} days`;
  if (days < 60) return `in ${Math.round(days / 7)} weeks`;
  return `in ${Math.round(days / 30)} months`;
}

export function formatMoney(amount: number, currency: string | null): string {
  if (currency && /^[A-Z]{3}$/.test(currency)) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
    } catch {
      // Unknown-but-well-formed code — fall through to the plain rendering.
    }
  }
  return currency ? `${amount} ${currency}` : String(amount);
}

export function titleCase(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Model spend, at a precision you can act on.
 *
 * A month of personal use lands in cents, so rounding to $0.00 would show
 * nothing at all. Sub-cent amounts keep enough decimals to stay non-zero;
 * dollar amounts drop to two.
 */
export function formatUsd(amount: number): string {
  if (amount === 0) return "$0.00";
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Token counts, which run to millions — 1.2M reads faster than 1,234,567. */
export function formatCount(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}K`;
  return `${(n / 1_000_000).toFixed(n < 10_000_000 ? 2 : 1)}M`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** A short local timestamp for log rows. */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
