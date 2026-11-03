import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { AvailabilityFindings } from "./availability-findings";
import type { AvailabilityCheckResponse } from "@/lib/types";

const base: AvailabilityCheckResponse = {
  params: { low_pct: 0.5, min_days: 3, over_tol: 0.02 },
  resources_in_dispo: 4,
  matched: 3,
  match_rate: 0.75,
  unmatched_resources: ["X"],
  ambiguous_paratec_names: 0,
  findings: [
    {
      resource: "TERMO1",
      capacity_mw: 100,
      issues: ["exceeds_capacity", "hour_pattern"],
      days_observed: 10,
      days_over_capacity: 2,
      max_ratio_to_capacity: 1.5,
      longest_low_run_days: 0,
      outage_days: 0,
      zero_hours: [2, 3],
    },
  ],
};

describe("AvailabilityFindings", () => {
  it("shows coverage and each finding with its alerts", () => {
    render(
      <I18nProvider>
        <AvailabilityFindings data={base} />
      </I18nProvider>,
    );
    expect(screen.getByText("TERMO1")).toBeTruthy();
    expect(screen.getByText(/3\/4/)).toBeTruthy();
    expect(screen.getByText("2, 3")).toBeTruthy();
  });
  it("shows the empty state", () => {
    render(
      <I18nProvider>
        <AvailabilityFindings data={{ ...base, findings: [] }} />
      </I18nProvider>,
    );
    expect(screen.queryByText("TERMO1")).toBeNull();
  });
});
