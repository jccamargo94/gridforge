import { describe, expect, it } from "vitest";
import { formatHourLabel, formatNumber } from "./chart-format";

describe("formatNumber", () => {
  it("uses comma as thousands separator and rounds to whole numbers by default", () => {
    expect(formatNumber(1234567.89)).toBe("1,234,568");
  });

  it("keeps dot as decimal separator when decimals are requested", () => {
    expect(formatNumber(1234567.89, 2)).toBe("1,234,567.89");
    expect(formatNumber(0.5, 1)).toBe("0.5");
    expect(formatNumber(96.6, 2)).toBe("96.60");
  });

  it("keeps small values without separators", () => {
    expect(formatNumber(42)).toBe("42");
    expect(formatNumber(42, 2)).toBe("42.00");
  });

  it("formats negatives", () => {
    expect(formatNumber(-1537.5328, 4)).toBe("-1,537.5328");
  });

  it("returns an em dash for null, undefined and NaN", () => {
    expect(formatNumber(null)).toBe("\u2014");
    expect(formatNumber(undefined)).toBe("\u2014");
    expect(formatNumber(Number.NaN)).toBe("\u2014");
  });

  it("shows 0, not -0, for solver floating-point noise that rounds to zero", () => {
    // e.g. compare_settlements deltas that are analytically zero but land at
    // ~1e-10 due to LP solver tolerance.
    expect(formatNumber(-2.3283064365386963e-10)).toBe("0");
    expect(formatNumber(-0.00004, 2)).toBe("0.00");
    expect(formatNumber(-0)).toBe("0");
  });

  it("still shows real negative values that round to a nonzero value", () => {
    expect(formatNumber(-0.006, 2)).toBe("-0.01");
  });
});

describe("formatHourLabel", () => {
  it("pads single-digit hours with a leading zero", () => {
    expect(formatHourLabel(5)).toBe("05:00");
  });

  it("formats double-digit hours unchanged", () => {
    expect(formatHourLabel(23)).toBe("23:00");
  });

  it("clamps out-of-range values", () => {
    expect(formatHourLabel(-1)).toBe("00:00");
    expect(formatHourLabel(99)).toBe("23:00");
  });
});
