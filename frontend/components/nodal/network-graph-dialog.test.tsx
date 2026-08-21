import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalNetwork } from "@/lib/types";
import { NetworkGraphDialog } from "./network-graph-dialog";

function makeLoad(zone: string, peak: number): NodalNetwork["loads"][number] {
  const p_load = Array.from({ length: 24 }, (_, h) => (h === 18 ? peak : peak / 2));
  return { zone, p_load };
}

const fixture: NodalNetwork = {
  name: "test_network",
  baseMVA: 100,
  reference_zone: "norte",
  zones: [
    { name: "norte", base_kv: 230 },
    { name: "sur", base_kv: 230 },
  ],
  generators: [
    {
      name: "G_N1", zone: "norte", p_min: 0, p_max: 150, marginal_cost: 12,
      no_load_cost: 0, fuel: "hydro", min_up_time: 0, min_down_time: 0,
      initial_status: 1, ramp_rate: null,
    },
    {
      name: "G_S1", zone: "sur", p_min: 0, p_max: 50, marginal_cost: 40,
      no_load_cost: 0, fuel: "coal", min_up_time: 0, min_down_time: 0,
      initial_status: 1, ramp_rate: null,
    },
  ],
  branches: [
    { name: "NS1", from_zone: "norte", to_zone: "sur", reactance: 0.2, rating: 300 },
  ],
  loads: [makeLoad("norte", 90), makeLoad("sur", 40)],
  demand_shares: {},
};

function renderDialog(network: NodalNetwork | null) {
  return render(
    <I18nProvider>
      <NetworkGraphDialog network={network} />
    </I18nProvider>,
  );
}

describe("NetworkGraphDialog", () => {
  it("disables the trigger when the network is null", () => {
    renderDialog(null);

    expect(screen.getByRole("button", { name: /ver grafo/i })).toBeDisabled();
  });

  it("enables the trigger when a valid network is provided", () => {
    renderDialog(fixture);

    expect(screen.getByRole("button", { name: /ver grafo/i })).toBeEnabled();
  });

  it("opens the graph inside the dialog when the trigger is clicked", async () => {
    renderDialog(fixture);

    fireEvent.click(screen.getByRole("button", { name: /ver grafo/i }));

    const title = await screen.findByRole("heading", { name: /grafo de la red/i }, { timeout: 15000 });
    expect(title).toBeInTheDocument();
    expect(await screen.findByText("norte", {}, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.getByText("sur")).toBeInTheDocument();
  });

  it("shows a zone detail panel with generators and branches when a zone is clicked", async () => {
    renderDialog(fixture);

    fireEvent.click(screen.getByRole("button", { name: /ver grafo/i }));
    const zoneNode = await screen.findByText("norte", {}, { timeout: 15000 });
    fireEvent.click(zoneNode);

    // Generator info for the clicked zone.
    expect(await screen.findByText("G_N1", {}, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.getByText(/hydro/i)).toBeInTheDocument();
    // Branch connected to the clicked zone.
    expect(screen.getByText(/norte → sur/)).toBeInTheDocument();
    expect(screen.getByText(/0.2/)).toBeInTheDocument();
    // Zones without selection do not leak their generators into the panel.
    expect(screen.queryByText("G_S1")).not.toBeInTheDocument();
  });

  it("expands zones via an accessible pill button and formats numbers", async () => {
    renderDialog(fixture);

    fireEvent.click(screen.getByRole("button", { name: /ver grafo/i }));

    // Wait for the lazily imported graph to mount before querying the pills.
    await screen.findByText("norte", {}, { timeout: 15000 });

    // jsdom has no layout engine, so React Flow keeps node wrappers
    // visibility:hidden until it measures them; reveal them so role queries
    // (which respect the accessibility tree) can see the pills.
    document.querySelectorAll<HTMLElement>(".react-flow__node").forEach((n) => {
      n.style.visibility = "visible";
    });

    // The reference zone pill announces the expand action and its reference
    // role (not by color alone).
    const pill = screen.getByRole("button", { name: /ampliar zona: norte/i });
    expect(pill.getAttribute("aria-label")).toMatch(/zona de referencia/i);

    fireEvent.click(pill);

    // Card capacity formatted with one decimal; peak demand appears formatted
    // on both the expanded card and the detail panel.
    expect(await screen.findByText("150.0", {}, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.getAllByText("90.0").length).toBeGreaterThanOrEqual(1);
  }, 20000);

  it("shows empty-state messages for a zone without generators or branches", async () => {
    const sparse: NodalNetwork = {
      ...fixture,
      generators: [],
      branches: [],
    };
    renderDialog(sparse);

    fireEvent.click(screen.getByRole("button", { name: /ver grafo/i }));
    const zoneNode = await screen.findByText("norte", {}, { timeout: 15000 });
    fireEvent.click(zoneNode);

    expect(await screen.findByText(/sin generadores en esta zona/i, {}, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.getByText(/sin ramas conectadas a esta zona/i)).toBeInTheDocument();
  });
});
