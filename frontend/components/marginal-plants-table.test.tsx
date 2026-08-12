import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { MarginalPlantsTable } from "./marginal-plants-table";
import type { MarginalPlant } from "@/lib/types";

function renderTable(rows: MarginalPlant[]) {
  return render(
    <I18nProvider>
      <MarginalPlantsTable rows={rows} />
    </I18nProvider>
  );
}

describe("MarginalPlantsTable", () => {
  it("shows only marginal plants with generator, dispatch and pmax", () => {
    const rows: MarginalPlant[] = [
      { datetime: "2024-04-18 00:00:00", generador: "TERMO1", dispatch: 300, pmax: 400, is_marginal: true },
      { datetime: "2024-04-18 00:00:00", generador: "HIDRO1", dispatch: 0, pmax: 500, is_marginal: false },
      { datetime: "2024-04-18 01:00:00", generador: "TERMO2", dispatch: 150, pmax: 350, is_marginal: true },
    ];

    renderTable(rows);

    expect(screen.getByText("TERMO1")).toBeInTheDocument();
    expect(screen.getByText("TERMO2")).toBeInTheDocument();
    expect(screen.getByText("300.00")).toBeInTheDocument();
    expect(screen.getByText("150.00")).toBeInTheDocument();
    expect(screen.queryByText("HIDRO1")).not.toBeInTheDocument();
  });

  it("shows an empty-state message when no plants are marginal", () => {
    const rows: MarginalPlant[] = [
      { datetime: "2024-04-18 00:00:00", generador: "TERMO1", dispatch: 400, pmax: 400, is_marginal: false },
    ];

    renderTable(rows);

    expect(screen.getByText(/sin plantas que marginan/i)).toBeInTheDocument();
  });
});
