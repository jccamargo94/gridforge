"use client";

import { ArtifactDownloads } from "@/components/artifact-downloads";
import { DispatchChart } from "@/components/dispatch-chart";
import { LogViewer } from "@/components/log-viewer";
import { MarginalPlantsTable } from "@/components/marginal-plants-table";
import { PriceSeriesChart } from "@/components/price-series-chart";
import { formatBogotaTime } from "@/lib/format-date";
import { formatNumber } from "@/lib/chart-format";
import { useRunDetail } from "@/hooks/use-run-detail";
import { getRunDispatch, getRunMarginalPlants } from "@/lib/api-client";
import { statusLabel } from "@/lib/run-status";
import { useLang, useT } from "@/lib/i18n-context";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  Activity,
  BarChart3,
  BatteryCharging,
  FileDown,
  Loader2,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import type { RunStatus } from "@/lib/types";

const STATUS_CLASSES: Record<RunStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  running: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  done: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border border-red-500/20",
};

function formatMetric(value: number | null, decimals = 2): string {
  if (value === null) return "\u2014";
  return formatNumber(value, decimals);
}

function formatPercent(value: number | null, decimals = 2): string {
  if (value === null) return "\u2014";
  return formatNumber(value * 100, decimals);
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading } = useRunDetail(id);
  const { lang } = useLang();
  const t = useT();

  const dispatchQuery = useQuery({
    queryKey: ["run-dispatch", id],
    queryFn: () => getRunDispatch(id),
    enabled: Boolean(data?.artifacts.dispatch),
  });

  const marginalPlantsQuery = useQuery({
    queryKey: ["run-marginal-plants", id],
    queryFn: () => getRunMarginalPlants(id),
    enabled: Boolean(data?.artifacts.marginal_plants),
  });

  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-3 py-12 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        {t("runDetail.loading")}
      </div>
    );
  }

  const isRunning = data.status === "running";

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 py-4">
          <div className="flex-1 min-w-0">
            <p className="font-mono text-xs text-muted-foreground truncate">
              {data.run_id}
            </p>
            <h1 className="font-heading text-xl font-bold">
              {data.dispatch_date}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {data.level}
              </span>
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span>{formatBogotaTime(data.created_at)}</span>
            {data.scenario_id && (
              <span className="rounded border border-border px-2 py-0.5 font-mono">
                {data.scenario_id}
              </span>
            )}
          </div>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
              STATUS_CLASSES[data.status]
            )}
          >
            {isRunning && <Loader2 className="size-3 animate-spin" />}
            {statusLabel(data.status, lang)}
          </span>
        </CardContent>
      </Card>

      {data.status === "failed" && data.error && (
        <Card className="border-red-500/20 bg-red-500/5">
          <CardContent className="py-3">
            <p className="text-sm text-red-400" role="alert">
              {data.error}
            </p>
          </CardContent>
        </Card>
      )}

      {data.metrics && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <MetricCard
            label={t("runDetail.rmse")}
            value={formatMetric(data.metrics.rmse)}
            unit={t("runDetail.copMwh")}
            icon={Activity}
          />
          <MetricCard
            label={t("runDetail.mae")}
            value={formatMetric(data.metrics.mae)}
            unit={t("runDetail.copMwh")}
            icon={BarChart3}
          />
          <MetricCard
            label={t("runDetail.bias")}
            value={formatMetric(data.metrics.bias)}
            unit={t("runDetail.copMwh")}
            icon={TrendingDown}
          />
          <MetricCard
            label={t("runDetail.wape")}
            value={formatPercent(data.metrics.wape)}
            unit="%"
            icon={TrendingDown}
          />
          <MetricCard
            label={t("runDetail.smape")}
            value={formatPercent(data.metrics.smape)}
            unit="%"
            icon={TrendingDown}
          />
          <MetricCard
            label={t("runDetail.r2")}
            value={formatMetric(data.metrics.r2, 4)}
            icon={TrendingUp}
          />
          <MetricCard
            label={t("runDetail.dispatchMae")}
            value={formatMetric(data.metrics.dispatch_mae_mw)}
            unit={t("chart.mw")}
            icon={Activity}
          />
          <MetricCard
            label={t("runDetail.dispatchRms")}
            value={formatMetric(data.metrics.dispatch_rmse_mw)}
            unit={t("chart.mw")}
            icon={BarChart3}
          />
          {data.metrics.bess_charge_mwh !== null && (
            <MetricCard
              label={t("runDetail.bessCharge")}
              value={formatMetric(data.metrics.bess_charge_mwh)}
              unit="MWh"
              icon={BatteryCharging}
            />
          )}
          {data.metrics.bess_discharge_mwh !== null && (
            <MetricCard
              label={t("runDetail.bessDischarge")}
              value={formatMetric(data.metrics.bess_discharge_mwh)}
              unit="MWh"
              icon={Zap}
            />
          )}
          {data.metrics.bess_net_revenue !== null && (
            <MetricCard
              label={t("runDetail.netRevenue")}
              value={formatMetric(data.metrics.bess_net_revenue, 2)}
              unit="COP"
              icon={FileDown}
            />
          )}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("runDetail.dispatchChart")}</CardTitle>
        </CardHeader>
        <CardContent>
          <DispatchChart rows={dispatchQuery.data ?? []} lang={lang} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("runDetail.pricesChart")}</CardTitle>
        </CardHeader>
        <CardContent>
          <PriceSeriesChart points={data.price_series} />
        </CardContent>
      </Card>

      {data.artifacts.marginal_plants && (
        <Card>
          <CardHeader>
            <CardTitle>{t("runDetail.marginalPlants")}</CardTitle>
          </CardHeader>
          <CardContent>
            {marginalPlantsQuery.isLoading ? (
              <div className="flex items-center gap-3 py-12 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                {t("runDetail.loading")}
              </div>
            ) : (
              <MarginalPlantsTable rows={marginalPlantsQuery.data ?? []} />
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("runDetail.downloadResults")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ArtifactDownloads runId={data.run_id} artifacts={data.artifacts} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("runDetail.solverLog")}</CardTitle>
        </CardHeader>
        <CardContent>
          <LogViewer runId={data.run_id} />
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({
  label,
  value,
  unit,
  icon: Icon,
}: {
  label: string;
  value: string;
  unit?: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card size="sm">
      <CardContent className="py-3">
        <div className="flex items-center gap-2">
          <Icon className="size-4 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
        <p className="mt-1 font-heading text-lg font-bold tabular-nums">
          {value}
          {unit && (
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              {unit}
            </span>
          )}
        </p>
      </CardContent>
    </Card>
  );
}
