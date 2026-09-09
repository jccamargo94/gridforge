import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "@/lib/i18n-context";
import { useChartSeries } from "@/hooks/use-chart-series";
import type { ChartSeriesRow } from "@/lib/types";
import Page from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => "/",
}));
vi.mock("@/hooks/use-chart-series", () => ({
  useChartSeries: vi.fn(),
}));

const ROWS: ChartSeriesRow[] = [
  {
    date: "2024-04-18",
    bolsa_tx1: 200000,
    mpo_xm: 150000,
    ideal_settled: 1000,
    ideal_settled_run_id: "run-settled",
    ideal_provisional: null,
    ideal_provisional_run_id: null,
    preideal: null,
    preideal_run_id: null,
  },
];

function mockSeries(result: Partial<ReturnType<typeof useChartSeries>>) {
  vi.mocked(useChartSeries).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...result,
  } as ReturnType<typeof useChartSeries>);
}

function renderPage() {
  return render(
    <I18nProvider>
      <Page />
    </I18nProvider>
  );
}

describe("Home page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the title and fetches the default 30-day window", async () => {
    mockSeries({ data: ROWS });

    const { container } = renderPage();

    expect(screen.getByText("Precios del mercado")).toBeInTheDocument();
    expect(useChartSeries).toHaveBeenCalledWith(30);
    expect(screen.getByRole("button", { name: "30" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await waitFor(() =>
      expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy()
    );
  });

  it("refetches with the new window when the selector changes", async () => {
    const user = userEvent.setup();
    mockSeries({ data: ROWS });

    renderPage();

    await user.click(screen.getByRole("button", { name: "7" }));

    await waitFor(() => expect(useChartSeries).toHaveBeenCalledWith(7));
  });

  it("shows a loading state while the series loads", () => {
    mockSeries({ isLoading: true });

    renderPage();

    expect(screen.getByText(/cargando serie/i)).toBeInTheDocument();
  });

  it("shows an alert with retry when the series fails", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    mockSeries({ isError: true, refetch: refetch as never });

    renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent(/no se pudo cargar la serie/i);

    await user.click(screen.getByRole("button", { name: /reintentar/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
