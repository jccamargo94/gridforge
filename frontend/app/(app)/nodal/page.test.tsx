import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { I18nProvider } from "@/lib/i18n-context";
import { listRuns } from "@/lib/api-client";
import Page from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/nodal",
}));
vi.mock("@/lib/api-client", () => ({ listRuns: vi.fn() }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ session: null, loading: false, signOut: vi.fn() }),
}));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <I18nProvider>{children}</I18nProvider>
  </QueryClientProvider>
);

describe("Nodal list page", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.mocked(listRuns).mockResolvedValue([
      {
        run_id: "run-nodal-1", status: "done", dispatch_date: "2024-04-18",
        level: "lmp", scenario_id: null, created_at: "2024-04-18T12:00:00Z",
        started_at: null, finished_at: null, error: null,
        nodal: { network_name: "three_zone", zones: 3, generators: 3, branches: 2 },
      },
      {
        run_id: "run-classic-1", status: "done", dispatch_date: "2024-04-18",
        level: "preideal", scenario_id: null, created_at: "2024-04-18T11:00:00Z",
        started_at: null, finished_at: null, error: null, nodal: null,
      },
    ]);
  });

  it("lists only lmp runs", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("run-nodal-1")).toBeInTheDocument());
    expect(screen.queryByText("run-classic-1")).not.toBeInTheDocument();
  });

  it("shows network topology chips", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("three_zone")).toBeInTheDocument());
    expect(screen.getByText(/3 zonas/i)).toBeInTheDocument();
    expect(screen.getByText(/3 generadores/i)).toBeInTheDocument();
  });

  it("links done nodal runs to the dashboard", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Analisis nodal/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Analisis nodal/i })).toHaveAttribute(
      "href", "/runs/run-nodal-1/nodal",
    );
  });

  it("shows an empty state when there are no lmp runs", async () => {
    vi.mocked(listRuns).mockResolvedValue([]);
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/No hay corridas nodales aun/i)).toBeInTheDocument());
  });
});