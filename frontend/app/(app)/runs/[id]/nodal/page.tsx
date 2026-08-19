"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowDownUp, Coins, Loader2, TrendingUp, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useT } from "@/lib/i18n-context";
import { useRunDetail } from "@/hooks/use-run-detail";
import { getRunNodalArtifact } from "@/lib/api-client";
import { formatNumber } from "@/lib/chart-format";
import { formatBogotaTime } from "@/lib/format-date";
import type { BranchFlowRow, LmpRow, NodalDispatchRow, RunStatus } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { NetworkCard } from "@/components/nodal/network-card";
import { ZonalMap } from "@/components/nodal/zonal-map";
import { PriceCurvesChart } from "@/components/nodal/price-curves-chart";
import { NodalDispatchChart } from "@/components/nodal/nodal-dispatch-chart";
import { BranchFlowsChart } from "@/components/nodal/branch-flows-chart";
import { DifferentialTable } from "@/components/nodal/differential-table";
import { RedistributionMatrix } from "@/components/nodal/redistribution-matrix";
import { NodalArtifactDownloads } from "@/components/nodal/nodal-artifact-downloads";
import { cn } from "@/lib/utils";

const STATUS_CLASSES: Record<RunStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  running: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  done: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border border-red-500/20",
};

interface MetricCardProps { label: string; value: string; icon: LucideIcon; }

function MetricCard({ label, value, icon: Icon }: MetricCardProps) {
  return (
    <Card size="sm">
      <CardContent className="py-3">
        <Icon className="size-4 text-muted-foreground" />
        <p className="mt-2 text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 font-heading text-lg font-bold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

export default function NodalDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const t = useT();
  const run = useRunDetail(id);
  const [hour, setHour] = useState(0);
  const nodal = run.data?.nodal ?? null;

  const lmpQuery = useQuery({
    queryKey: ["nodal-lmp", id],
    queryFn: () => getRunNodalArtifact<LmpRow[]>(id, "lmp"),
    enabled: Boolean(nodal?.artifacts.lmp),
  });
  const dispatchQuery = useQuery({
    queryKey: ["nodal-dispatch", id],
    queryFn: () => getRunNodalArtifact<NodalDispatchRow[]>(id, "dispatch"),
    enabled: Boolean(nodal?.artifacts.dispatch),
  });
  const branchFlowsQuery = useQuery({
    queryKey: ["nodal-branch_flows", id],
    queryFn: () => getRunNodalArtifact<BranchFlowRow[]>(id, "branch_flows"),
    enabled: Boolean(nodal?.artifacts.branch_flows),
  });

  if (run.isLoading) {
    return (
      <div className="flex items-center gap-3 py-12 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> {t("runDetail.loading")}
      </div>
    );
  }
  if (run.isError || !run.data || !nodal) {
    return (
      <Card className="border-red-500/20 bg-red-500/5">
        <CardContent className="py-6">
          <p role="alert" className="text-sm text-red-400">{t("nodal.noNodalData")}</p>
        </CardContent>
      </Card>
    );
  }

  const { metrics } = nodal;
  const priceAvgKeys = Object.keys(metrics).filter((key) => key.startsWith("price_avg_"));
  const priceVolKeys = Object.keys(metrics).filter((key) => key.startsWith("price_vol_"));

  const metricCards: MetricCardProps[] = [
    { label: t("nodal.totalCost"), value: formatNumber(metrics.total_cost), icon: Wallet },
    { label: t("nodal.loadPaymentDelta"), value: formatNumber(metrics.load_payment_delta), icon: ArrowDownUp },
    { label: t("nodal.genRevenueDelta"), value: formatNumber(metrics.gen_revenue_delta), icon: TrendingUp },
    { label: t("nodal.congestionRent"), value: formatNumber(metrics.congestion_rent_total), icon: Coins },
    ...priceAvgKeys.map((key) => ({
      label: `${t("nodal.priceAvg")} ${key.replace("price_avg_", "")}`,
      value: formatNumber(metrics[key]),
      icon: Wallet,
    })),
    ...priceVolKeys.map((key) => ({
      label: `${t("nodal.priceVol")} ${key.replace("price_vol_", "")}`,
      value: formatNumber(metrics[key]),
      icon: TrendingUp,
    })),
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 py-4">
          <Link
            href={`/runs/${id}`}
            className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1.5")}
          >
            <ArrowLeft className="size-4" /> {t("nodal.backToRun")}
          </Link>
          <div className="min-w-0">
            <p className="truncate font-mono text-xs text-muted-foreground">{run.data.run_id}</p>
            <h1 className="font-heading text-xl font-bold">
              {run.data.dispatch_date}
              <span className="ml-2 text-sm font-normal text-muted-foreground">{run.data.level}</span>
            </h1>
            <p className="text-xs text-muted-foreground">{formatBogotaTime(run.data.created_at)}</p>
          </div>
          <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs ${STATUS_CLASSES[run.data.status]}`}>
            {t(`status.${run.data.status}`)}
          </span>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-heading text-lg font-bold">{t("nodal.hour")}</h2>
          <select
            aria-label={t("nodal.hour")}
            value={hour}
            onChange={(e) => setHour(Number(e.target.value))}
            className="mt-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          >
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>{h}:00</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {metricCards.map((card) => (
          <MetricCard key={card.label} {...card} />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("nodal.mapTitle")}</CardTitle>
            <CardDescription>{t("nodal.mapSubtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ZonalMap
              zones={nodal.network.zones}
              branches={nodal.network.branches}
              generators={nodal.network.generators}
              lmpRows={lmpQuery.data ?? []}
              hour={hour}
            />
          </CardContent>
        </Card>
        <NetworkCard network={nodal.network} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.priceCurvesTitle")}</CardTitle>
          <CardDescription>{t("nodal.priceCurvesSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <PriceCurvesChart rows={lmpQuery.data ?? []} referenceZone={nodal.network.reference_zone} hour={hour} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("nodal.dispatchTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <NodalDispatchChart rows={dispatchQuery.data ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("nodal.branchFlowsTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <BranchFlowsChart rows={branchFlowsQuery.data ?? []} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.differentialTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <DifferentialTable redistribution={nodal.redistribution} genRevenue={nodal.gen_revenue_by_zone} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.redistributionTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <RedistributionMatrix rows={nodal.redistribution} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.downloadsTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <NodalArtifactDownloads runId={id} artifacts={nodal.artifacts} />
        </CardContent>
      </Card>
    </div>
  );
}