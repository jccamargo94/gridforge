import { describe, expect, it } from "vitest";
import { isManualRun, isTerminalStatus, statusLabel, statusBadgeVariant } from "./run-status";

describe("isTerminalStatus", () => {
  it("is false for pending and running", () => {
    expect(isTerminalStatus("pending")).toBe(false);
    expect(isTerminalStatus("running")).toBe(false);
  });

  it("is true for done and failed", () => {
    expect(isTerminalStatus("done")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
  });
});

describe("isManualRun", () => {
  it("is false for public runs (daily system lane)", () => {
    expect(isManualRun({ visibility: "public" })).toBe(false);
  });

  it("is true for private runs (manual lane)", () => {
    expect(isManualRun({ visibility: "private" })).toBe(true);
  });

  it("is true when visibility is missing (stale fixture)", () => {
    expect(isManualRun({})).toBe(true);
    expect(isManualRun({ visibility: undefined })).toBe(true);
  });
});

describe("statusLabel", () => {
  it("returns the Spanish label for each status", () => {
    expect(statusLabel("pending")).toBe("Pendiente");
    expect(statusLabel("running")).toBe("En ejecucion");
    expect(statusLabel("done")).toBe("Completado");
    expect(statusLabel("failed")).toBe("Fallido");
  });

  it("returns the English label when lang=en", () => {
    expect(statusLabel("pending", "en")).toBe("Pending");
    expect(statusLabel("running", "en")).toBe("Running");
    expect(statusLabel("done", "en")).toBe("Done");
    expect(statusLabel("failed", "en")).toBe("Failed");
  });
});

describe("statusBadgeVariant", () => {
  it("maps done to default and failed to destructive", () => {
    expect(statusBadgeVariant("done")).toBe("default");
    expect(statusBadgeVariant("failed")).toBe("destructive");
  });
});
