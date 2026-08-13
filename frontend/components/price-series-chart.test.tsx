import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "@/lib/i18n-context";
import { PriceSeriesChart } from "./price-series-chart";
import type { PricePoint } from "@/lib/types";

function renderChart(points: PricePoint[] | null) {
  return render(
    <I18nProvider>
      <PriceSeriesChart points={points} />
    </I18nProvider>
  );
}

const TWO_POINTS: PricePoint[] = [
  { datetime: "2024-04-18 00:00:00", model_mpo: 100, xm_mpo: 105 },
  { datetime: "2024-04-18 01:00:00", model_mpo: 110, xm_mpo: 108 },
];

describe("PriceSeriesChart", () => {
  it("renders a chart when there are price points", () => {
    const points: PricePoint[] = [
      { datetime: "2024-04-18 00:00:00", model_mpo: 100, xm_mpo: 105 },
      { datetime: "2024-04-18 01:00:00", model_mpo: 110, xm_mpo: 108 },
    ];

    const { container } = renderChart(points);

    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
  });

  it("shows an empty-state message instead of a chart when points are null", () => {
    renderChart(null);

    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });

  it("shows an empty-state message instead of a chart when points are empty", () => {
    renderChart([]);

    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });

  it("hides a line when its legend entry is clicked and restores it on a second click", async () => {
    const user = userEvent.setup();
    const { container } = renderChart(TWO_POINTS);
    expect(container.querySelectorAll(".recharts-line").length).toBe(2);

    await user.click(screen.getByRole("button", { name: /modelo mpo/i }));

    expect(screen.getByRole("button", { name: /modelo mpo/i })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
    expect(container.querySelectorAll(".recharts-line").length).toBe(1);

    await user.click(screen.getByRole("button", { name: /modelo mpo/i }));
    expect(container.querySelectorAll(".recharts-line").length).toBe(2);
  });
});
