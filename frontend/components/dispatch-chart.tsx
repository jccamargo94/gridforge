"use client";

import { toHourlyDispatchSeries } from "@/lib/dispatch-chart-data";
import type { Lang } from "@/lib/i18n";
import type { DispatchRow } from "@/lib/types";
import { useLang, useT } from "@/lib/i18n-context";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
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

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        {t("chart.noData")}
      </div>
    );
  }

  const { data, seriesKeys } = toHourlyDispatchSeries(rows, l);

  return (
    <div className="w-full" style={{ minHeight: 320 }}>
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="hour"
            tick={{ fill: "#a1a1aa" }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
            label={{
              value: t("chart.hour"),
              position: "insideBottom",
              offset: -5,
              fill: "#a1a1aa",
            }}
          />
          <YAxis
            tick={{ fill: "#a1a1aa" }}
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
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #27272a",
              borderRadius: "8px",
              color: "#fafafa",
              fontSize: "13px",
            }}
            itemStyle={{ color: "#fafafa" }}
          />
          <Legend wrapperStyle={{ color: "#fafafa" }} />
          {seriesKeys.map((key, i) => (
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
  );
}
