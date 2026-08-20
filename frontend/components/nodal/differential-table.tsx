"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import { aggregateGenRevenueByZoneFuel } from "@/lib/nodal-chart-data";
import type { NodalGenRevenueRow, NodalRedistributionRow } from "@/lib/types";
import { DataTable } from "@/components/ui/data-table";

interface DifferentialTableProps {
  redistribution: NodalRedistributionRow[];
  genRevenue: NodalGenRevenueRow[];
}

function deltaClass(delta: number): string {
  return delta <= 0 ? "text-emerald-400" : "text-red-400";
}

export function DifferentialTable({ redistribution, genRevenue }: DifferentialTableProps) {
  const t = useT();

  const redistributionColumns: ColumnDef<NodalRedistributionRow>[] = useMemo(() => [
    { accessorKey: "zone", header: t("nodal.zone") },
    {
      accessorKey: "load_payment_a",
      header: t("nodal.loadPaymentA"),
      cell: ({ getValue }) => formatNumber(getValue<number>()),
    },
    {
      accessorKey: "load_payment_b",
      header: t("nodal.loadPaymentB"),
      cell: ({ getValue }) => formatNumber(getValue<number>()),
    },
    {
      accessorKey: "delta",
      header: t("nodal.delta"),
      cell: ({ getValue }) => {
        const value = getValue<number>();
        return <span className={deltaClass(value)}>{formatNumber(value)}</span>;
      },
    },
  ], [t]);

  const genRevenueRows = useMemo(() => aggregateGenRevenueByZoneFuel(genRevenue), [genRevenue]);

  const genRevenueColumns: ColumnDef<NodalGenRevenueRow>[] = useMemo(() => [
    { accessorKey: "zone", header: t("nodal.zone") },
    { accessorKey: "fuel", header: t("nodal.fuel") },
    {
      accessorKey: "revenue_a",
      header: t("nodal.genRevenueA"),
      cell: ({ getValue }) => formatNumber(getValue<number>()),
    },
    {
      accessorKey: "revenue_b",
      header: t("nodal.genRevenueB"),
      cell: ({ getValue }) => formatNumber(getValue<number>()),
    },
    {
      accessorKey: "delta",
      header: t("nodal.delta"),
      cell: ({ getValue }) => {
        const value = getValue<number>();
        return <span className={deltaClass(value)}>{formatNumber(value)}</span>;
      },
    },
  ], [t]);

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <p className="text-sm font-medium">{t("nodal.loadPaymentA")} / {t("nodal.loadPaymentB")}</p>
        <DataTable columns={redistributionColumns} data={redistribution} initialPageSize={10} />
      </div>
      <div className="space-y-3">
        <p className="text-sm font-medium">{t("nodal.genRevenueA")} / {t("nodal.genRevenueB")}</p>
        <DataTable columns={genRevenueColumns} data={genRevenueRows} initialPageSize={10} />
      </div>
    </div>
  );
}
