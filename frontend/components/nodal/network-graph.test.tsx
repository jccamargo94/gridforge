import { describe, expect, it } from "vitest";
import type { NodalNetwork } from "@/lib/types";
import {
  ZONE_LAYOUT_SPACING,
  buildGraphElements,
  computeGraphLayout,
  truncateName,
} from "./network-graph";

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

describe("computeGraphLayout", () => {
  it("places a single zone exactly at the origin", () => {
    expect(computeGraphLayout(["unico"])).toEqual({ unico: { x: 0, y: 0 } });
  });

  it("keeps every pairwise center distance at least 180px for ring sizes 1..36", () => {
    for (let n = 1; n <= 36; n++) {
      const names = Array.from({ length: n }, (_, i) => `z${i}`);
      const layout = computeGraphLayout(names);
      const points = names.map((name) => layout[name]);

      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const distance = Math.hypot(
            points[i].x - points[j].x,
            points[i].y - points[j].y,
          );
          // Unique points AND readable separation (epsilon absorbs float noise
          // in 2*R*sin(pi/n) rounding back down just below the spacing).
          expect(distance).toBeGreaterThan(0);
          expect(distance).toBeGreaterThanOrEqual(ZONE_LAYOUT_SPACING - 1e-6);
        }
      }
    }
  });

  it("uses the radius floor for two zones (golden values)", () => {
    const layout = computeGraphLayout(["a", "b"]);

    expect(layout.a.x).toBeCloseTo(0, 6);
    expect(layout.a.y).toBeCloseTo(-180, 6);
    expect(layout.b.x).toBeCloseTo(0, 6);
    expect(layout.b.y).toBeCloseTo(180, 6);
  });

  it("uses the radius floor for three zones (golden values)", () => {
    const layout = computeGraphLayout(["a", "b", "c"]);
    const side = 180 * Math.cos(Math.PI / 6);

    expect(layout.a.x).toBeCloseTo(0, 6);
    expect(layout.a.y).toBeCloseTo(-180, 6);
    expect(layout.b.x).toBeCloseTo(side, 6);
    expect(layout.b.y).toBeCloseTo(90, 6);
    expect(layout.c.x).toBeCloseTo(-side, 6);
    expect(layout.c.y).toBeCloseTo(90, 6);
  });

  it("is fully deterministic across calls", () => {
    const names = ["a", "b", "c", "d"];

    expect(computeGraphLayout(names)).toEqual(computeGraphLayout(names));
  });

  it("starts at the top: the first zone sits at the minimum y with x ~ 0", () => {
    const layout = computeGraphLayout(["a", "b", "c", "d", "e"]);
    const ys = Object.values(layout).map((p) => p.y);

    expect(layout.a.x).toBeCloseTo(0, 9);
    expect(layout.a.y).toBeLessThan(0);
    expect(layout.a.y).toBe(Math.min(...ys));
  });

  it("keeps an 18-zone ring inside a large bounding box (overlap regression guard)", () => {
    // With ~18 zones the previous layout put adjacent centers only ~44px apart
    // while cards are ~200x110px, collapsing everything into one cluster. The
    // ring must instead span roughly +/-518px so cards never overlap.
    const names = Array.from({ length: 18 }, (_, i) => `z${i}`);
    const points = Object.values(computeGraphLayout(names));
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const width = Math.max(...xs) - Math.min(...xs);
    const height = Math.max(...ys) - Math.min(...ys);

    expect(width).toBeGreaterThanOrEqual(900);
    expect(width).toBeLessThanOrEqual(1200);
    expect(height).toBeGreaterThanOrEqual(900);
    expect(height).toBeLessThanOrEqual(1200);
  });
});

