import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalRedistributionRow } from "@/lib/types";
import { RedistributionMatrix } from "./redistribution-matrix";

const ROWS: NodalRedistributionRow[] = [
  { zone: "norte", load_payment_a: 100, load_payment_b: 120, delta: 20 },
  { zone: "centro", load_payment_a: 100, load_payment_b: 100, delta: 0 },
  { zone: "sur", load_payment_a: 100, load_payment_b: 80, delta: -20 },
];

describe("RedistributionMatrix", () => {
  it("renders one cell per zone", () => {
    render(<I18nProvider><RedistributionMatrix rows={ROWS} /></I18nProvider>);
    expect(screen.getByText("norte")).toBeInTheDocument();
    expect(screen.getByText("centro")).toBeInTheDocument();
    expect(screen.getByText("sur")).toBeInTheDocument();
    expect(screen.getByText(/Cambio neto en pago de la demanda/i)).toBeInTheDocument();
  });

  it("colors positive and negative deltas differently", () => {
    const { container } = render(<I18nProvider><RedistributionMatrix rows={ROWS} /></I18nProvider>);
    const cells = container.querySelectorAll("[data-delta]");
    expect(cells).toHaveLength(3);
    const north = [...cells].find((c) => c.getAttribute("data-zone") === "norte");
    const south = [...cells].find((c) => c.getAttribute("data-zone") === "sur");
    expect(north?.getAttribute("style")).not.toBe(south?.getAttribute("style"));
  });
});