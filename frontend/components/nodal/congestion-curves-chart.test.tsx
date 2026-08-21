import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow } from "@/lib/types";
import { CongestionCurvesChart } from "./congestion-curves-chart";

const ROWS: LmpRow[] = Array.from({ length: 24 }, (_, hour) => [
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "norte", lmp: 20 + hour, lmp_avg: 20 + hour, lmp_congestion: -20,
  },
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "sur", lmp: 30 + hour, lmp_avg: 20 + hour, lmp_congestion: 10,
  },
]).flat();

describe("CongestionCurvesChart", () => {
  it("renders one line per zone", () => {
    const { container } = render(
      <I18nProvider><CongestionCurvesChart rows={ROWS} hour={0} /></I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><CongestionCurvesChart rows={[]} hour={0} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });
});