describe("truncateName", () => {
  it("passes short names through unchanged", () => {
    expect(truncateName("sur", 14)).toBe("sur");
  });

  it("passes a name of exactly max length through unchanged", () => {
    const exact = "exactly14chars";

    expect(truncateName(exact, 14)).toBe(exact);
    expect(truncateName(exact, 14).endsWith("\u2026")).toBe(false);
  });

  it("truncates longer names to at most max characters with an ellipsis", () => {
    const truncated = truncateName("costenosaDelCaribeColombiano", 14);

    expect(truncated.length).toBeLessThanOrEqual(14);
    expect(truncated.endsWith("\u2026")).toBe(true);
    expect(truncated.startsWith("costenosaDelC")).toBe(true);
  });

  it("appends the ellipsis if and only if the name was truncated", () => {
    for (const [name, max] of [
      ["sur", 14],
      ["norte", 3],
      ["costenosaDelCaribeColombiano", 14],
      ["ab", 2],
    ] as const) {
      const result = truncateName(name, max);

      expect(result.endsWith("\u2026")).toBe(name.length > max);
      expect(result.length).toBeLessThanOrEqual(max);
    }
  });
});

describe("buildGraphElements", () => {
  it("creates exactly one node per network zone (bijection)", () => {
    const { nodes } = buildGraphElements(fixture);

    expect(nodes.map((n) => n.id)).toEqual(fixture.zones.map((z) => z.name));
  });

  it("types every node as a collapsed pill by default", () => {
    const { nodes } = buildGraphElements(fixture);

    for (const node of nodes) {
      expect(node.type).toBe("zonePill");
      expect(node.data.zoneName).toBe(node.id);
    }
  });

  it("expands at most one zone into a card, keeping the rest as pills", () => {
    const { nodes } = buildGraphElements(fixture, "norte");
    const cards = nodes.filter((n) => n.type === "zoneCard");

    expect(cards).toHaveLength(1);
    expect(cards[0].id).toBe("norte");
    for (const node of nodes.filter((n) => n.type !== "zoneCard")) {
      expect(node.type).toBe("zonePill");
    }
  });

  it("carries isReference in both pill and card data", () => {
    const { nodes } = buildGraphElements(fixture, "norte");
    const byId = new Map(nodes.map((n) => [n.id, n]));

    expect(byId.get("norte")?.type).toBe("zoneCard");
    expect(byId.get("norte")?.data.isReference).toBe(true);
    expect(byId.get("sur")?.type).toBe("zonePill");
    expect(byId.get("sur")?.data.isReference).toBe(false);
  });

  it("applies name truncation only to pills, never to the expanded card", () => {
    const longZones: NodalNetwork = {
      ...fixture,
      zones: [
        { name: "costenosaDelCaribeColombiano", base_kv: 115 },
        { name: "sur", base_kv: 230 },
      ],
      reference_zone: "sur",
    };

    const collapsed = buildGraphElements(longZones).nodes;
    const pill = collapsed.find((n) => n.id === "costenosaDelCaribeColombiano");
    expect(pill?.type).toBe("zonePill");
    expect(pill?.data.displayName).toBeDefined();
    expect(pill?.data.displayName.length).toBeLessThanOrEqual(14);

    const expanded = buildGraphElements(longZones, "costenosaDelCaribeColombiano").nodes;
    const card = expanded.find((n) => n.id === "costenosaDelCaribeColombiano");
    expect(card?.type).toBe("zoneCard");
    expect(card?.data.displayName).toBeUndefined();
  });

  it("assigns identical positions regardless of which zone is expanded", () => {
    const collapsed = buildGraphElements(fixture).nodes;
    const expandedNorte = buildGraphElements(fixture, "norte").nodes;
    const expandedSur = buildGraphElements(fixture, "sur").nodes;

    for (const node of collapsed) {
      const nortePos = expandedNorte.find((n) => n.id === node.id)?.position;
      const surPos = expandedSur.find((n) => n.id === node.id)?.position;
      expect(nortePos).toEqual(node.position);
      expect(surPos).toEqual(node.position);
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
