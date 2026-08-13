import { describe, expect, it } from "vitest";
import {
  fullWindow,
  isWindowFull,
  panRange,
  windowSpan,
  zoomRange,
} from "./chart-zoom";

const TOTAL = 24;
const MIN = 4;

describe("fullWindow / isWindowFull", () => {
  it("covers the whole data range", () => {
    expect(fullWindow(24)).toEqual({ start: 0, end: 23 });
    expect(isWindowFull(fullWindow(24), 24)).toBe(true);
  });

  it("handles empty and single-point data", () => {
    expect(fullWindow(0)).toEqual({ start: 0, end: 0 });
    expect(fullWindow(1)).toEqual({ start: 0, end: 0 });
  });
});

describe("zoomRange", () => {
  it("shrinks the window around the focus ratio when zooming in", () => {
    const zoomed = zoomRange({ start: 0, end: 23 }, 0.5, 0.8, TOTAL, MIN);
    expect(windowSpan(zoomed)).toBeLessThan(24);
    expect(zoomed.start).toBeGreaterThanOrEqual(0);
    expect(zoomed.end).toBeLessThanOrEqual(23);
  });

  it("does not shrink below the minimum window", () => {
    const zoomed = zoomRange({ start: 10, end: 13 }, 0.5, 0.5, TOTAL, MIN);
    expect(windowSpan(zoomed)).toBe(MIN);
  });

  it("grows back toward the full window when zooming out", () => {
    const zoomed = zoomRange({ start: 5, end: 14 }, 0.5, 2, TOTAL, MIN);
    expect(windowSpan(zoomed)).toBeGreaterThan(10);
    expect(zoomed.start).toBeGreaterThanOrEqual(0);
    expect(zoomed.end).toBeLessThanOrEqual(23);
  });

  it("stays within bounds when the focus ratio is at the edges", () => {
    const left = zoomRange({ start: 3, end: 21 }, 0, 0.8, TOTAL, MIN);
    expect(left.start).toBe(0);

    const right = zoomRange({ start: 3, end: 21 }, 1, 0.8, TOTAL, MIN);
    expect(right.end).toBe(23);
  });

  it("returns the same window when the span would not change", () => {
    const current = { start: 3, end: 21 };
    expect(zoomRange(current, 0.5, 1, TOTAL, MIN)).toEqual(current);
  });
});

describe("panRange", () => {
  it("moves the window by the given delta", () => {
    expect(panRange({ start: 5, end: 14 }, 3, TOTAL)).toEqual({ start: 8, end: 17 });
  });

  it("clamps to the start of the data", () => {
    expect(panRange({ start: 5, end: 14 }, -20, TOTAL)).toEqual({ start: 0, end: 9 });
  });

  it("clamps to the end of the data", () => {
    expect(panRange({ start: 5, end: 14 }, 20, TOTAL)).toEqual({ start: 14, end: 23 });
  });

  it("cannot move a full window", () => {
    expect(panRange(fullWindow(24), 5, TOTAL)).toEqual(fullWindow(24));
  });
});
