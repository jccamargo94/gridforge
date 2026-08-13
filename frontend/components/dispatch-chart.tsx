"use client";

import { useState } from "react";
import { toHourlyDispatchSeries, type HourlyDispatchPoint } from "@/lib/dispatch-chart-data";
import type { Lang } from "@/lib/i18n";
import type { DispatchRow } from "@/lib/types";
import { useLang, useT } from "@/lib/i18n-context";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { ChartLegend } from "@/components/chart-legend";
import { ChartTooltip } from "@/components/chart-tooltip";
import { formatNumber } from "@/lib/chart-format";
import { cn } from "@/lib/utils";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const COLORS = [
  "#f59e0b",
  "#3b82f6",
  "#10b981",
  "#06b6d4",
  "#8b5cf6",
  "#f97316",
  "#64748b",
];

export function DispatchChart({ rows, lang }: { rows: DispatchRow[]; lang?: Lang }) {
  const { lang: ctxLang } = useLang();
  const l = lang ?? ctxLang;
  const t = useT();
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set());

  const { data: allData, seriesKeys } = toHourlyDispatchSeries(rows, l);
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(allData);

  if (allData.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        {t("chart.noData")}
      </div>
    );
  }

  const toggleSeries = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const visibleKeys = seriesKeys.filter((key) => !hidden.has(key));

  const data: HourlyDispatchPoint[] = visibleData.map((point) => {
    const filtered: HourlyDispatchPoint = { hour: point.hour };
    for (const key of visibleKeys) {
      if (point[key] !== undefined) filtered[key] = point[key];
    }
    return filtered;
  });

  const legendItems = seriesKeys.map((key, i) => ({
    key,
    name: key,
    color: COLORS[i % COLORS.length],
  }));

  return (
    <div>
      <div
        {...getWrapperProps()}
        ref={wrapperRef}
        title={t("chart.zoomHint")}
        className={cn(
          "w-full",
          isZoomed ? "cursor-grab select-none active:cursor-grabbing" : "cursor-crosshair"
        )}
        style={{ minHeight: 320 }}
      >
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 32 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="hour"
              tick={{ fill: "#a1a1aa" }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{
                value: t("chart.hour"),
                position: "bottom",
                offset: 8,
                fill: "#a1a1aa",
              }}
            />
            <YAxis
              tick={{ fill: "#a1a1aa" }}
              tickFormatter={(value: number) => formatNumber(value)}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{
                value: t("chart.mw"),
                angle: -90,
                position: "insideLeft",
                fill: "#a1a1aa",
              }}
            />
            <Tooltip
              content={
                <ChartTooltip unit={t("chart.mw")} hourLabel={t("chart.hourLabel")} />
              }
            />
            {visibleKeys.map((key, i) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stackId="dispatch"
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {isZoomed && (
        <div className="mt-2 flex items-center justify-end gap-3 text-xs text-muted-foreground">
          <span className="hidden sm:inline">{t("chart.zoomHint")}</span>
          <button
            type="button"
            onClick={reset}
            className="rounded-full border border-zinc-700 px-3 py-1 text-zinc-200 transition-colors hover:border-zinc-500"
          >
            {t("chart.resetZoom")}
          </button>
        </div>
      )}
      <ChartLegend items={legendItems} hidden={hidden} onToggle={toggleSeries} />
    </div>
  );
}
