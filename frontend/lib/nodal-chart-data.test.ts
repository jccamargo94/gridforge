import { describe, expect, it } from "vitest";
import {
  aggregateGenRevenueByZoneFuel,
  hourFromTimestamp, toBranchFlowSeries, toNodalDispatchSeries,
  toPriceCurveData, zoneLmpAtHour,
} from "./nodal-chart-data";

describe("hourFromTimestamp", () => {
  it("parses H-hour timestamps", () => {
    expect(hourFromTimestamp("H00")).toBe(0);
    expect(hourFromTimestamp("H23")).toBe(23);
  });
  it("parses space-separated timestamps", () => {
    expect(hourFromTimestamp("2024-04-18 13:45")).toBe(13);
  });
  it("parses ISO timestamps", () => {
    expect(hourFromTimestamp("2024-04-18T07:00:00Z")).toBe(7);
  });
  it("returns 0 for unparseable input", () => {
    expect(hourFromTimestamp("nope")).toBe(0);
  });
});

describe("toPriceCurveData", () => {
  const rows = [
    { timestamp: "H00", bus: "norte", lmp: 20, lmp_avg: 20, lmp_congestion: 0 },
    { timestamp: "H01", bus: "norte", lmp: 21, lmp_avg: 21, lmp_congestion: 0 },
    { timestamp: "H00", bus: "sur", lmp: 30, lmp_avg: 30, lmp_congestion: 0 },
  ];
  it("builds 24 hourly points with one series per zone", () => {
    const { data, seriesKeys } = toPriceCurveData(rows);
    expect(data).toHaveLength(24);
    expect(seriesKeys.sort()).toEqual(["norte", "sur"]);
    expect(data[0]).toMatchObject({ hour: 0, norte: 20, sur: 30 });
    expect(data[1]).toMatchObject({ hour: 1, norte: 21 });
  });
});

describe("toNodalDispatchSeries", () => {
  const rows = [
    { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 },
    { generator: "G_N", zone: "norte", fuel: "hydro", hour: 1, dispatch_mw: 110 },
    { generator: "G_S", zone: "sur", fuel: "coal", hour: 0, dispatch_mw: 40 },
    { generator: "G_S", zone: "sur", fuel: "coal", hour: 1, dispatch_mw: 40 },
  ];
  it("stacks dispatch by generator per hour", () => {
    const { data, seriesKeys } = toNodalDispatchSeries(rows, "es");
    expect(data).toHaveLength(24);
    expect(seriesKeys.sort()).toEqual(["G_N", "G_S"]);
    expect(data[0]).toMatchObject({ hour: 0, G_N: 100, G_S: 40 });
    expect(data[1]).toMatchObject({ hour: 1, G_N: 110, G_S: 40 });
  });
});

describe("toBranchFlowSeries", () => {
  const rows = [
    { timestamp: "H00", branch: "NC", flow_mw: 10 },
    { timestamp: "H01", branch: "NC", flow_mw: 15 },
  ];
  it("builds hourly flows per branch", () => {
    const { data, seriesKeys } = toBranchFlowSeries(rows);
    expect(data).toHaveLength(24);
    expect(seriesKeys).toEqual(["NC"]);
    expect(data[0]).toMatchObject({ hour: 0, NC: 10 });
    expect(data[1]).toMatchObject({ hour: 1, NC: 15 });
  });
});

describe("zoneLmpAtHour", () => {
  const rows = [
    { timestamp: "H00", bus: "norte", lmp: 20, lmp_avg: 20, lmp_congestion: 0 },
    { timestamp: "H01", bus: "norte", lmp: 21, lmp_avg: 21, lmp_congestion: 0 },
  ];
  it("returns the lmp for a zone and hour", () => {
    expect(zoneLmpAtHour(rows, "norte", 0)).toBe(20);
    expect(zoneLmpAtHour(rows, "norte", 5)).toBeNull();
  });
});

describe("aggregateGenRevenueByZoneFuel", () => {
  it("sums revenue across generators sharing the same (zone, fuel)", () => {
    const rows = [
      { zone: "norte", fuel: "hydro", revenue_a: 100, revenue_b: 110, delta: 10 },
      { zone: "norte", fuel: "hydro", revenue_a: 50, revenue_b: 45, delta: -5 },
      { zone: "sur", fuel: "thermal", revenue_a: 200, revenue_b: 200, delta: 0 },
    ];
    const result = aggregateGenRevenueByZoneFuel(rows);
    expect(result).toHaveLength(2);
    const norteHydro = result.find((r) => r.zone === "norte" && r.fuel === "hydro");
    expect(norteHydro).toMatchObject({ revenue_a: 150, revenue_b: 155, delta: 5 });
  });

  it("returns an empty list for no rows", () => {
    expect(aggregateGenRevenueByZoneFuel([])).toEqual([]);
  });
});