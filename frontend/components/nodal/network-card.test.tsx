import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalNetwork } from "@/lib/types";
import { NetworkCard } from "./network-card";

const NETWORK: NodalNetwork = {
  name: "three_zone", baseMVA: 100, reference_zone: "norte",
  zones: [{ name: "norte", base_kv: 230 }, { name: "centro", base_kv: 230 }],
  generators: [
    { name: "G_N", zone: "norte", p_min: 0, p_max: 500, marginal_cost: 20,
      no_load_cost: 0, fuel: "hydro", min_up_time: 1, min_down_time: 1,
      initial_status: 1, ramp_rate: null },
  ],
  branches: [{ name: "NC", from_zone: "norte", to_zone: "centro", reactance: 0.1, rating: 120 }],
  loads: [], demand_shares: { norte: 0.5, centro: 0.5 },
};

describe("NetworkCard", () => {
  it("renders the network name and reference zone", () => {
    render(<I18nProvider><NetworkCard network={NETWORK} /></I18nProvider>);
    expect(screen.getByText("three_zone")).toBeInTheDocument();
    expect(screen.getByText(/Zona de referencia/i)).toBeInTheDocument();
  });

  it("lists zones, generators and branches", () => {
    render(<I18nProvider><NetworkCard network={NETWORK} /></I18nProvider>);
    expect(screen.getByText("centro")).toBeInTheDocument();
    expect(screen.getByText("G_N")).toBeInTheDocument();
    expect(screen.getByText("NC")).toBeInTheDocument();
    expect(screen.getByText(/hydro/i)).toBeInTheDocument();
  });
});