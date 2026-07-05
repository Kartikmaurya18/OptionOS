const priceFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
});

const strikeFormatter = new Intl.NumberFormat("en-US");

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return "--";
  return priceFormatter.format(value);
}

export function formatStrike(value: number): string {
  return strikeFormatter.format(value);
}

/** Delta expiry strings are ddmmyy, e.g. "050726" -> "05 Jul 2026". */
export function formatExpiry(expiry: string | null): string {
  if (!expiry || expiry.length !== 6) return "--";
  const day = Number(expiry.slice(0, 2));
  const month = Number(expiry.slice(2, 4));
  const year = Number(expiry.slice(4, 6));
  const date = new Date(2000 + year, month - 1, day);
  if (Number.isNaN(date.getTime())) return expiry;
  return date.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatRelativeTime(timestampMs: number | null): string {
  if (timestampMs == null) return "--";
  const diffSeconds = Math.max(0, Math.round((Date.now() - timestampMs) / 1000));
  if (diffSeconds < 2) return "just now";
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  return `${diffHours}h ago`;
}
