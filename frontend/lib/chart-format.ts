export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "\u2014";
  // Solver floating-point noise (e.g. -2.3e-10) rounds to zero at the
  // requested precision but Intl.NumberFormat still renders "-0" for it --
  // force true (positive) zero once rounding would make it zero anyway.
  const safeValue = Number(value.toFixed(decimals)) === 0 ? 0 : value;
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(safeValue);
}

export function formatHourLabel(hour: number): string {
  const h = Math.max(0, Math.min(23, Math.floor(hour)));
  return `${String(h).padStart(2, "0")}:00`;
}
