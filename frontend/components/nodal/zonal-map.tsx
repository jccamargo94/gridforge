"use client";

import { useMemo } from "react";
import { useT } from "@/lib/i18n-context";
import { computeZoneLayout, lmpColor } from "@/lib/nodal-layout";
import { zoneLmpAtHour } from "@/lib/nodal-chart-data";
import type { LmpRow, NodalBranch, NodalBusLoad, NodalGenerator, NodalZone } from "@/lib/types";

interface ZonalMapProps {
  zones: NodalZone[];
  branches: NodalBranch[];
  generators: NodalGenerator[];
  lmpRows: LmpRow[];
  loads: NodalBusLoad[];
  hour: number;
}

export function ZonalMap({ zones, branches, generators, lmpRows, loads, hour }: ZonalMapProps) {
  const t = useT();
  const layout = useMemo(
    () => computeZoneLayout(
      zones.map((zone) => zone.name),
      branches.map((b) => ({ from: b.from_zone, to: b.to_zone })),
    ),
    [zones, branches],
  );
  const zoneValues = zones
    .map((zone) => zoneLmpAtHour(lmpRows, zone.name, hour))
    .filter((value): value is number => value !== null);
  const min = zoneValues.length ? Math.min(...zoneValues) : 0;
  const max = zoneValues.length ? Math.max(...zoneValues) : 0;
  const zoneInstalledCapacity = (zone: string) =>
    generators.filter((g) => g.zone === zone).reduce((sum, g) => sum + g.p_max, 0);
  const zoneLoad = (zone: string) => loads.find((l) => l.zone === zone)?.p_load[hour] ?? 0;

  return (
    <svg viewBox="0 0 600 400" className="h-auto w-full" role="img">
      {branches.map((branch) => {
        const from = layout[branch.from_zone];
        const to = layout[branch.to_zone];
        if (!from || !to) return null;
        return (
          <line key={branch.name} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            stroke="#3f3f46" strokeWidth={2} />
        );
      })}
      {zones.map((zone) => {
        const point = layout[zone.name];
        if (!point) return null;
        const lmp = zoneLmpAtHour(lmpRows, zone.name, hour);
        const fill = lmp === null ? "#71717a" : lmpColor(lmp, min, max);
        return (
          <g key={zone.name}>
            <title>{`${zone.name} - LMP: ${lmp ?? "-"} - ${t("nodal.load")}: ${zoneLoad(zone.name)} ${t("nodal.unitMw")} - ${t("nodal.installedCapacity")}: ${zoneInstalledCapacity(zone.name)} ${t("nodal.unitMw")}`}</title>
            <circle cx={point.x} cy={point.y} r={30} fill={fill} stroke="#18181b" strokeWidth={2} />
            <text x={point.x} y={point.y + 4} textAnchor="middle" fill="#fafafa" fontSize={13} fontWeight={600}>
              {zone.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}