import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { RunArtifacts } from "@/lib/types";
import { ArtifactDownloads } from "./artifact-downloads";

vi.mock("@/lib/api-client", () => ({
  downloadRunArtifact: vi.fn(),
}));

import { downloadRunArtifact } from "@/lib/api-client";

function renderDownloads(runId: string, artifacts: RunArtifacts) {
  return render(
    <I18nProvider>
      <ArtifactDownloads runId={runId} artifacts={artifacts} />
    </I18nProvider>
  );
}

function noArtifacts(): RunArtifacts {
  return { dispatch: false, prices: false, bess: false, marginal_plants: false };
}

beforeEach(() => {
  vi.mocked(downloadRunArtifact).mockReset();
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:mock-url"),
    revokeObjectURL: vi.fn(),
  });
});

describe("ArtifactDownloads", () => {
  it("shows an empty-state message when no artifacts are available", () => {
    renderDownloads("run-1", noArtifacts());

    expect(screen.getByText(/no hay artefactos disponibles/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders one button per available artifact and none for unavailable ones", () => {
    renderDownloads("run-1", {
      dispatch: true,
      prices: true,
      bess: false,
      marginal_plants: false,
    });

    expect(screen.getByRole("button", { name: /despacho csv/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^precios csv$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /comparacion de precios csv/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /bess csv/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /plantas marginales csv/i })).not.toBeInTheDocument();
  });

  it("offers marginal plants and price comparison downloads when available", () => {
    renderDownloads("run-1", {
      dispatch: false,
      prices: true,
      bess: false,
      marginal_plants: true,
    });

    expect(screen.getByRole("button", { name: /plantas marginales csv/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /comparacion de precios csv/i })).toBeInTheDocument();
  });

  it("does not offer price comparison when prices are unavailable", () => {
    renderDownloads("run-1", {
      dispatch: true,
      prices: false,
      bess: false,
      marginal_plants: true,
    });

    expect(screen.queryByRole("button", { name: /comparacion de precios csv/i })).not.toBeInTheDocument();
  });

  it("clicking a download button fetches the blob and triggers a synthetic anchor click", async () => {
    const fakeBlob = new Blob(["csv,data"]);
    vi.mocked(downloadRunArtifact).mockResolvedValue(fakeBlob);
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderDownloads("run-1", {
      dispatch: true,
      prices: false,
      bess: false,
      marginal_plants: false,
    });
    fireEvent.click(screen.getByRole("button", { name: /despacho csv/i }));

    await vi.waitFor(() => {
      expect(downloadRunArtifact).toHaveBeenCalledWith("run-1", "dispatch");
    });
    expect(clickSpy).toHaveBeenCalled();

    clickSpy.mockRestore();
  });

  it("downloads marginal plants with the marginal_plants artifact key", async () => {
    const fakeBlob = new Blob(["csv,data"]);
    vi.mocked(downloadRunArtifact).mockResolvedValue(fakeBlob);
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderDownloads("run-1", {
      dispatch: false,
      prices: false,
      bess: false,
      marginal_plants: true,
    });
    fireEvent.click(screen.getByRole("button", { name: /plantas marginales csv/i }));

    await vi.waitFor(() => {
      expect(downloadRunArtifact).toHaveBeenCalledWith("run-1", "marginal_plants");
    });
    expect(clickSpy).toHaveBeenCalled();

    clickSpy.mockRestore();
  });

  it("shows an error message when the download fails", async () => {
    vi.mocked(downloadRunArtifact).mockRejectedValue(new Error("500"));

    renderDownloads("run-1", {
      dispatch: true,
      prices: false,
      bess: false,
      marginal_plants: false,
    });
    fireEvent.click(screen.getByRole("button", { name: /despacho csv/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudo descargar/i);
  });
});
