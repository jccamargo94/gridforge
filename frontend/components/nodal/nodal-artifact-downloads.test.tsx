import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { downloadNodalArtifact } from "@/lib/api-client";
import type { NodalArtifactName } from "@/lib/types";
import { NodalArtifactDownloads } from "./nodal-artifact-downloads";

vi.mock("@/lib/api-client", () => ({
  downloadNodalArtifact: vi.fn().mockResolvedValue(new Blob()),
}));

const ALL_ARTIFACTS = {
  lmp: true, dispatch: true, branch_flows: true, settlement_status_quo: true,
  settlement_lmp: true, comparison: true, summary: true,
} as Record<NodalArtifactName, boolean>;

beforeEach(() => {
  vi.mocked(downloadNodalArtifact).mockReset();
  vi.mocked(downloadNodalArtifact).mockResolvedValue(new Blob());
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:mock-url"),
    revokeObjectURL: vi.fn(),
  });
});

describe("NodalArtifactDownloads", () => {
  it("renders a button per available artifact", () => {
    render(<I18nProvider><NodalArtifactDownloads runId="run-1" artifacts={ALL_ARTIFACTS} /></I18nProvider>);
    expect(screen.getByRole("button", { name: /LMP por zona CSV/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Resumen JSON/i })).toBeInTheDocument();
  });

  it("downloads an artifact on click", () => {
    render(<I18nProvider><NodalArtifactDownloads runId="run-1" artifacts={ALL_ARTIFACTS} /></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: /LMP por zona CSV/i }));
    expect(downloadNodalArtifact).toHaveBeenCalledWith("run-1", "lmp");
  });

  it("shows empty state when no artifacts available", () => {
    render(<I18nProvider><NodalArtifactDownloads runId="run-1" artifacts={{} as Record<NodalArtifactName, boolean>} /></I18nProvider>);
    expect(screen.getByText(/no hay artefactos disponibles/i)).toBeInTheDocument();
  });
});