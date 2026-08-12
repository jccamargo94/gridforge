"use client";

import type { PricePoint } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

  if (!points || points.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        {t("chart.pricesNoData")}
      </div>
    );
  }

  const data = toChartData(points);

  return (
    <div className="w-full" style={{ minHeight: 320 }}>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data}>
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
              value: t("runDetail.copMwh"),
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
          <Line
            type="monotone"
            dataKey="model_mpo"
            name={t("runDetail.modelMpo")}
            stroke="#3b82f6"
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="xm_mpo"
            name={t("runDetail.xmMpo")}
            stroke="#f59e0b"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
