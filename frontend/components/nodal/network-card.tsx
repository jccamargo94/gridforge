"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import type { NodalBranch, NodalGenerator, NodalNetwork, NodalZone } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";

interface NetworkCardProps { network: NodalNetwork; }

export function NetworkCard({ network }: NetworkCardProps) {
  const t = useT();

  const zoneColumns: ColumnDef<NodalZone>[] = useMemo(() => [
    { accessorKey: "name", header: t("nodal.zone") },
    { accessorKey: "base_kv", header: t("nodal.baseMva") },
  ], [t]);

  const generatorColumns: ColumnDef<NodalGenerator>[] = useMemo(() => [
    { accessorKey: "name", header: t("nodal.generator") },
    { accessorKey: "zone", header: t("nodal.zone") },
    { accessorKey: "fuel", header: t("nodal.fuel") },
    {
      accessorKey: "marginal_cost",
      header: t("nodal.marginalCost"),
      cell: ({ getValue }) => formatNumber(getValue<number>(), 2),
    },
  ], [t]);

  const branchColumns: ColumnDef<NodalBranch>[] = useMemo(() => [
    { accessorKey: "name", header: t("nodal.branch") },
    {
      id: "fromTo",
      header: t("nodal.fromTo"),
      accessorFn: (branch) => `${branch.from_zone} → ${branch.to_zone}`,
    },
    {
      accessorKey: "reactance",
      header: t("nodal.reactance"),
      cell: ({ getValue }) => formatNumber(getValue<number>(), 4),
    },
    {
      accessorKey: "rating",
      header: t("nodal.rating"),
      cell: ({ getValue }) => formatNumber(getValue<number>(), 1),
    },
  ], [t]);

  const fuelMix = useMemo(() => {
    const counts = new Map<string, number>();
    for (const gen of network.generators) counts.set(gen.fuel, (counts.get(gen.fuel) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [network.generators]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("nodal.networkTitle")}</CardTitle>
        <CardDescription>
          <span>{network.name}</span> — {t("nodal.referenceZone")}: {network.reference_zone}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="text-muted-foreground">{t("nodal.networkName")}: {network.name}</span>
          <span className="text-muted-foreground">{t("nodal.baseMva")}: {network.baseMVA}</span>
          <span className="text-muted-foreground">{t("nodal.zones")}: {network.zones.length}</span>
          <span className="text-muted-foreground">{t("nodal.generators")}: {network.generators.length}</span>
          <span className="text-muted-foreground">{t("nodal.branches")}: {network.branches.length}</span>
        </div>
        {fuelMix.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {fuelMix.map(([fuel, count]) => (
              <span key={fuel} className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground">
                {fuel}: {count}
              </span>
            ))}
          </div>
        )}
        <div className="space-y-3">
          <p className="text-sm font-medium">{t("nodal.zone")}</p>
          <DataTable columns={zoneColumns} data={network.zones} initialPageSize={10} />
        </div>
        <div className="space-y-3">
          <p className="text-sm font-medium">{t("nodal.generator")}</p>
          <DataTable columns={generatorColumns} data={network.generators} initialPageSize={10} />
        </div>
        <div className="space-y-3">
          <p className="text-sm font-medium">{t("nodal.branch")}</p>
          <DataTable columns={branchColumns} data={network.branches} initialPageSize={10} />
        </div>
      </CardContent>
    </Card>
  );
}
