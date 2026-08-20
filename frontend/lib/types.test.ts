import { describe, expect, it } from "vitest";
import type { DispatchLevel, LmpRow, NodalDispatchRow, NodalResult, RunSummary } from "./types";

describe("nodal types", () => {
  it("accepts lmp dispatch level", () => {
    const level: DispatchLevel = "lmp";
    expect(level).toBe("lmp");
  });

  it("shapes RunSummary with nodal summary", () => {
    const summary: RunSummary = {
      run_id: "r1", status: "done", dispatch_date: "2024-04-18", level: "lmp",
      scenario_id: null, created_at: "2024-04-18T00:00:00Z", started_at: null,
      finished_at: null, error: null,
      nodal: { network_name: "three_zone", zones: 3, generators: 3, branches: 2 },
    };
    expect(summary.nodal?.zones).toBe(3);
  });

  it("shapes a full nodal result", () => {
    const result: NodalResult = {
      metrics: { total_cost: 100 },
      redistribution: [{ zone: "norte", load_payment_a: 1, load_payment_b: 2, delta: 1 }],
      gen_revenue_by_zone: [{ zone: "norte", fuel: "hydro", revenue_a: 1, revenue_b: 2, delta: 1 }],
      network: {
        name: "three_zone", baseMVA: 100, reference_zone: "norte",
        zones: [{ name: "norte", base_kv: 230 }],
        generators: [
          { name: "G_N", zone: "norte", p_min: 0, p_max: 500, marginal_cost: 20,
            no_load_cost: 0, fuel: "hydro", min_up_time: 1, min_down_time: 1,
            initial_status: 1, ramp_rate: null },
        ],
        branches: [{ name: "NC", from_zone: "norte", to_zone: "centro", reactance: 0.1, rating: 120 }],
        loads: [], demand_shares: { norte: 1 },
      },
      price_series: null,
      artifacts: { lmp: true, dispatch: true, branch_flows: true, settlement_status_quo: true, settlement_lmp: true, comparison: true, summary: true },
    };
    expect(result.network.zones[0].name).toBe("norte");
  });

  it("shapes LMP and nodal dispatch rows", () => {
    const lmp: LmpRow = { timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20, lmp_avg: 20, lmp_congestion: 0 };
    const row: NodalDispatchRow = { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 };
    expect(lmp.bus).toBe("norte");
    expect(row.dispatch_mw).toBe(100);
  });
});