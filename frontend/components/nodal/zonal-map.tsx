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
  const { positions, width, height, nodeRadius } = useMemo(
    () => computeZoneLayout(zones.map((zone) => zone.name)),
    [zones],
  );
  const zoneValues = zones
    .map((zone) => zoneLmpAtHour(lmpRows, zone.name, hour))
    .filter((value): value is number => value !== null);
  const min = zoneValues.length ? Math.min(...zoneValues) : 0;
  const max = zoneValues.length ? Math.max(...zoneValues) : 0;
  const zoneInstalledCapacity = (zone: string) =>
    generators.filter((g) => g.zone === zone).reduce((sum, g) => sum + g.p_max, 0);
  const zoneLoad = (zone: string) => loads.find((l) => l.zone === zone)?.p_load[hour] ?? 0;
  // Labels sit below each node rather than centered on it: at 18+ zones the
  // node circles shrink below what most zone names fit inside legibly.
  const fontSize = Math.max(9, Math.min(13, Math.round(nodeRadius * 0.5)));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img">
      {branches.map((branch) => {
        const from = positions[branch.from_zone];
        const to = positions[branch.to_zone];
        if (!from || !to) return null;
        return (
          <line key={branch.name} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            stroke="#3f3f46" strokeWidth={2} />
        );
      })}
      {zones.map((zone) => {
        const point = positions[zone.name];
        if (!point) return null;
        const lmp = zoneLmpAtHour(lmpRows, zone.name, hour);
        const fill = lmp === null ? "#71717a" : lmpColor(lmp, min, max);
        return (
          <g key={zone.name}>
            <title>{`${zone.name} - LMP: ${lmp ?? "-"} - ${t("nodal.load")}: ${zoneLoad(zone.name)} ${t("nodal.unitMw")} - ${t("nodal.installedCapacity")}: ${zoneInstalledCapacity(zone.name)} ${t("nodal.unitMw")}`}</title>
            <circle cx={point.x} cy={point.y} r={nodeRadius} fill={fill} stroke="#18181b" strokeWidth={2} />
            <text
              x={point.x}
              y={point.y + nodeRadius + fontSize + 2}
              textAnchor="middle"
              fill="currentColor"
              fontSize={fontSize}
              fontWeight={600}
            >
              {zone.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}