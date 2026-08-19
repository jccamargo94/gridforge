import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { RunsTable } from "./runs-table";
import type { RunSummary } from "@/lib/types";

const runs: RunSummary[] = [
  {
    run_id: "r1",
    status: "done",
    dispatch_date: "2024-04-18",
    level: "preideal",
    scenario_id: null,
    created_at: "2024-04-18T05:00:00Z",
    started_at: "2024-04-18T05:00:00Z",
    finished_at: "2024-04-18T05:04:12Z",
    error: null,
    nodal: null,
  },
];

function renderTable(runs: RunSummary[]) {
  return render(
    <I18nProvider>
      <RunsTable runs={runs} />
    </I18nProvider>
  );
}

describe("RunsTable", () => {
  it("renders one row per run with date/level/status/duration", () => {
    renderTable(runs);
    expect(screen.getByText("2024-04-18")).toBeInTheDocument();
    expect(screen.getByText("preideal")).toBeInTheDocument();
    expect(screen.getByText("Completado")).toBeInTheDocument();
    expect(screen.getByText("4m 12s")).toBeInTheDocument();
  });

  it("shows a dash for duration when the run has not finished", () => {
    const running: RunSummary[] = [
      { ...runs[0], run_id: "r2", status: "running", finished_at: null },
    ];
    renderTable(running);
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("renders an empty state with no runs", () => {
    renderTable([]);
    expect(screen.getByText(/sin ejecuciones todavia/i)).toBeInTheDocument();
  });
});
