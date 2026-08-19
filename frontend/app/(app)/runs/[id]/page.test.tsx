import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { I18nProvider } from "@/lib/i18n-context";
import { getRun, getRunDispatch, getRunLog, getRunMarginalPlants } from "@/lib/api-client";
import type { RunDetail } from "@/lib/types";
import Page from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "run-1" }),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/runs/run-1",
}));
vi.mock("@/lib/api-client", () => ({
  getRun: vi.fn(),
  getRunDispatch: vi.fn(),
  getRunMarginalPlants: vi.fn(),
  getRunLog: vi.fn(),
  downloadRunArtifact: vi.fn(),
}));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ session: null, loading: false, signOut: vi.fn() }),
}));

const NODAL_RUN: RunDetail = {
  run_id: "run-1", status: "done", dispatch_date: "2024-04-18", level: "lmp",
  scenario_id: null, created_at: "2024-04-18T12:00:00Z", started_at: null,
  finished_at: null, error: null,
  metrics: null,
  artifacts: { dispatch: false, prices: false, bess: false, marginal_plants: false },
  price_series: null,
  nodal: {
    metrics: {
      total_cost: 100000, load_payment_delta: 5000, gen_revenue_delta: -2000,
      congestion_rent_total: 7200, price_avg_norte: 90, price_avg_sur: 110,
      price_vol_norte: 5, price_vol_sur: 8,
    },
    redistribution: [
      { zone: "norte", load_payment_a: 100, load_payment_b: 120, delta: 20 },
      { zone: "sur", load_payment_a: 100, load_payment_b: 80, delta: -20 },
    ],
    gen_revenue_by_zone: [{ zone: "norte", fuel: "hydro", revenue_a: 50, revenue_b: 70, delta: 20 }],
    network: {
      name: "three_zone", baseMVA: 100, reference_zone: "norte",
      zones: [{ name: "norte", base_kv: 230 }, { name: "sur", base_kv: 230 }],
      generators: [
        { name: "G_N", zone: "norte", p_min: 0, p_max: 500, marginal_cost: 20,
          no_load_cost: 0, fuel: "hydro", min_up_time: 1, min_down_time: 1,
          initial_status: 1, ramp_rate: null },
      ],
      branches: [{ name: "NC", from_zone: "norte", to_zone: "sur", reactance: 0.1, rating: 120 }],
      loads: [], demand_shares: { norte: 0.5, sur: 0.5 },
    },
    artifacts: {
      lmp: true, dispatch: true, branch_flows: true, settlement_status_quo: true,
      settlement_lmp: true, comparison: true, summary: true,
    },
  },
};

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <I18nProvider>{children}</I18nProvider>
  </QueryClientProvider>
);

describe("Run detail page", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.mocked(getRun).mockResolvedValue(NODAL_RUN);
    vi.mocked(getRunDispatch).mockResolvedValue([]);
    vi.mocked(getRunMarginalPlants).mockResolvedValue([]);
    vi.mocked(getRunLog).mockResolvedValue("log line");
  });

  it("links to the nodal dashboard when the run has nodal data", async () => {
    render(<Page />, { wrapper });
    const link = await screen.findByRole("link", { name: /Abrir dashboard/i });
    expect(link).toHaveAttribute("href", "/runs/run-1/nodal");
  });

  it("does not link to the nodal dashboard when the run has no nodal data", async () => {
    vi.mocked(getRun).mockResolvedValue({ ...NODAL_RUN, nodal: null });
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("run-1")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: /Abrir dashboard/i })).toBeNull();
  });
});