import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "@/lib/i18n-context";
import type { ChartSeriesRow } from "@/lib/types";
import { HomeChart, HomeChartTooltip, bestRunId, handleChartClick } from "./home-chart";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

function makeRow(overrides: Partial<ChartSeriesRow>): ChartSeriesRow {
  return {
    date: "2024-04-18",
    bolsa_tx1: 200000,
    mpo_xm: 150000,
    ideal_settled: 1000,
    ideal_settled_run_id: "run-settled",
    ideal_provisional: 2000,
    ideal_provisional_run_id: "run-prov",
    preideal: 3000,
    preideal_run_id: "run-pre",
    ...overrides,
  };
}

function renderChart(rows: ChartSeriesRow[] | null) {
  return render(
    <I18nProvider>
      <HomeChart rows={rows} />
    </I18nProvider>
  );
}

afterEach(() => {
  push.mockReset();
  localStorage.clear();
});

describe("bestRunId", () => {
  it("prefers the settled ideal run over provisional and preideal", () => {
    expect(bestRunId(makeRow({}))).toBe("run-settled");
  });

  it("falls back to provisional, then preideal", () => {
    expect(
      bestRunId(makeRow({ ideal_settled_run_id: null }))
    ).toBe("run-prov");
    expect(
      bestRunId(makeRow({ ideal_settled_run_id: null, ideal_provisional_run_id: null }))
    ).toBe("run-pre");
  });

  it("returns null when the day has no runs", () => {
    expect(
      bestRunId(
        makeRow({
          ideal_settled_run_id: null,
          ideal_provisional_run_id: null,
          preideal_run_id: null,
        })
      )
    ).toBeNull();
  });
});

describe("handleChartClick", () => {
  const rows = [
    makeRow({ date: "2024-04-18" }),
    makeRow({
      date: "2024-04-19",
      ideal_settled_run_id: null,
      ideal_provisional_run_id: null,
      preideal_run_id: null,
    }),
  ];

  it("navigates to the best run of the clicked day", () => {
    handleChartClick(rows, "2024-04-18", push);
    expect(push).toHaveBeenCalledWith("/runs/run-settled");
  });

  it("does not navigate when the day has no runs", () => {
    handleChartClick(rows, "2024-04-19", push);
    expect(push).not.toHaveBeenCalled();
  });

  it("does not navigate without an active day", () => {
    handleChartClick(rows, undefined, push);
    expect(push).not.toHaveBeenCalled();
  });
});

describe("HomeChart", () => {
  it("renders five lines for a full window", async () => {
    const { container } = renderChart([makeRow({}), makeRow({ date: "2024-04-19" })]);
    await waitFor(() =>
      expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy()
    );
    expect(container.querySelectorAll(".recharts-line").length).toBe(5);
  });

  it("renders gaps for null values instead of coercing them to zero", async () => {
    const rows = [
      makeRow({ date: "2024-04-16" }),
      makeRow({
        date: "2024-04-17",
        bolsa_tx1: null,
        mpo_xm: null,
        ideal_settled: null,
        ideal_provisional: null,
        preideal: null,
      }),
      makeRow({ date: "2024-04-18" }),
    ];
    const { container } = renderChart(rows);
    await waitFor(() =>
      expect(container.querySelectorAll(".recharts-line-curve").length).toBe(5)
    );
    const curves = Array.from(
      container.querySelectorAll(".recharts-line-curve")
    );
    expect(curves.length).toBe(5);
    // A null in the middle of a line with connectNulls={false} splits its
    // path into segments (one "M" moveto per segment); a zero-coerced value
    // would render a single continuous path through zero instead.
    const multiSegment = curves.filter((curve) => {
      const d = curve.getAttribute("d") ?? "";
      return (d.match(/M/g) ?? []).length > 1;
    });
    expect(multiSegment.length).toBe(5);
  });

  it("renders a single continuous path when no values are null", async () => {
    const { container } = renderChart([makeRow({}), makeRow({ date: "2024-04-19" })]);
    await waitFor(() =>
      expect(container.querySelectorAll(".recharts-line-curve").length).toBe(5)
    );
    const curves = Array.from(container.querySelectorAll(".recharts-line-curve"));
    expect(curves.length).toBe(5);
    for (const curve of curves) {
      const d = curve.getAttribute("d") ?? "";
      expect((d.match(/M/g) ?? []).length).toBe(1);
    }
  });

  it("shows an empty state only when the whole window is null", () => {
    renderChart([
      makeRow({
        bolsa_tx1: null,
        mpo_xm: null,
        ideal_settled: null,
        ideal_provisional: null,
        preideal: null,
      }),
    ]);
    expect(screen.getByText(/sin datos de serie todavia/i)).toBeInTheDocument();
  });

  it("renders a partial chart plus caption when only trailing days are null", async () => {
    const { container } = renderChart([
      makeRow({ date: "2024-04-16" }),
      makeRow({
        date: "2024-04-17",
        bolsa_tx1: null,
        mpo_xm: null,
        ideal_settled: null,
        ideal_provisional: null,
        preideal: null,
      }),
    ]);
    await waitFor(() =>
      expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy()
    );
    expect(screen.queryByText(/sin datos de serie todavia/i)).not.toBeInTheDocument();
    expect(screen.getByText(/retraso/i)).toBeInTheDocument();
  });

  it("hides a line when its legend entry is clicked", async () => {
    const user = userEvent.setup();
    const { container } = renderChart([makeRow({}), makeRow({ date: "2024-04-19" })]);
    await waitFor(() =>
      expect(container.querySelectorAll(".recharts-line").length).toBe(5)
    );

    await user.click(screen.getByRole("button", { name: /bolsa real/i }));

    expect(screen.getByRole("button", { name: /bolsa real/i })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
    expect(container.querySelectorAll(".recharts-line").length).toBe(4);
  });

  it("renders English copy when the locale is en", async () => {
    localStorage.setItem("gridforge-lang", "en");
    renderChart([makeRow({}), makeRow({ date: "2024-04-19" })]);
    expect(await screen.findByRole("button", { name: /real bolsa/i })).toBeInTheDocument();
    expect(screen.getByText(/2-4 day lag/i)).toBeInTheDocument();
  });
});

describe("HomeChartTooltip", () => {
  it("lists only non-null series plus the date", () => {
    render(
      <I18nProvider>
        <HomeChartTooltip
          active
          label="2024-04-18"
          unit="COP/MWh"
          payload={[
            { name: "Bolsa real (TX1)", value: 200000, color: "#22c55e", dataKey: "bolsa_tx1" },
            { name: "MPO XM (iMAR)", value: null, color: "#f59e0b", dataKey: "mpo_xm" },
          ]}
        />
      </I18nProvider>
    );
    expect(screen.getByText("2024-04-18")).toBeInTheDocument();
    expect(screen.getByText("Bolsa real (TX1)")).toBeInTheDocument();
    expect(screen.getByText("200,000")).toBeInTheDocument();
    expect(screen.queryByText("MPO XM (iMAR)")).not.toBeInTheDocument();
  });

  it("renders nothing when inactive", () => {
    const { container } = render(
      <I18nProvider>
        <HomeChartTooltip active={false} label="2024-04-18" payload={[]} />
      </I18nProvider>
    );
    expect(container).toBeEmptyDOMElement();
  });
});
