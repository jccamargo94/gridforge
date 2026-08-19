"use client";

import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import type { NodalGenRevenueRow, NodalRedistributionRow } from "@/lib/types";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

interface DifferentialTableProps {
  redistribution: NodalRedistributionRow[];
  genRevenue: NodalGenRevenueRow[];
}

function deltaClass(delta: number): string {
  return delta <= 0 ? "text-emerald-400" : "text-red-400";
}

export function DifferentialTable({ redistribution, genRevenue }: DifferentialTableProps) {
  const t = useT();
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium">{t("nodal.loadPaymentA")} / {t("nodal.loadPaymentB")}</p>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("nodal.zone")}</TableHead>
                <TableHead>{t("nodal.loadPaymentA")}</TableHead>
                <TableHead>{t("nodal.loadPaymentB")}</TableHead>
                <TableHead>{t("nodal.delta")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {redistribution.map((row) => (
                <TableRow key={row.zone}>
                  <TableCell className="font-medium">{row.zone}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.load_payment_a)}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.load_payment_b)}</TableCell>
                  <TableCell className={`tabular-nums ${deltaClass(row.delta)}`}>{formatNumber(row.delta)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium">{t("nodal.genRevenueA")} / {t("nodal.genRevenueB")}</p>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("nodal.zone")}</TableHead>
                <TableHead>{t("nodal.fuel")}</TableHead>
                <TableHead>{t("nodal.genRevenueA")}</TableHead>
                <TableHead>{t("nodal.genRevenueB")}</TableHead>
                <TableHead>{t("nodal.delta")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {genRevenue.map((row, index) => (
                <TableRow key={`${row.zone}-${row.fuel}-${index}`}>
                  <TableCell className="font-medium">{row.zone}</TableCell>
                  <TableCell>{row.fuel}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.revenue_a)}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.revenue_b)}</TableCell>
                  <TableCell className={`tabular-nums ${deltaClass(row.delta)}`}>{formatNumber(row.delta)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}