"use client";

import { CreateRunForm } from "@/components/create-run-form";
import { RunsTable } from "@/components/runs-table";
import { listRuns } from "@/lib/api-client";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useT } from "@/lib/i18n-context";
import { cn } from "@/lib/utils";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, CheckCircle2, Clock, Loader2, XCircle, Zap } from "lucide-react";

export default function RunsPage() {
  const queryClient = useQueryClient();
  const runsQuery = useQuery({ queryKey: ["runs"], queryFn: listRuns });
  const t = useT();

  const runs = runsQuery.data ?? [];
  const totalRuns = runs.length;
  const pendingRuns = runs.filter((r) => r.status === "pending").length;
  const runningRuns = runs.filter((r) => r.status === "running").length;
  const doneRuns = runs.filter((r) => r.status === "done").length;
  const failedRuns = runs.filter((r) => r.status === "failed").length;

  const stats = [
    { label: t("runs.stats.total"), value: totalRuns, icon: Activity, color: "text-muted-foreground" },
    { label: t("runs.stats.pending"), value: pendingRuns, icon: Clock, color: "text-amber-400" },
    { label: t("runs.stats.running"), value: runningRuns, icon: Loader2, color: "text-blue-400" },
    { label: t("runs.stats.done"), value: doneRuns, icon: CheckCircle2, color: "text-emerald-400" },
    { label: t("runs.stats.failed"), value: failedRuns, icon: XCircle, color: "text-red-400" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("runs.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("runs.subtitle")}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {stats.map((stat) => (
          <Card key={stat.label} size="sm">
            <CardContent className="flex items-center gap-3 py-3">
              <stat.icon className={cn("size-5", stat.color)} />
              <div>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
                <p className="font-heading text-lg font-bold tabular-nums">
                  {runsQuery.isLoading ? "\u2014" : stat.value}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("runs.newExecution")}</CardTitle>
          <CardDescription>
            {t("runs.newExecutionDesc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CreateRunForm
            onCreated={() => queryClient.invalidateQueries({ queryKey: ["runs"] })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("runs.executionHistory")}</CardTitle>
        </CardHeader>
        <CardContent>
          {runsQuery.isLoading ? (
            <div className="flex items-center gap-3 py-8 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              {t("runs.loading")}
            </div>
          ) : runsQuery.data && runsQuery.data.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Zap className="size-10 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                {t("runs.empty")}
              </p>
              <p className="text-xs text-muted-foreground/60">
                {t("runs.emptyHint")}
              </p>
            </div>
          ) : (
            <RunsTable runs={runsQuery.data ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
