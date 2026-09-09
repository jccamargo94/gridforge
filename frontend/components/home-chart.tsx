"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Zap } from "lucide-react";
import { ChartLegend } from "@/components/chart-legend";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import type { ChartSeriesRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const SERIES = [
  { key: "bolsa_tx1", labelKey: "home.tx1", color: "#22c55e" },
  { key: "mpo_xm", labelKey: "home.mpo", color: "#f59e0b" },
  { key: "ideal_settled", labelKey: "home.idealSettled", color: "#3b82f6" },
  { key: "ideal_provisional", labelKey: "home.idealProv", color: "#38bdf8" },
  { key: "preideal", labelKey: "home.preideal", color: "#a78bfa" },
] as const;

type SeriesKey = (typeof SERIES)[number]["key"];

const SERIES_KEYS: readonly SeriesKey[] = SERIES.map((s) => s.key);

// Drill-down priority: a settled ideal run beats a provisional one, which
// beats preideal. A day without any run id never navigates.
export function bestRunId(row: ChartSeriesRow): string | null {
  return (
    row.ideal_settled_run_id ?? row.ideal_provisional_run_id ?? row.preideal_run_id ?? null
  );
}

export function handleChartClick(
  rows: ChartSeriesRow[],
  activeLabel: string | number | undefined,
  push: (href: string) => void
): void {
  if (activeLabel === undefined) return;
  const row = rows.find((r) => r.date === String(activeLabel));
  const id = row ? bestRunId(row) : null;
  if (id !== null) push(`/runs/${id}`);
}

function isEmptyWindow(rows: ChartSeriesRow[]): boolean {
  return rows.length === 0 || rows.every((r) => SERIES_KEYS.every((k) => r[k] == null));
}

interface HomeTooltipEntry {
  name?: React.ReactNode;
  value?: number | string | null;
  color?: string;
  dataKey?: string | number;
}

export function HomeChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: ReadonlyArray<HomeTooltipEntry>;
  label?: string | number;
  unit?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const visible = payload.filter(
    (entry): entry is HomeTooltipEntry & { value: number } =>
      typeof entry.value === "number" && !Number.isNaN(entry.value)
  );

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/95 px-3 py-2 text-[13px] text-zinc-50 shadow-xl backdrop-blur">
      <p className="mb-1.5 font-medium text-zinc-200 tabular-nums">{String(label ?? "")}</p>
      <ul className="space-y-1">
        {visible.map((entry) => (
          <li
            key={String(entry.dataKey ?? entry.name)}
            className="flex items-center gap-2 tabular-nums"
          >
            <span
              className="inline-block size-2 shrink-0 rounded-full"
              style={{ backgroundColor: entry.color ?? "#a1a1aa" }}
            />
            <span className="text-zinc-300">{entry.name}</span>
            <span className="ml-auto pl-4 font-medium text-zinc-50">
              {formatNumber(entry.value)}
              {unit && <span className="ml-1 text-xs font-normal text-zinc-400">{unit}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HomeChart({ rows }: { rows: ChartSeriesRow[] | null }) {
  const t = useT();
  const router = useRouter();
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set());

  const data = rows ?? [];
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

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
    name: t(s.labelKey),
    color: s.color,
  }));

  const empty = isEmptyWindow(data);

  return (
    <div>
      {empty ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <Zap className="size-10 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">{t("home.empty")}</p>
        </div>
      ) : (
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
            <LineChart
              data={visibleData}
              margin={{ top: 8, right: 16, left: 8, bottom: 32 }}
              onClick={(state) =>
                handleChartClick(rows ?? [], state.activeLabel, (href) => {
                  router.push(href);
                })
              }
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#a1a1aa", fontSize: 12 }}
                axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
                minTickGap={28}
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
              <Tooltip content={<HomeChartTooltip unit={t("runDetail.copMwh")} />} />
              {SERIES.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={t(s.labelKey)}
                  stroke={s.color}
                  dot={false}
                  connectNulls={false}
                  hide={hidden.has(s.key)}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {isZoomed && !empty && (
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
      {!empty && <ChartLegend items={legendItems} hidden={hidden} onToggle={toggleSeries} />}
      <p className="mt-2 text-xs text-muted-foreground">{t("home.tx1Lag")}</p>
    </div>
  );
}

// Preideal is a single merged lane server-side (chart.py _SERIES_KEYS: a
// settled hit wins and the provisional id becomes unreachable once a settled
// run exists for the day), so one preideal line covers both grades here.
