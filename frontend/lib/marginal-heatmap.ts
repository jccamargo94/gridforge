import type { MarginalCell } from "@/lib/types";

export type HeatmapRow = { label: string; hours: number[] };

/** Rows = technology (or zone); each of the 24 columns sums the shares of the
 * cells in that group, which is valid because every share uses the same
 * per-hour denominator. */
export function buildHeatmap(cells: MarginalCell[], by: "tech" | "zone"): HeatmapRow[] {
  const rows = new Map<string, number[]>();
  for (const c of cells) {
    const label = by === "tech" ? c.gen_type : (c.zone ?? "-");
    const hours = rows.get(label) ?? new Array<number>(24).fill(0);
    hours[c.hour] += c.share;
    rows.set(label, hours);
  }
  return [...rows.entries()]
    .map(([label, hours]) => ({ label, hours }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
