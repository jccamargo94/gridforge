import { describe, expect, it } from "vitest";
import { buildHeatmap } from "./marginal-heatmap";

const cells = [
  { gen_type: "TERMICA", zone: "Caribe", hour: 3, share: 0.25 },
  { gen_type: "TERMICA", zone: "Antioquia", hour: 3, share: 0.5 },
  { gen_type: "HIDRAULICA", zone: null, hour: 3, share: 0.25 },
];

describe("buildHeatmap", () => {
  it("sums shares per technology", () => {
    const rows = buildHeatmap(cells, "tech");
    expect(rows.map((r) => r.label)).toEqual(["HIDRAULICA", "TERMICA"]);
    expect(rows[1].hours[3]).toBeCloseTo(0.75);
    expect(rows[1].hours).toHaveLength(24);
  });
  it("groups by zone with a placeholder for unmapped resources", () => {
    const rows = buildHeatmap(cells, "zone");
    expect(rows.map((r) => r.label)).toEqual(["-", "Antioquia", "Caribe"]);
  });
});
