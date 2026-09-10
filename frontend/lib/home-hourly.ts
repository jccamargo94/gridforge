import type { ChartSeriesRow } from "./types";

export type HourlySeriesKey =
  | "bolsa_tx1"
  | "mpo_xm"
  | "ideal_settled"
  | "ideal_provisional"
  | "preideal";

type HourlyField =
  | "bolsa_tx1_hourly"
  | "mpo_xm_hourly"
  | "ideal_settled_hourly"
  | "ideal_provisional_hourly"
  | "preideal_hourly";

export const HOURS_PER_DAY = 24;

const HOURLY_FIELD: Record<HourlySeriesKey, HourlyField> = {
  bolsa_tx1: "bolsa_tx1_hourly",
  mpo_xm: "mpo_xm_hourly",
  ideal_settled: "ideal_settled_hourly",
  ideal_provisional: "ideal_provisional_hourly",
  preideal: "preideal_hourly",
};

export type HourlyPoint = { hour: number } & Partial<
  Record<HourlySeriesKey, number | null>
>;

/**
 * Row of the day + series visible in the legend -> 24 hourly points (0..23),
 * one key per series. Every missing or out-of-range value stays `null` so the
 * chart draws a gap instead of inventing a zero.
 */
export function buildHourlyPoints(
  row: ChartSeriesRow,
  seriesKeys: readonly HourlySeriesKey[]
): HourlyPoint[] {
  return Array.from({ length: HOURS_PER_DAY }, (_, hour) => {
    const point: HourlyPoint = { hour };
    for (const key of seriesKeys) {
      point[key] = row[HOURLY_FIELD[key]]?.[hour] ?? null;
    }
    return point;
  });
}

export function hasHourlyData(
  points: readonly HourlyPoint[],
  seriesKeys: readonly HourlySeriesKey[]
): boolean {
  return points.some((point) => seriesKeys.some((key) => point[key] != null));
}
