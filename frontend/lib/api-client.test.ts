import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./supabase", () => ({
  supabase: { auth: { getSession: vi.fn() } },
}));

import { supabase } from "./supabase";
import { createRun, createScenario, downloadNodalArtifact, downloadRunArtifact, getChartSeries, getRunDispatch, getRunLog, getRunMarginalPlants, getRunNodalArtifact, listRuns } from "./api-client";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

beforeEach(() => {
  fetchMock.mockReset();
  vi.mocked(supabase.auth.getSession).mockResolvedValue({
    data: { session: { access_token: "tok-123" } },
  } as never);
});

describe("api-client", () => {
  it("listRuns sends the Authorization header and returns parsed JSON", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [{ run_id: "r1" }],
    });

    const runs = await listRuns();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      })
    );
    expect(runs).toEqual([{ run_id: "r1" }]);
  });

  it("createRun POSTs the body as JSON", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: "r2", status: "pending" }),
    });

    await createRun({ dispatch_date: "2024-04-18", level: "preideal" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      dispatch_date: "2024-04-18",
      level: "preideal",
    });
  });

  it("createScenario POSTs the body as JSON and returns the id", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ id: "scn-1" }),
    });

    const result = await createScenario({
      mode: "arbitrage",
      penetration_level: "baseline",
      units: [
        {
          name: "bess-1",
          mwh_nom: 10,
          hours_to_deplete: 4,
          initial_soc: 0.5,
          min_soc: 0.1,
          max_soc: 0.9,
          efficiency: 0.9,
          charge_bid: 50,
          discharge_bid: 200,
        },
      ],
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body);
    expect(body.mode).toBe("arbitrage");
    expect(body.units).toHaveLength(1);
    expect(result).toEqual({ id: "scn-1" });
  });

  it("throws with status and body text when the response is not ok", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      text: async () => "run not found",
    });

    await expect(listRuns()).rejects.toThrow("404");
  });

  it("getRunDispatch fetches the dispatch artifact as JSON rows", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [{ generador: "TERMO1", datetime: "2024-04-18 00:00:00", dispatch: 300 }],
    });

    const rows = await getRunDispatch("run-1");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs/run-1/dispatch"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      })
    );
    expect(rows).toEqual([{ generador: "TERMO1", datetime: "2024-04-18 00:00:00", dispatch: 300 }]);
  });

  it("downloadRunArtifact fetches with auth header and returns a Blob", async () => {
    const fakeBlob = new Blob(["csv,data"], { type: "text/csv" });
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => fakeBlob,
    });

    const blob = await downloadRunArtifact("run-1", "dispatch");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs/run-1/download/dispatch"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      })
    );
    expect(blob).toBe(fakeBlob);
  });

  it("downloadRunArtifact throws when the response is not ok", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, statusText: "Not Found" });

    await expect(downloadRunArtifact("run-1", "bess")).rejects.toThrow("404");
  });

  it("getRunMarginalPlants fetches the marginal plants endpoint as JSON rows", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [
        { datetime: "2024-04-18 00:00:00", generador: "TERMO1", dispatch: 300, pmax: 400, is_marginal: true },
      ],
    });

    const rows = await getRunMarginalPlants("run-1");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs/run-1/marginal_plants"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      })
    );
    expect(rows).toEqual([
      { datetime: "2024-04-18 00:00:00", generador: "TERMO1", dispatch: 300, pmax: 400, is_marginal: true },
    ]);
  });

  it("getRunLog returns the text body on success", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => "line 1\nline 2",
    });

    const log = await getRunLog("run-1");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs/run-1/log"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      })
    );
    expect(log).toBe("line 1\nline 2");
  });

  it("getRunLog returns null on 404 instead of throwing", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, statusText: "Not Found" });

    const log = await getRunLog("run-1");

    expect(log).toBeNull();
  });
});

describe("getChartSeries", () => {
  it("fetches /chart/series with the requested days window", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [{ date: "2024-04-18" }],
    });

    const rows = await getChartSeries(7);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/chart/series?days=7"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      })
    );
    expect(rows).toEqual([{ date: "2024-04-18" }]);
  });

  it("requests the default 30-day window", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => [] });

    await getChartSeries(30);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/chart/series?days=30"),
      expect.anything()
    );
  });
});

describe("getRunNodalArtifact", () => {
  it("fetches nodal artifact rows with auth header", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200, statusText: "OK",
      json: async () => [{ timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20 }],
    } as never);
    const rows = await getRunNodalArtifact<{ timestamp: string; bus: string; lmp: number }[]>(
      "run-1", "lmp",
    );
    expect(rows).toEqual([{ timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20 }]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs/run-1/nodal/lmp"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      }),
    );
  });

  it("parses summary artifact as an object", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200, statusText: "OK",
      json: async () => ({ metrics: { total_cost: 100 } }),
    } as never);
    const summary = await getRunNodalArtifact<{ metrics: Record<string, number> }>(
      "run-1", "summary",
    );
    expect(summary.metrics.total_cost).toBe(100);
  });
});

describe("downloadNodalArtifact", () => {
  it("downloads a nodal artifact blob", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200, statusText: "OK",
      blob: async () => new Blob(["a,b\n1,2"]),
    } as never);
    const blob = await downloadNodalArtifact("run-1", "branch_flows");
    expect(blob).toBeInstanceOf(Blob);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/runs/run-1/download/nodal/branch_flows"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
      }),
    );
  });

  it("throws on error response", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404, statusText: "Not Found" } as never);
    await expect(downloadNodalArtifact("run-1", "lmp")).rejects.toThrow("404 Not Found");
  });
});
