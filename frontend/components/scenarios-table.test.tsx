import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { ScenariosTable } from "./scenarios-table";
import type { Scenario } from "@/lib/types";

const scenarios: Scenario[] = [
  {
    id: "scn-1",
    mode: "arbitrage",
    penetration_level: "baseline",
    units: [
      {
        name: "bess-1",
        mwh_nom: 10,
        hours_to_deplete: 4,
        initial_soc: 0.5,
        min_soc: 0.1,
        max_soc: 0.9,
        efficiency: 0.9,
        charge_bid: 50,
        discharge_bid: 200,
      },
    ],
    created_at: "2024-04-18T05:00:00Z",
  },
];

function renderTable(scenarios: Scenario[]) {
  return render(
    <I18nProvider>
      <ScenariosTable scenarios={scenarios} />
    </I18nProvider>
  );
}

describe("ScenariosTable", () => {
  it("renders one row per scenario with mode/penetration/unit count", () => {
    renderTable(scenarios);
    expect(screen.getByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("arbitrage")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("renders an empty state with no scenarios", () => {
    renderTable([]);
    expect(screen.getByText(/sin escenarios/i)).toBeInTheDocument();
  });
});
