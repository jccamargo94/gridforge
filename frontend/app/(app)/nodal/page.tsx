"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Network } from "lucide-react";
import { listRuns } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import { formatBogotaTime } from "@/lib/format-date";
import type { RunStatus } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const STATUS_CLASSES: Record<RunStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  running: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  done: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border border-red-500/20",
};

export default function NodalPage() {
  const t = useT();
  const { data: runs, isLoading, isError } = useQuery({ queryKey: ["runs"], queryFn: listRuns });
  const nodalRuns = (runs ?? []).filter((run) => run.level === "lmp");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("nodal.listTitle")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("nodal.listSubtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.listTitle")}</CardTitle>
          <CardDescription>{t("nodal.listSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">{t("runs.loading")}</p>}
          {isError && (
            <p role="alert" className="py-8 text-center text-sm text-red-400">{t("runs.loadError")}</p>
          )}
          {!isLoading && !isError && nodalRuns.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <Network className="size-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">{t("nodal.noRuns")}</p>
              <p className="text-xs text-muted-foreground">{t("nodal.noRunsHint")}</p>
            </div>
          )}
          {nodalRuns.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("runsTable.date")}</TableHead>
                    <TableHead>{t("runsTable.status")}</TableHead>
                    <TableHead>{t("runsTable.runId")}</TableHead>
                    <TableHead>{t("nodal.networkName")}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {nodalRuns.map((run) => (
                    <TableRow key={run.run_id}>
                      <TableCell>{formatBogotaTime(run.created_at)}</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs ${STATUS_CLASSES[run.status]}`}>
                          {t(`status.${run.status}`)}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{run.run_id}</TableCell>
                      <TableCell>
                        {run.nodal ? (
                          <div className="space-y-1">
                            <p className="text-sm font-medium">{run.nodal.network_name ?? "—"}</p>
                            <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                              <span>{run.nodal.zones} {t("nodal.zones")}</span>
                              <span>·</span>
                              <span>{run.nodal.generators} {t("nodal.generators")}</span>
                              <span>·</span>
                              <span>{run.nodal.branches} {t("nodal.branches")}</span>
                            </div>
                          </div>
                        ) : (
                          <span className="text-sm text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {run.status === "done" && run.nodal && (
                          <Link
                            href={`/runs/${run.run_id}/nodal`}
                            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
                          >
                            <Network className="size-3.5" />
                            {t("nodal.openDashboard")}
                          </Link>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}