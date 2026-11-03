import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { MeritPositionView } from "./merit-position-view";
import type { MeritPositionResponse } from "@/lib/types";

const hour = (h: number) => ({
  hour: h,
  demand_mw: 500,
  n_priced: 5,
  clearing_price_cop_mwh: 300000,
  own:
    h === 0
      ? [{ resource: "TERMO1", gen_type: "TERMICA", price_cop_mwh: 300000, capacity_mw: 300, rank: 4, cum_ahead_mw: 500, in_merit: false }]
      : [],
  market_by_tech: [{ gen_type: "HIDRAULICA", n_resources: 3, capacity_mw: 500, avg_price_cop_mwh: 115000, in_merit_mw: 500 }],
});

const data: MeritPositionResponse = {
  date: "2026-03-10",
  unpriced_mw_avg: 0,
  hours: Array.from({ length: 24 }, (_, h) => hour(h)),
};

describe("MeritPositionView", () => {
  it("shows own rank and the technology aggregate", () => {
    render(
      <I18nProvider>
        <MeritPositionView data={data} />
      </I18nProvider>,
    );
    expect(screen.getByText("TERMO1", { selector: "td" })).toBeTruthy();
    expect(screen.getByText("HIDRAULICA")).toBeTruthy();
  });

  it("shows an empty state when no own resource has an offer", () => {
    const empty = { ...data, hours: data.hours.map((h) => ({ ...h, own: [] })) };
    render(
      <I18nProvider>
        <MeritPositionView data={empty} />
      </I18nProvider>,
    );
    expect(screen.queryByText("HIDRAULICA")).toBeNull();
  });
});
