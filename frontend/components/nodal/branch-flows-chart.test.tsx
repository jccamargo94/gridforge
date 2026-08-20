import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { BranchFlowRow } from "@/lib/types";
import { BranchFlowsChart } from "./branch-flows-chart";

const ROWS: BranchFlowRow[] = [
  { timestamp: "2024-04-18 00:00", branch: "NC", flow_mw: 10 },
  { timestamp: "2024-04-18 01:00", branch: "NC", flow_mw: 15 },
  { timestamp: "2024-04-18 00:00", branch: "CS", flow_mw: -4 },
];

describe("BranchFlowsChart", () => {
  it("renders one line per branch", () => {
    const { container } = render(
      <I18nProvider><BranchFlowsChart rows={ROWS} /></I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><BranchFlowsChart rows={[]} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de flujos de rama/i)).toBeInTheDocument();
  });
});