import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChartTooltip } from "./chart-tooltip";

const payload = [
  { name: "Generador A", value: 1234567.89, color: "#f59e0b", dataKey: "A", graphicalItemId: "1" },
  { name: "Generador B", value: 500, color: "#3b82f6", dataKey: "B", graphicalItemId: "2" },
];

describe("ChartTooltip", () => {
  it("formats the hour label with HH:00", () => {
    render(<ChartTooltip active payload={payload} label={5} hourLabel="Hora" unit="MW" />);
    expect(screen.getByText("Hora:")).toBeInTheDocument();
    expect(screen.getByText("05:00")).toBeInTheDocument();
  });

  it("formats values with comma thousands separators, no decimals, and appends the unit", () => {
    render(<ChartTooltip active payload={payload} label={5} hourLabel="Hora" unit="MW" />);
    expect(screen.getByText("1,234,568")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getAllByText("MW")).toHaveLength(2);
  });

  it("uses the same dot-decimal / comma-thousands format regardless of language", () => {
    render(<ChartTooltip active payload={payload} label={5} hourLabel="Hour" unit="COP/MWh" />);
    expect(screen.getByText("1,234,568")).toBeInTheDocument();
    expect(screen.getAllByText("COP/MWh")).toHaveLength(2);
  });

  it("renders nothing when not active or without payload", () => {
    const { container } = render(
      <ChartTooltip active={false} payload={payload} label={5} />
    );
    expect(container).toBeEmptyDOMElement();

    const { container: c2 } = render(<ChartTooltip active payload={[]} label={5} />);
    expect(c2).toBeEmptyDOMElement();
  });
});
