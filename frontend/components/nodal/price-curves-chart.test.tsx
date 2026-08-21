import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow } from "@/lib/types";
import { PriceCurvesChart } from "./price-curves-chart";

const ROWS: LmpRow[] = Array.from({ length: 24 }, (_, hour) => [
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "norte", lmp: 20 + hour, lmp_avg: 20 + hour, lmp_congestion: 0,
  },
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "sur", lmp: 30 + hour, lmp_avg: 20 + hour, lmp_congestion: 10,
  },
]).flat();

describe("PriceCurvesChart", () => {
  it("renders one line per zone plus the always-present weighted-average line", () => {
    const { container } = render(
      <I18nProvider>
        <PriceCurvesChart rows={ROWS} hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    // 2 zone lines (norte, sur) + 1 weighted-average (lmp_avg) line
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(3);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><PriceCurvesChart rows={[]} hour={0} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });
});
