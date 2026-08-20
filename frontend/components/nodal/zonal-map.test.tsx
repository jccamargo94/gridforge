import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow, NodalBusLoad } from "@/lib/types";
import { ZonalMap } from "./zonal-map";

const ZONES = [
  { name: "norte", base_kv: 230 },
  { name: "centro", base_kv: 230 },
  { name: "sur", base_kv: 230 },
];
const BRANCHES = [
  { name: "NC", from_zone: "norte", to_zone: "centro", reactance: 0.1, rating: 120 },
  { name: "CS", from_zone: "centro", to_zone: "sur", reactance: 0.1, rating: 400 },
];
const GENERATORS = [
  { name: "G_N", zone: "norte", p_min: 0, p_max: 500, marginal_cost: 20,
    no_load_cost: 0, fuel: "hydro", min_up_time: 1, min_down_time: 1,
    initial_status: 1, ramp_rate: null },
];
const LMP_ROWS: LmpRow[] = [
  { timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20 },
  { timestamp: "2024-04-18 00:00", bus: "centro", lmp: 30 },
  { timestamp: "2024-04-18 00:00", bus: "sur", lmp: 40 },
  { timestamp: "2024-04-18 01:00", bus: "norte", lmp: 21 },
];
const LOADS: NodalBusLoad[] = [
  { zone: "norte", p_load: Array.from({ length: 24 }, (_, i) => 100 + i) },
  { zone: "centro", p_load: Array.from({ length: 24 }, (_, i) => 200 + i) },
  { zone: "sur", p_load: Array.from({ length: 24 }, (_, i) => 300 + i) },
];

describe("ZonalMap", () => {
  it("renders one node per zone and one edge per branch", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} loads={LOADS} hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelectorAll("circle")).toHaveLength(3);
    expect(container.querySelectorAll("line")).toHaveLength(2);
  });

  it("colors nodes by lmp at the selected hour", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} loads={LOADS} hour={0} />
      </I18nProvider>,
    );
    const fills = [...container.querySelectorAll("circle")].map((c) => c.getAttribute("fill"));
    expect(fills).toContain("rgb(37, 99, 235)");
    expect(fills).toContain("rgb(245, 158, 11)");
  });

  it("includes a tooltip title per zone", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} loads={LOADS} hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelector("title")?.textContent).toContain("norte");
  });

  it("shows zone load and installed capacity in the tooltip", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} loads={LOADS} hour={0} />
      </I18nProvider>,
    );
    const titles = [...container.querySelectorAll("title")].map((t) => t.textContent);
    const norte = titles.find((t) => t?.includes("norte"));
    expect(norte).toContain("Carga");
    expect(norte).toContain("100");
    expect(norte).toContain("Capacidad instalada");
    expect(norte).toContain("500");
  });
});