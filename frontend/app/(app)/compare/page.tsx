"use client";

import { RunComparisonTable } from "@/components/run-comparison-table";
import { RunSelector } from "@/components/run-selector";
import { useRunComparisons } from "@/hooks/use-run-comparisons";
import { listRuns } from "@/lib/api-client";
import type { RunDetail } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/lib/i18n-context";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

export default function ComparePage() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const runsQuery = useQuery({ queryKey: ["runs"], queryFn: listRuns });
  const comparisons = useRunComparisons(selectedIds);
  const t = useT();

  function toggle(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const loadedRuns: RunDetail[] = comparisons
    .map((c) => c.data)
    .filter((d): d is RunDetail => d !== undefined);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("compare.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("compare.subtitle")}
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t("compare.selectRuns")}</CardTitle>
        </CardHeader>
        <CardContent>
          {runsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t("compare.loading")}</p>
          )}
          {runsQuery.data && (
            <RunSelector runs={runsQuery.data} selectedIds={selectedIds} onToggle={toggle} />
          )}
        </CardContent>
      </Card>
      {comparisons.some((c) => c.isError) && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-400">
          {t("compare.loadError")}
        </p>
      )}
      {loadedRuns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t("compare.metricsComparison")}</CardTitle>
          </CardHeader>
          <CardContent>
            <RunComparisonTable runs={loadedRuns} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
