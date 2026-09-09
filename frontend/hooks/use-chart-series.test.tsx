import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChartSeries } from "./use-chart-series";

vi.mock("@/lib/api-client", () => ({
  getChartSeries: vi.fn(),
}));

import { getChartSeries } from "@/lib/api-client";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ROWS = [
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

describe("useChartSeries", () => {
  it("fetches the series for the requested window", async () => {
    vi.mocked(getChartSeries).mockResolvedValue(ROWS as never);

    const { result } = renderHook(() => useChartSeries(30), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getChartSeries).toHaveBeenCalledWith(30);
    expect(result.current.data).toEqual(ROWS);
  });

  it("refetches with the new window when days change", async () => {
    vi.mocked(getChartSeries).mockResolvedValue(ROWS as never);

    const { result, rerender } = renderHook(({ days }) => useChartSeries(days), {
      wrapper,
      initialProps: { days: 30 },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getChartSeries).toHaveBeenCalledWith(30);

    rerender({ days: 7 });

    await waitFor(() => expect(getChartSeries).toHaveBeenCalledWith(7));
  });
});
