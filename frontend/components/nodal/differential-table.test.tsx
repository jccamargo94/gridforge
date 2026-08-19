import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalGenRevenueRow, NodalRedistributionRow } from "@/lib/types";
import { DifferentialTable } from "./differential-table";

const REDISTRIBUTION: NodalRedistributionRow[] = [
  { zone: "norte", load_payment_a: 100, load_payment_b: 120, delta: 20 },
  { zone: "sur", load_payment_a: 100, load_payment_b: 80, delta: -20 },
];
const GEN_REVENUE: NodalGenRevenueRow[] = [
  { zone: "centro", fuel: "hydro", revenue_a: 50, revenue_b: 70, delta: 20 },
];

describe("DifferentialTable", () => {
  it("renders load payment deltas per zone", () => {
    render(<I18nProvider><DifferentialTable redistribution={REDISTRIBUTION} genRevenue={GEN_REVENUE} /></I18nProvider>);
    expect(screen.getByText("norte")).toBeInTheDocument();
    expect(screen.getByText("sur")).toBeInTheDocument();
    expect(screen.getAllByText(/Pago demanda A/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Delta/i).length).toBeGreaterThan(0);
  });

  it("renders generation revenue per zone and fuel", () => {
    render(<I18nProvider><DifferentialTable redistribution={REDISTRIBUTION} genRevenue={GEN_REVENUE} /></I18nProvider>);
    expect(screen.getByText("hydro")).toBeInTheDocument();
    expect(screen.getAllByText(/Ingreso generacion A/i).length).toBeGreaterThan(0);
  });

  it("renders duplicate (zone, fuel) rows without a key collision", () => {
    const duplicateGenRevenue: NodalGenRevenueRow[] = [
      ...GEN_REVENUE,
      { zone: "centro", fuel: "hydro", revenue_a: 60, revenue_b: 80, delta: 20 },
    ];
    render(<I18nProvider><DifferentialTable redistribution={REDISTRIBUTION} genRevenue={duplicateGenRevenue} /></I18nProvider>);
    expect(screen.getAllByText("hydro")).toHaveLength(2);
  });
});