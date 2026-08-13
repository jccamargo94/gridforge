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
