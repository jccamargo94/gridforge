"use client";

import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import type { NodalRedistributionRow } from "@/lib/types";

const EMERALD: [number, number, number] = [16, 185, 129];
const RED: [number, number, number] = [239, 68, 68];

function deltaColor(delta: number, maxAbs: number): string {
  if (maxAbs === 0 || delta === 0) return "rgba(63, 63, 70, 0.35)";
  const intensity = Math.min(1, Math.abs(delta) / maxAbs);
  const target = delta > 0 ? RED : EMERALD;
  const r = Math.round(63 + (target[0] - 63) * intensity);
  const g = Math.round(63 + (target[1] - 63) * intensity);
  const b = Math.round(70 + (target[2] - 70) * intensity);
  return `rgba(${r}, ${g}, ${b}, 0.55)`;
}

interface RedistributionMatrixProps { rows: NodalRedistributionRow[]; }

export function RedistributionMatrix({ rows }: RedistributionMatrixProps) {
  const t = useT();
  const maxAbs = Math.max(1, ...rows.map((row) => Math.abs(row.delta)));
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{t("nodal.redistributionSubtitle")}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((row) => (
          <div key={row.zone} data-zone={row.zone} data-delta={row.delta}
            className="rounded-lg border border-border p-3"
            style={{ backgroundColor: deltaColor(row.delta, maxAbs) }}>
            <p className="text-sm font-medium">{row.zone}</p>
            <p className="mt-1 font-mono text-sm tabular-nums">{formatNumber(row.delta)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}