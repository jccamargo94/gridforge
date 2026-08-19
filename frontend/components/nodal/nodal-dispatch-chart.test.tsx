import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalDispatchRow } from "@/lib/types";
import { NodalDispatchChart } from "./nodal-dispatch-chart";

const ROWS: NodalDispatchRow[] = [
  { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 },
  { generator: "G_S", zone: "sur", fuel: "coal", hour: 0, dispatch_mw: 40 },
];

describe("NodalDispatchChart", () => {
  it("renders a stacked area per generator", () => {
    const { container } = render(
      <I18nProvider><NodalDispatchChart rows={ROWS} /></I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-area")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><NodalDispatchChart rows={[]} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de despacho nodal/i)).toBeInTheDocument();
  });
});