"use client";

import { useState } from "react";
import type { PricePoint } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { ChartLegend } from "@/components/chart-legend";
import { ChartTooltip } from "@/components/chart-tooltip";
import { formatNumber } from "@/lib/chart-format";
import { cn } from "@/lib/utils";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const SERIES = [
  { key: "model_mpo", color: "#3b82f6" },
  { key: "xm_mpo", color: "#f59e0b" },
];

function hourOfDay(datetime: string): number {
  const timePart = datetime.includes("T")
    ? (datetime.split("T")[1] ?? "00:00")
    : (datetime.split(" ")[1] ?? "00:00");
  return Number(timePart.split(":")[0]);
}

function toChartData(points: PricePoint[]) {
  return points
    .map((p) => ({ hour: hourOfDay(p.datetime), model_mpo: p.model_mpo, xm_mpo: p.xm_mpo }))
    .sort((a, b) => a.hour - b.hour);
}

export function PriceSeriesChart({ points }: { points: PricePoint[] | null }) {
  const t = useT();
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set());

  const allData = toChartData(points ?? []);
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(allData);

  if (!points || points.length === 0 || allData.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        {t("chart.pricesNoData")}
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

  const legendItems = SERIES.map((s) => ({
    key: s.key,
    name: t(s.key === "model_mpo" ? "runDetail.modelMpo" : "runDetail.xmMpo"),
    color: s.color,
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
          <LineChart data={visibleData} margin={{ top: 8, right: 16, left: 8, bottom: 32 }}>
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
                value: t("runDetail.copMwh"),
                angle: -90,
                position: "insideLeft",
                fill: "#a1a1aa",
              }}
            />
            <Tooltip
              content={
                <ChartTooltip unit={t("runDetail.copMwh")} hourLabel={t("chart.hourLabel")} />
              }
            />
            {SERIES.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={t(s.key === "model_mpo" ? "runDetail.modelMpo" : "runDetail.xmMpo")}
                stroke={s.color}
                dot={false}
                hide={hidden.has(s.key)}
              />
            ))}
          </LineChart>
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
