import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "@/lib/i18n-context";
import { DispatchChart } from "./dispatch-chart";
import type { DispatchRow } from "@/lib/types";

function renderChart(rows: DispatchRow[]) {
  return render(
    <I18nProvider>
      <DispatchChart rows={rows} />
    </I18nProvider>
  );
}

const TWO_GENERATORS: DispatchRow[] = [
  { generador: "A", datetime: "2024-04-18 00:00:00", dispatch: 10 },
  { generador: "A", datetime: "2024-04-18 01:00:00", dispatch: 20 },
  { generador: "B", datetime: "2024-04-18 00:00:00", dispatch: 5 },
  { generador: "B", datetime: "2024-04-18 01:00:00", dispatch: 8 },
];

describe("DispatchChart", () => {
  it("renders a chart when there are rows", () => {
    const rows: DispatchRow[] = [
      { generador: "A", datetime: "2024-04-18 00:00:00", dispatch: 10 },
      { generador: "A", datetime: "2024-04-18 01:00:00", dispatch: 20 },
    ];

    const { container } = renderChart(rows);

    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
  });

  it("shows an empty-state message instead of a chart when there are no rows", () => {
    renderChart([]);

    expect(screen.getByText(/no hay datos de despacho/i)).toBeInTheDocument();
  });

  it("renders a clickable legend entry per series", () => {
    renderChart(TWO_GENERATORS);

    const buttonA = screen.getByRole("button", { name: /^A$/ });
    const buttonB = screen.getByRole("button", { name: /^B$/ });

    expect(buttonA).toHaveAttribute("aria-pressed", "true");
    expect(buttonB).toHaveAttribute("aria-pressed", "true");
  });

  it("hides a series when its legend entry is clicked and restores it on a second click", async () => {
    const user = userEvent.setup();
    const { container } = renderChart(TWO_GENERATORS);
    expect(container.querySelectorAll(".recharts-area").length).toBe(2);

    await user.click(screen.getByRole("button", { name: /^A$/ }));

    expect(screen.getByRole("button", { name: /^A$/ })).toHaveAttribute("aria-pressed", "false");
    expect(container.querySelectorAll(".recharts-area").length).toBe(1);

    await user.click(screen.getByRole("button", { name: /^A$/ }));
    expect(container.querySelectorAll(".recharts-area").length).toBe(2);
  });
});
