import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { NodalNetworkEditor } from "./nodal-network-editor";
import type { NodalNetwork } from "@/lib/types";

function renderEditor() {
  const onChange = vi.fn();
  render(
    <I18nProvider>
      <NodalNetworkEditor value={null} onChange={onChange} />
    </I18nProvider>
  );
  return { onChange };
}

describe("NodalNetworkEditor", () => {
  it("loads the example network and calls onChange with a valid network", () => {
    const { onChange } = renderEditor();

    fireEvent.click(screen.getByRole("button", { name: /cargar red de ejemplo/i }));

    expect(screen.getByText(/red valida/i)).toBeInTheDocument();
    const called = onChange.mock.calls[0][0] as NodalNetwork;
    expect(called.name).toBe("three_zone");
    expect(called.baseMVA).toBe(100);
    expect(called.reference_zone).toBe("norte");
    expect(called.zones.map((z) => z.name)).toEqual(["norte", "centro", "sur"]);
    expect(called.generators).toHaveLength(3);
    expect(called.generators[0]).toMatchObject({
      name: "G_N",
      zone: "norte",
      p_max: 500,
      marginal_cost: 20,
      fuel: "hydro",
      initial_status: 1,
    });
    expect(called.branches[0]).toMatchObject({
      name: "NC",
      from_zone: "norte",
      to_zone: "centro",
      reactance: 0.1,
      rating: 400,
    });
    expect(called.loads).toHaveLength(3);
    expect(called.loads[0]).toMatchObject({ zone: "norte" });
    expect(called.loads[0].p_load).toHaveLength(24);
  });

  it("shows an error when the JSON does not parse", () => {
    const { onChange } = renderEditor();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "esto no es json" } });

    expect(screen.getByText(/red invalida/i)).toBeInTheDocument();
    expect(screen.getByText(/json invalido/i)).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("shows an error when the reference zone does not exist in zones", () => {
    const { onChange } = renderEditor();
    const badReference = {
      name: "two_zone",
      baseMVA: 100,
      reference_zone: "oeste",
      zones: [{ name: "norte", base_kv: 230 }, { name: "sur", base_kv: 230 }],
      generators: [],
      branches: [],
      loads: [],
      demand_shares: {},
    };

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: JSON.stringify(badReference) },
    });

    expect(screen.getByText(/zona de referencia no existe/i)).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("shows an error when a load has fewer than 24 p_load values", () => {
    const { onChange } = renderEditor();
    const shortLoad = {
      name: "one_zone",
      baseMVA: 100,
      reference_zone: "norte",
      zones: [{ name: "norte", base_kv: 230 }],
      generators: [],
      branches: [],
      loads: [{ zone: "norte", p_load: [100, 200] }],
      demand_shares: {},
    };

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: JSON.stringify(shortLoad) },
    });

    expect(screen.getByText(/exactamente 24 numeros/i)).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
