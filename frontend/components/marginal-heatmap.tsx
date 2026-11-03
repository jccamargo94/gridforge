"use client";

import { buildHeatmap } from "@/lib/marginal-heatmap";
import type { MarginalCell } from "@/lib/types";

export function MarginalHeatmap({ cells, by }: { cells: MarginalCell[]; by: "tech" | "zone" }) {
  const rows = buildHeatmap(cells, by);
  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr>
            <th className="pr-3 text-left" />
            {Array.from({ length: 24 }, (_, h) => (
              <th key={h} className="w-8 text-center font-normal text-muted-foreground">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th className="whitespace-nowrap pr-3 text-left font-medium">{row.label}</th>
              {row.hours.map((v, h) => (
                <td
                  key={h}
                  title={`${row.label} ${h}h: ${(v * 100).toFixed(1)}%`}
                  className="h-7 w-8 text-center"
                  style={{ backgroundColor: `rgba(245, 158, 11, ${Math.min(v, 1)})` }}
                >
                  {v >= 0.1 ? Math.round(v * 100) : ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
