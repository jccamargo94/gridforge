import type { BranchFlowRow, LmpRow, NodalDispatchRow } from "./types";
import { t, type Lang } from "./i18n";

export interface HourlyPoint { hour: number; [key: string]: number; }

export function hourFromTimestamp(timestamp: string): number {
  const h = timestamp.match(/^H(\d{2})$/);
  if (h) return Number(h[1]);
  const iso = timestamp.match(/T(\d{2})/);
  if (iso) return Number(iso[1]);
  const space = timestamp.split(" ");
  if (space.length > 1) return Number(space[1].split(":")[0] ?? 0);
  return 0;
}

export function toPriceCurveData(rows: LmpRow[]) {
  const byZone = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byZone.has(row.bus)) byZone.set(row.bus, new Map());
    byZone.get(row.bus)!.set(hourFromTimestamp(row.timestamp), row.lmp);
  }
  const seriesKeys = [...byZone.keys()];
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const point: HourlyPoint = { hour };
    for (const zone of seriesKeys) point[zone] = byZone.get(zone)?.get(hour) ?? 0;
    data.push(point);
  }
  return { data, seriesKeys };
}

export function toNodalDispatchSeries(rows: NodalDispatchRow[], lang: Lang = "es") {
  const byGen = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byGen.has(row.generator)) byGen.set(row.generator, new Map());
    const hours = byGen.get(row.generator)!;
    hours.set(row.hour, (hours.get(row.hour) ?? 0) + row.dispatch_mw);
  }
  const totals = [...byGen.entries()]
    .map(([gen, hours]) => [gen, [...hours.values()].reduce((a, b) => a + b, 0)] as const)
    .sort((a, b) => b[1] - a[1]);
  const top = totals.slice(0, 6).map(([gen]) => gen);
  const othersKey = t(lang, "chart.others");
  const useOthers = byGen.size > 6;
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const point: HourlyPoint = { hour };
    for (const gen of top) point[gen] = byGen.get(gen)?.get(hour) ?? 0;
    if (useOthers) {
      let others = 0;
      for (const [gen, hours] of byGen) {
        if (!top.includes(gen)) others += hours.get(hour) ?? 0;
      }
      point[othersKey] = others;
    }
    data.push(point);
  }
  const seriesKeys = useOthers ? [...top, othersKey] : top;
  return { data, seriesKeys };
}

export function toBranchFlowSeries(rows: BranchFlowRow[]) {
  const byBranch = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byBranch.has(row.branch)) byBranch.set(row.branch, new Map());
    byBranch.get(row.branch)!.set(hourFromTimestamp(row.timestamp), row.flow_mw);
  }
  const seriesKeys = [...byBranch.keys()];
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const point: HourlyPoint = { hour };
    for (const branch of seriesKeys) point[branch] = byBranch.get(branch)?.get(hour) ?? 0;
    data.push(point);
  }
  return { data, seriesKeys };
}

export function zoneLmpAtHour(rows: LmpRow[], zone: string, hour: number): number | null {
  const found = rows.find(
    (row) => row.bus === zone && hourFromTimestamp(row.timestamp) === hour,
  );
  return found ? found.lmp : null;
}