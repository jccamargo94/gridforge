import { describe, expect, it } from "vitest";
import { computeZoneLayout, lmpColor } from "./nodal-layout";

const THREE_ZONES = ["norte", "centro", "sur"];

function distance(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

describe("computeZoneLayout", () => {
  it("is deterministic for the same input", () => {
    const a = computeZoneLayout(THREE_ZONES);
    const b = computeZoneLayout(THREE_ZONES);
    expect(a).toEqual(b);
  });

  it("places one point per zone", () => {
    const { positions } = computeZoneLayout(THREE_ZONES);
    expect(Object.keys(positions).sort()).toEqual([...THREE_ZONES].sort());
  });

  it("keeps coordinates inside the returned canvas", () => {
    const { positions, width, height } = computeZoneLayout(THREE_ZONES);
    for (const p of Object.values(positions)) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(width);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(height);
    }
  });

  it("returns empty positions for empty zones", () => {
    expect(computeZoneLayout([]).positions).toEqual({});
  });

  it("never overlaps node circles for a small network (regression: keep prior look)", () => {
    const { positions, nodeRadius } = computeZoneLayout(THREE_ZONES);
    const pts = Object.values(positions);
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        expect(distance(pts[i], pts[j])).toBeGreaterThanOrEqual(2 * nodeRadius);
      }
    }
  });

  it("never overlaps node circles for a real-sized 18-zone network (regression: was a cluster of overlapping circles)", () => {
    const zones = Array.from({ length: 18 }, (_, i) => `SubArea ${i}`);
    const { positions, nodeRadius, width, height } = computeZoneLayout(zones);
    const pts = Object.values(positions);
    expect(pts).toHaveLength(18);
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        expect(distance(pts[i], pts[j])).toBeGreaterThanOrEqual(2 * nodeRadius - 0.01);
      }
    }
    // Canvas grew to fit -- the old fixed 600x400 canvas is exactly what caused the overlap.
    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
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
    expect(lmpColor(50, 0, 100)).toBe("rgb(141, 129, 123)");
  });
});
