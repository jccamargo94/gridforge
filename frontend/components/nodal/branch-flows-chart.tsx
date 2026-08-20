"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartLegend, type ChartLegendItem } from "@/components/chart-legend";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { formatNumber } from "@/lib/chart-format";
import { useT } from "@/lib/i18n-context";
import { toBranchFlowSeries } from "@/lib/nodal-chart-data";
import type { BranchFlowRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];

interface BranchFlowsChartProps { rows: BranchFlowRow[]; }

export function BranchFlowsChart({ rows }: BranchFlowsChartProps) {
  const t = useT();
  const { data, seriesKeys } = useMemo(() => toBranchFlowSeries(rows), [rows]);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{t("nodal.branchFlowsNoData")}</div>;
  }

  const legendItems: ChartLegendItem[] = seriesKeys.map((key, index) => ({
    key, name: key, color: PALETTE[index % PALETTE.length],
  }));

  const toggleSeries = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div>
      <div
        {...getWrapperProps()}
        ref={wrapperRef}
        title={t("chart.zoomHint")}
        className={cn("w-full", isZoomed ? "cursor-grab select-none active:cursor-grabbing" : "cursor-crosshair")}
        style={{ minHeight: 320 }}
      >
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={visibleData} margin={{ top: 8, right: 16, left: 8, bottom: 32 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="hour" tick={{ fill: "#a1a1aa" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{ value: t("chart.hour"), position: "bottom", offset: 8, fill: "#a1a1aa" }} />
            <YAxis tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: "#a1a1aa" }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{ value: t("nodal.unitMw"), angle: -90, position: "insideLeft", fill: "#a1a1aa" }} />
            <Tooltip content={<ChartTooltip unit={t("nodal.unitMw")} hourLabel={t("chart.hourLabel")} />} />
            {seriesKeys.map((key, index) => (
              <Line key={key} type="monotone" dataKey={key}
                name={key}
                stroke={PALETTE[index % PALETTE.length]} dot={false}
                strokeWidth={2}
                hide={hidden.has(key)} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {isZoomed && (
        <div className="mt-2 flex items-center justify-end gap-3 text-xs text-muted-foreground">
          <span className="hidden sm:inline">{t("chart.zoomHint")}</span>
          <button onClick={reset}
            className="rounded-full border border-zinc-700 px-3 py-1 text-zinc-200 hover:border-zinc-500">
            {t("chart.resetZoom")}
          </button>
        </div>
      )}
      <ChartLegend items={legendItems} hidden={hidden} onToggle={toggleSeries} />
    </div>
  );
}