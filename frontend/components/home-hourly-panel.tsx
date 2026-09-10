"use client";

import { X } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "@/components/chart-tooltip";
import { formatNumber } from "@/lib/chart-format";
import { buildHourlyPoints, hasHourlyData, type HourlySeriesKey } from "@/lib/home-hourly";
import { useT } from "@/lib/i18n-context";
import type { ChartSeriesRow } from "@/lib/types";

export interface HomeHourlySeries {
  key: HourlySeriesKey;
  name: string;
  color: string;
}

interface HomeHourlyPanelProps {
  row: ChartSeriesRow;
  series: HomeHourlySeries[];
  canViewRun: boolean;
  onClose: () => void;
  onViewRun: () => void;
}

export function HomeHourlyPanel({
  row,
  series,
  canViewRun,
  onClose,
  onViewRun,
}: HomeHourlyPanelProps) {
  const t = useT();
  const seriesKeys = series.map((s) => s.key);
  const points = buildHourlyPoints(row, seriesKeys);
  const hasData = hasHourlyData(points, seriesKeys);

  return (
    <section
      aria-label={t("home.hourly")}
      className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3"
    >
      <header className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-zinc-200">{t("home.hourly")}</h3>
        <span className="text-xs text-muted-foreground tabular-nums">{row.date}</span>
        <div className="ml-auto flex items-center gap-2">
          {canViewRun && (
            <button
              type="button"
              onClick={onViewRun}
              className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-200 transition-colors hover:border-zinc-500"
            >
              {t("home.viewRun")}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label={t("home.close")}
            className="rounded-full p-1 text-muted-foreground transition-colors hover:text-zinc-200"
          >
            <X className="size-4" />
          </button>
        </div>
      </header>
      {hasData ? (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={points} margin={{ top: 4, right: 16, left: 8, bottom: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="hour"
              tick={{ fill: "#a1a1aa", fontSize: 11 }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              minTickGap={24}
              label={{ value: t("chart.hour"), position: "bottom", offset: 4, fill: "#a1a1aa" }}
            />
            <YAxis
              width={56}
              tick={{ fill: "#a1a1aa", fontSize: 11 }}
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
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.name}
                stroke={s.color}
                dot={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="py-8 text-center text-sm text-muted-foreground">{t("home.hourlyEmpty")}</p>
      )}
    </section>
  );
}
