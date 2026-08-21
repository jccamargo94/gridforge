"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChartLegend, type ChartLegendItem } from "@/components/chart-legend";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { formatNumber } from "@/lib/chart-format";
import { useT } from "@/lib/i18n-context";
import { toAvgPriceData, toPriceCurveData } from "@/lib/nodal-chart-data";
import type { LmpRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];
const AVG_PRICE_KEY = "lmp_avg";
const AVG_PRICE_COLOR = "#ffffff";

interface PriceCurvesChartProps {
  rows: LmpRow[];
  hour: number;
}

export function PriceCurvesChart({ rows, hour }: PriceCurvesChartProps) {
  const t = useT();
  const { data: zoneData, seriesKeys } = useMemo(() => toPriceCurveData(rows), [rows]);
  const avgData = useMemo(() => toAvgPriceData(rows), [rows]);
  const data = useMemo(
    () => zoneData.map((point, i) => ({ ...point, [AVG_PRICE_KEY]: avgData[i]?.lmp_avg ?? 0 })),
    [zoneData, avgData],
  );
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{t("chart.pricesNoData")}</div>;
  }

  const legendItems: ChartLegendItem[] = [
    ...seriesKeys.map((key, index) => ({ key, name: key, color: PALETTE[index % PALETTE.length] })),
    { key: AVG_PRICE_KEY, name: t("nodal.avgPrice"), color: AVG_PRICE_COLOR },
  ];

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
              label={{ value: t("runDetail.copMwh"), angle: -90, position: "insideLeft", fill: "#a1a1aa" }} />
            <Tooltip content={<ChartTooltip unit={t("runDetail.copMwh")} hourLabel={t("chart.hourLabel")} />} />
            <ReferenceLine x={hour} stroke="#f59e0b" strokeDasharray="4 4" />
            {seriesKeys.map((key, index) => (
              <Line key={key} type="monotone" dataKey={key} name={key}
                stroke={PALETTE[index % PALETTE.length]} dot={false} strokeWidth={2}
                hide={hidden.has(key)} />
            ))}
            <Line key={AVG_PRICE_KEY} type="monotone" dataKey={AVG_PRICE_KEY}
              name={t("nodal.avgPrice")} stroke={AVG_PRICE_COLOR} dot={false}
              strokeWidth={3} strokeDasharray="6 4" hide={hidden.has(AVG_PRICE_KEY)} />
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
