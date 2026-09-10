import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "@/lib/i18n-context";
import type { ChartSeriesRow } from "@/lib/types";
import {
  HomeChart,
  HomeChartTooltip,
  bestRunId,
  nextSelectedDate,
  viewRunHref,
} from "./home-chart";
import { HomeHourlyPanel } from "./home-hourly-panel";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

function hourly(overrides: Record<number, number> = {}): (number | null)[] {
  return Array.from({ length: 24 }, (_, hour) => overrides[hour] ?? null);
}

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
    bolsa_tx1_hourly: hourly({ 0: 190000, 12: 210000 }),
    mpo_xm_hourly: hourly({ 0: 140000, 12: 160000 }),
    ideal_settled_hourly: hourly({ 0: 900, 12: 1100 }),
    ideal_provisional_hourly: hourly({ 0: 1900, 12: 2100 }),
    preideal_hourly: hourly({ 0: 2900, 12: 3100 }),
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

function renderPanel(overrides: Partial<Parameters<typeof HomeHourlyPanel>[0]> = {}) {
  const onClose = vi.fn();
  const onViewRun = vi.fn();
  const result = render(
    <I18nProvider>
      <HomeHourlyPanel
        row={makeRow({})}
        series={[
          { key: "bolsa_tx1", name: "Bolsa real (TX1)", color: "#22c55e" },
          { key: "mpo_xm", name: "MPO XM (iMAR)", color: "#f59e0b" },
        ]}
        canViewRun
        onClose={onClose}
        onViewRun={onViewRun}
        {...overrides}
      />
    </I18nProvider>
  );
  return { ...result, onClose, onViewRun };
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

describe("viewRunHref", () => {
  it("targets the best run of the day", () => {
    expect(viewRunHref(makeRow({}))).toBe("/runs/run-settled");
    expect(viewRunHref(makeRow({ ideal_settled_run_id: null }))).toBe("/runs/run-prov");
  });

  it("returns null when the day has no runs", () => {
    expect(
      viewRunHref(
        makeRow({
          ideal_settled_run_id: null,
          ideal_provisional_run_id: null,
          preideal_run_id: null,
        })
      )
    ).toBeNull();
  });
});

describe("nextSelectedDate", () => {
  it("selects the clicked day", () => {
    expect(nextSelectedDate(null, "2024-04-18")).toBe("2024-04-18");
  });

  it("moves the selection to another day", () => {
    expect(nextSelectedDate("2024-04-18", "2024-04-19")).toBe("2024-04-19");
  });

  it("closes the selection when the same day is clicked again", () => {
    expect(nextSelectedDate("2024-04-18", "2024-04-18")).toBeNull();
  });

  it("keeps the current selection on a click without an active day", () => {
    expect(nextSelectedDate(null, undefined)).toBeNull();
    expect(nextSelectedDate("2024-04-18", undefined)).toBe("2024-04-18");
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

  it("does not open the hourly panel before a day is clicked", async () => {
    renderChart([makeRow({}), makeRow({ date: "2024-04-19" })]);
    expect(screen.queryByRole("heading", { name: /detalle horario/i })).not.toBeInTheDocument();
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

describe("HomeHourlyPanel", () => {
  it("renders one line per visible series for the selected day", async () => {
    const { container } = renderPanel();

    expect(screen.getByRole("heading", { name: /detalle horario/i })).toBeInTheDocument();
    expect(screen.getByText("2024-04-18")).toBeInTheDocument();
    await waitFor(() =>
      expect(container.querySelectorAll(".recharts-line").length).toBe(2)
    );
  });

  it("navigates through the explicit view-run action", async () => {
    const user = userEvent.setup();
    const { onViewRun } = renderPanel();

    await user.click(screen.getByRole("button", { name: /ver run/i }));

    expect(onViewRun).toHaveBeenCalledTimes(1);
  });

  it("omits the view-run action when the day has no runs", () => {
    renderPanel({ canViewRun: false });

    expect(screen.queryByRole("button", { name: /ver run/i })).not.toBeInTheDocument();
  });

  it("closes through the close action", async () => {
    const user = userEvent.setup();
    const { onClose } = renderPanel();

    await user.click(screen.getByRole("button", { name: /cerrar/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows an empty message when every visible hour is null", () => {
    renderPanel({
      row: makeRow({
        bolsa_tx1_hourly: hourly(),
        mpo_xm_hourly: hourly(),
      }),
    });

    expect(screen.getByText(/sin detalle horario/i)).toBeInTheDocument();
  });
});
