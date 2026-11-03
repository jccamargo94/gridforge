import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { OfferAuditTable } from "./offer-audit-table";
import type { OfferAuditResult } from "@/lib/types";

const results: OfferAuditResult[] = [
  {
    resource: "TERMO1",
    date: "2026-03-31",
    status: "ok",
    price_cop_mwh: 300000,
    price_source: "candidate",
    n_history: 30,
    flag: "alert",
    z: 4.2,
    band: { mean_cop_mwh: 100000, std_cop_mwh: 1000, p05_cop_mwh: 98000, p50_cop_mwh: 100000, p95_cop_mwh: 102000, min_cop_mwh: 97000, max_cop_mwh: 103000 },
    change_vs_last_pct: 200,
  },
  { resource: "TERMO2", date: "2026-03-31", status: "no_offer" },
  { resource: "NUEVA", date: "2026-03-31", status: "insufficient_history", price_cop_mwh: 1, price_source: "candidate", n_history: 2 },
];

describe("OfferAuditTable", () => {
  it("renders flags, z-score and the empty states", () => {
    render(
      <I18nProvider>
        <OfferAuditTable results={results} />
      </I18nProvider>,
    );
    expect(screen.getByText("4.20")).toBeTruthy();
    expect(screen.getByText("200%")).toBeTruthy();
    expect(screen.getByText("TERMO2")).toBeTruthy();
    expect(screen.getAllByRole("row").length).toBe(4);
  });
});
