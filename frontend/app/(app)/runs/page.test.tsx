import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { listRuns } from "@/lib/api-client";
import type { RunSummary } from "@/lib/types";
import Page from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api-client", () => ({
  listRuns: vi.fn(),
  createRun: vi.fn(),
  listScenarios: vi.fn().mockResolvedValue([]),
  getTopologyNetwork: vi.fn(),
  scrapeTopology: vi.fn(),
}));

function makeRun(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_id: "run-manual",
    status: "done",
    dispatch_date: "2024-04-18",
    level: "preideal",
    scenario_id: null,
    visibility: "private",
    input_grade: null,
    created_at: "2024-04-18T05:00:00Z",
    started_at: "2024-04-18T05:00:00Z",
    finished_at: "2024-04-18T05:04:12Z",
    error: null,
    nodal: null,
    ...overrides,
  };
}

const MANUAL = makeRun({});
const DAILY_PUBLIC = makeRun({
  run_id: "run-daily",
  dispatch_date: "2024-04-19",
  level: "ideal",
  visibility: "public",
  input_grade: "settled",
});

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderPage() {
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <Page />
      </I18nProvider>
    </QueryClientProvider>
  );
}

function statValues(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll(".tabular-nums")).map(
    (el) => el.textContent ?? ""
  );
}

describe("Runs page manual-only filter", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("shows only manual runs in the table", async () => {
    vi.mocked(listRuns).mockResolvedValue([MANUAL, DAILY_PUBLIC]);

    renderPage();

    await waitFor(() => expect(screen.getByText("2024-04-18")).toBeInTheDocument());
    expect(screen.queryByText("2024-04-19")).not.toBeInTheDocument();
  });

  it("counts only manual runs in every stat", async () => {
    vi.mocked(listRuns).mockResolvedValue([MANUAL, DAILY_PUBLIC]);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("2024-04-18")).toBeInTheDocument());
    // total, pending, running, done, failed — the public daily run is excluded
    expect(statValues(container)).toEqual(["1", "0", "0", "1", "0"]);
  });

  it("shows the empty state when every run is a public daily run", async () => {
    vi.mocked(listRuns).mockResolvedValue([DAILY_PUBLIC]);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/sin ejecuciones todavia/i)).toBeInTheDocument()
    );
  });
});
