import { t as translate } from "./i18n";
import type { Lang } from "./i18n";
import type { DispatchRow } from "./types";

export interface HourlyDispatchPoint {
  hour: number;
  [series: string]: number;
}

const TOP_N = 6;

function hourOfDay(datetime: string): number {
  const timePart = datetime.split(" ")[1] ?? "00:00";
  return Number(timePart.split(":")[0]);
}

export function toHourlyDispatchSeries(rows: DispatchRow[], lang: Lang = "es"): {
  data: HourlyDispatchPoint[];
  seriesKeys: string[];
} {
  const otherLabel = translate(lang, "chart.others");

  const totals = new Map<string, number>();
  for (const row of rows) {
    totals.set(row.generador, (totals.get(row.generador) ?? 0) + row.dispatch);
  }

  const sortedByTotal = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  const topGeneradores = sortedByTotal.slice(0, TOP_N).map(([name]) => name);
  const topSet = new Set(topGeneradores);
  const hasOthers = totals.size > topGeneradores.length;

  const byHour = new Map<number, HourlyDispatchPoint>();
  for (const row of rows) {
    const hour = hourOfDay(row.datetime);
    const point = byHour.get(hour) ?? { hour };
    const key = topSet.has(row.generador) ? row.generador : otherLabel;
    point[key] = (point[key] ?? 0) + row.dispatch;
    byHour.set(hour, point);
  }

  const data = [...byHour.values()].sort((a, b) => a.hour - b.hour);
  const seriesKeys = hasOthers ? [...topGeneradores, otherLabel] : topGeneradores;
  return { data, seriesKeys };
}
