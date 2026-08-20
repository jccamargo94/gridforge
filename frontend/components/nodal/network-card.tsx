"use client";

import { useT } from "@/lib/i18n-context";
import type { NodalNetwork } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

interface NetworkCardProps { network: NodalNetwork; }

export function NetworkCard({ network }: NetworkCardProps) {
  const t = useT();
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
        </div>
        <div className="space-y-4">
          <p className="text-sm font-medium">{t("nodal.zone")}</p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodal.zone")}</TableHead>
                  <TableHead>{t("nodal.baseMva")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {network.zones.map((zone) => (
                  <TableRow key={zone.name}>
                    <TableCell className="font-medium">{zone.name}</TableCell>
                    <TableCell>{zone.base_kv}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        <div className="space-y-4">
          <p className="text-sm font-medium">{t("nodal.generator")}</p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodal.generator")}</TableHead>
                  <TableHead>{t("nodal.zone")}</TableHead>
                  <TableHead>{t("nodal.fuel")}</TableHead>
                  <TableHead>{t("nodal.marginalCost")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {network.generators.map((gen) => (
                  <TableRow key={gen.name}>
                    <TableCell className="font-medium">{gen.name}</TableCell>
                    <TableCell>{gen.zone}</TableCell>
                    <TableCell>{gen.fuel}</TableCell>
                    <TableCell>{gen.marginal_cost}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        <div className="space-y-4">
          <p className="text-sm font-medium">{t("nodal.branch")}</p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodal.branch")}</TableHead>
                  <TableHead>{t("nodal.fromTo")}</TableHead>
                  <TableHead>{t("nodal.reactance")}</TableHead>
                  <TableHead>{t("nodal.rating")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {network.branches.map((branch) => (
                  <TableRow key={branch.name}>
                    <TableCell className="font-medium">{branch.name}</TableCell>
                    <TableCell>{branch.from_zone} → {branch.to_zone}</TableCell>
                    <TableCell>{branch.reactance}</TableCell>
                    <TableCell>{branch.rating}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}