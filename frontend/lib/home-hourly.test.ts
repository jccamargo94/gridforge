import { describe, expect, it } from "vitest";
import { buildHourlyPoints, hasHourlyData } from "./home-hourly";
import type { ChartSeriesRow } from "./types";

function makeRow(overrides: Partial<ChartSeriesRow> = {}): ChartSeriesRow {
  return {
    date: "2024-04-18",
    bolsa_tx1: 200000,
    mpo_xm: 150000,
    ideal_settled: 1000,
    ideal_settled_run_id: "run-settled",
    ideal_provisional: null,
    ideal_provisional_run_id: null,
    preideal: null,
    preideal_run_id: null,
    bolsa_tx1_hourly: [null, 100, 200, ...Array.from({ length: 21 }, () => null)],
    mpo_xm_hourly: Array.from({ length: 24 }, (_, hour) => 1000 + hour),
    ideal_settled_hourly: Array.from({ length: 24 }, () => null),
    ideal_provisional_hourly: Array.from({ length: 24 }, () => null),
    preideal_hourly: Array.from({ length: 24 }, () => null),
    ...overrides,
  };
}

describe("buildHourlyPoints", () => {
  it("builds 24 points, one per hour, for the requested series", () => {
    const points = buildHourlyPoints(makeRow(), ["bolsa_tx1", "mpo_xm"]);

    expect(points).toHaveLength(24);
    expect(points.map((p) => p.hour)).toEqual(Array.from({ length: 24 }, (_, h) => h));
    expect(points[1]?.bolsa_tx1).toBe(100);
    expect(points[1]?.mpo_xm).toBe(1001);
  });

  it("keeps nulls as gaps instead of coercing them to zero", () => {
    const points = buildHourlyPoints(makeRow(), ["bolsa_tx1"]);

    expect(points[0]?.bolsa_tx1).toBeNull();
    expect(points[3]?.bolsa_tx1).toBeNull();
    expect(points[3]?.bolsa_tx1).not.toBe(0);
  });

  it("only includes the requested series", () => {
    const points = buildHourlyPoints(makeRow(), ["mpo_xm"]);

    expect(points[0]).toHaveProperty("mpo_xm");
    expect(points[0]).not.toHaveProperty("bolsa_tx1");
  });

  it("pads missing or short hourly arrays with nulls", () => {
    const row = makeRow({
      bolsa_tx1_hourly: [50],
      mpo_xm_hourly: [],
    });
    const points = buildHourlyPoints(row, ["bolsa_tx1", "mpo_xm"]);

    expect(points[0]?.bolsa_tx1).toBe(50);
    expect(points[1]?.bolsa_tx1).toBeNull();
    expect(points[23]?.bolsa_tx1).toBeNull();
    expect(points.every((p) => p.mpo_xm === null)).toBe(true);
  });

  it("returns 24 empty points when no series is visible", () => {
    const points = buildHourlyPoints(makeRow(), []);

    expect(points).toHaveLength(24);
    expect(points.every((p) => Object.keys(p).length === 1)).toBe(true);
  });
});

describe("hasHourlyData", () => {
  it("is true when any visible series has a value", () => {
    const points = buildHourlyPoints(makeRow(), ["bolsa_tx1"]);
    expect(hasHourlyData(points, ["bolsa_tx1"])).toBe(true);
  });

  it("is false when every visible value is null", () => {
    const points = buildHourlyPoints(makeRow(), ["ideal_settled"]);
    expect(hasHourlyData(points, ["ideal_settled"])).toBe(false);
  });

  it("ignores series that are not visible", () => {
    const points = buildHourlyPoints(makeRow(), ["ideal_settled"]);
    expect(hasHourlyData(points, ["bolsa_tx1"])).toBe(false);
  });
});
