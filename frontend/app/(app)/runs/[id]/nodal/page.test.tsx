import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { I18nProvider } from "@/lib/i18n-context";
import { getRun, getRunNodalArtifact } from "@/lib/api-client";
import type { RunDetail } from "@/lib/types";
import Page from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "run-1" }),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/runs/run-1/nodal",
}));
vi.mock("@/lib/api-client", () => ({
  getRun: vi.fn(), getRunNodalArtifact: vi.fn(), listRuns: vi.fn(),
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
    price_series: null,
    artifacts: {
      lmp: true, dispatch: true, branch_flows: true, settlement_status_quo: true,
      settlement_lmp: true, comparison: true, summary: true,
    },
  },
};

const LMP_ROWS = Array.from({ length: 24 }, (_, hour) => [
  { timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`, bus: "norte", lmp: 20 + hour, lmp_avg: 20 + hour, lmp_congestion: 0 },
  { timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`, bus: "sur", lmp: 30 + hour, lmp_avg: 30 + hour, lmp_congestion: 0 },
]).flat();

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <I18nProvider>{children}</I18nProvider>
  </QueryClientProvider>
);

describe("Nodal dashboard page", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.mocked(getRun).mockResolvedValue(NODAL_RUN);
    vi.mocked(getRunNodalArtifact).mockImplementation((_id, artifact) => {
      if (artifact === "lmp") return Promise.resolve(LMP_ROWS);
      if (artifact === "dispatch")
        return Promise.resolve([
          { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 },
        ]);
      return Promise.resolve([{ timestamp: "2024-04-18 00:00", branch: "NC", flow_mw: 10 }]);
    });
  });

  it("renders the header and metric cards", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("run-1")).toBeInTheDocument());
    expect(screen.getByText(/Costo total/i)).toBeInTheDocument();
    expect(screen.getByText(/Delta pago demanda/i)).toBeInTheDocument();
    expect(screen.getByText(/Renta de congestion/i)).toBeInTheDocument();
  });

  it("renders the zonal map and network card", async () => {
    const { container } = render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Red utilizada/i)).toBeInTheDocument());
    expect(container.querySelector("svg")).toBeTruthy();
    expect(screen.getByText("three_zone")).toBeInTheDocument();
  });

  it("renders the price curves, dispatch and branch flows charts", async () => {
    const { container } = render(<Page />, { wrapper });
    await waitFor(() => {
      expect(container.querySelectorAll(".recharts-wrapper, svg").length).toBeGreaterThanOrEqual(3);
    });
  });

  it("shows the differential table and redistribution matrix", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Tabla de diferencial/i)).toBeInTheDocument());
    expect(screen.getByText(/Matriz de redistribucion/i)).toBeInTheDocument();
    expect(screen.getAllByText("norte").length).toBeGreaterThan(0);
  });

  it("changes the selected hour via the selector", async () => {
    render(<Page />, { wrapper });
    // Disambiguated from the DataTable rows-per-page selects (Network/
    // Differential tables each render their own <select>).
    await waitFor(() => expect(screen.getByLabelText("Hora")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Hora"), { target: { value: "3" } });
    expect(screen.getByLabelText("Hora")).toHaveValue("3");
  });

  it("renders the run level as a badge", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("run-1")).toBeInTheDocument());
    const badge = screen.getByText("lmp");
    expect(badge.className).toContain("bg-amber-500/10");
    expect(badge.className).toContain("border");
  });
});