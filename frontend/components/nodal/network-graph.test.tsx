import { describe, expect, it } from "vitest";
import { computeZoneLayout } from "@/lib/nodal-layout";
import type { NodalNetwork } from "@/lib/types";
import { buildGraphElements } from "./network-graph";

function makeLoad(zone: string, peak: number): NodalNetwork["loads"][number] {
  const p_load = Array.from({ length: 24 }, (_, h) => (h === 18 ? peak : peak / 2));
  return { zone, p_load };
}

const fixture: NodalNetwork = {
  name: "test_network",
  baseMVA: 100,
  reference_zone: "norte",
  zones: [
    { name: "norte", base_kv: 230 },
    { name: "sur", base_kv: 230 },
  ],
  generators: [
    {
      name: "G_N1", zone: "norte", p_min: 0, p_max: 150, marginal_cost: 12,
      no_load_cost: 0, fuel: "hydro", min_up_time: 0, min_down_time: 0,
      initial_status: 1, ramp_rate: null,
    },
    {
      name: "G_N2", zone: "norte", p_min: 0, p_max: 100, marginal_cost: 30,
      no_load_cost: 0, fuel: "gas", min_up_time: 0, min_down_time: 0,
      initial_status: 1, ramp_rate: null,
    },
    {
      name: "G_S1", zone: "sur", p_min: 0, p_max: 50, marginal_cost: 40,
      no_load_cost: 0, fuel: "coal", min_up_time: 0, min_down_time: 0,
      initial_status: 1, ramp_rate: null,
    },
  ],
  branches: [
    { name: "NS1", from_zone: "norte", to_zone: "sur", reactance: 0.2, rating: 300 },
    { name: "NS2", from_zone: "norte", to_zone: "sur", reactance: 0.25, rating: 200 },
  ],
  loads: [makeLoad("norte", 90), makeLoad("sur", 40)],
  demand_shares: {},
};

describe("buildGraphElements", () => {
  it("creates one zone node per network zone with layout positions", () => {
    const { nodes } = buildGraphElements(fixture);

    expect(nodes).toHaveLength(2);
    const layout = computeZoneLayout(fixture.zones.map((z) => z.name));
    for (const node of nodes) {
      expect(node.position).toEqual(layout.positions[node.id]);
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
    }
  });

  it("sums installed capacity and counts generators per zone", () => {
    const { nodes } = buildGraphElements(fixture);
    const byId = new Map(nodes.map((n) => [n.id, n]));

    expect(byId.get("norte")?.data.installedCapacityMw).toBe(250);
    expect(byId.get("norte")?.data.generatorCount).toBe(2);
    expect(byId.get("sur")?.data.installedCapacityMw).toBe(50);
    expect(byId.get("sur")?.data.generatorCount).toBe(1);
  });

  it("computes peak demand as the max p_load across 24 hours per zone", () => {
    const { nodes } = buildGraphElements(fixture);
    const byId = new Map(nodes.map((n) => [n.id, n]));

    expect(byId.get("norte")?.data.peakDemandMw).toBe(90);
    expect(byId.get("sur")?.data.peakDemandMw).toBe(40);
  });

  it("flags only the reference zone node", () => {
    const { nodes } = buildGraphElements(fixture);
    const byId = new Map(nodes.map((n) => [n.id, n]));

    expect(byId.get("norte")?.data.isReference).toBe(true);
    expect(byId.get("sur")?.data.isReference).toBe(false);
  });

  it("types every node as a custom zone node carrying its zone name", () => {
    const { nodes } = buildGraphElements(fixture);

    for (const node of nodes) {
      expect(node.type).toBe("zone");
      expect(node.data.zoneName).toBe(node.id);
    }
  });

  it("maps each branch to an edge between its zones with reactance and rating data", () => {
    const { edges } = buildGraphElements(fixture);

    expect(edges).toHaveLength(2);
    const first = edges.find((e) => e.id === "NS1");
    expect(first?.source).toBe("norte");
    expect(first?.target).toBe("sur");
    expect(first?.data).toMatchObject({ branchName: "NS1", reactance: 0.2, rating: 300 });
    const second = edges.find((e) => e.id === "NS2");
    expect(second?.source).toBe("norte");
    expect(second?.target).toBe("sur");
    expect(second?.data).toMatchObject({ branchName: "NS2", reactance: 0.25, rating: 200 });
  });

  it("handles zones without generators or loads with zeroed aggregates", () => {
    const emptyZoneNetwork: NodalNetwork = {
      ...fixture,
      zones: [...fixture.zones, { name: "oriente", base_kv: 115 }],
      generators: fixture.generators,
      loads: fixture.loads,
    };

    const { nodes } = buildGraphElements(emptyZoneNetwork);
    const oriente = nodes.find((n) => n.id === "oriente");

    expect(oriente?.data).toMatchObject({
      installedCapacityMw: 0,
      peakDemandMw: 0,
      generatorCount: 0,
      isReference: false,
    });
  });
});
