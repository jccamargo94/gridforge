import { describe, expect, it } from "vitest";
import {
  clampWindow,
  fullWindow,
  isDragGesture,
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

describe("clampWindow", () => {
  it("normalizes an inverted range", () => {
    expect(clampWindow({ start: 8, end: 3 }, TOTAL, MIN)).toEqual({ start: 3, end: 8 });
  });

  it("clamps indexes to the data bounds", () => {
    expect(clampWindow({ start: -5, end: 99 }, TOTAL, MIN)).toEqual({ start: 0, end: 23 });
  });

  it("enforces the minimum window around the selection", () => {
    expect(clampWindow({ start: 10, end: 11 }, TOTAL, MIN)).toEqual({ start: 10, end: 13 });
    expect(clampWindow({ start: 22, end: 23 }, TOTAL, MIN)).toEqual({ start: 20, end: 23 });
  });

  it("accepts any range when the data is smaller than the minimum", () => {
    expect(clampWindow({ start: 0, end: 2 }, 3, MIN)).toEqual({ start: 0, end: 2 });
  });

  it("handles empty data", () => {
    expect(clampWindow({ start: 0, end: 0 }, 0, MIN)).toEqual({ start: 0, end: 0 });
  });
});

describe("isDragGesture", () => {
  it("is false without a press origin", () => {
    expect(isDragGesture(null, { x: 100, y: 100 })).toBe(false);
  });

  it("is false for a click that barely moves", () => {
    expect(isDragGesture({ x: 100, y: 100 }, { x: 102, y: 101 })).toBe(false);
  });

  it("is true when the pointer moved past the threshold", () => {
    expect(isDragGesture({ x: 100, y: 100 }, { x: 140, y: 100 })).toBe(true);
  });

  it("honors a custom threshold", () => {
    expect(isDragGesture({ x: 100, y: 100 }, { x: 106, y: 100 }, 5)).toBe(true);
    expect(isDragGesture({ x: 100, y: 100 }, { x: 104, y: 100 }, 5)).toBe(false);
  });
});
