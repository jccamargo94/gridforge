import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
});
