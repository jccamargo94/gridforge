export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "\u2014";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatHourLabel(hour: number): string {
  const h = Math.max(0, Math.min(23, Math.floor(hour)));
  return `${String(h).padStart(2, "0")}:00`;
}
