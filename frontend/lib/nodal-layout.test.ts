import { describe, expect, it } from "vitest";
import { computeZoneLayout, lmpColor } from "./nodal-layout";

const THREE_ZONES = ["norte", "centro", "sur"];
const THREE_BRANCHES = [
  { from: "norte", to: "centro" },
  { from: "centro", to: "sur" },
];

describe("computeZoneLayout", () => {
  it("is deterministic for the same input", () => {
    const a = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    const b = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    expect(a).toEqual(b);
  });

  it("places one point per zone", () => {
    const layout = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    expect(Object.keys(layout).sort()).toEqual([...THREE_ZONES].sort());
  });

  it("keeps coordinates inside the canvas", () => {
    const layout = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    for (const p of Object.values(layout)) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(600);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(400);
    }
  });

  it("returns empty for empty zones", () => {
    expect(computeZoneLayout([], [])).toEqual({});
  });

  it("handles branches referencing unknown zones", () => {
    const layout = computeZoneLayout(["a"], [{ from: "a", to: "missing" }]);
    expect(layout.a).toBeDefined();
  });
});

describe("lmpColor", () => {
  it("returns neutral for degenerate range", () => {
    expect(lmpColor(50, 50, 50)).toBe("#71717a");
  });
  it("returns blue at the minimum", () => {
    expect(lmpColor(0, 0, 100)).toBe("rgb(37, 99, 235)");
  });
  it("returns amber at the maximum", () => {
    expect(lmpColor(100, 0, 100)).toBe("rgb(245, 158, 11)");
  });
  it("clamps out-of-range values", () => {
    expect(lmpColor(-50, 0, 100)).toBe("rgb(37, 99, 235)");
    expect(lmpColor(500, 0, 100)).toBe("rgb(245, 158, 11)");
  });
  it("interpolates midpoints", () => {
    expect(lmpColor(50, 0, 100)).toMatch(/^rgb\(/);
  });
});