# Dashboard de comparación nodal (Fase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the nodal LMP comparison dashboard in the frontend: a `/nodal` discovery page listing LMP runs with their network topology, and a `/runs/[id]/nodal` dashboard visualizing zonal map, price curves, dispatch, branch flows, differential tables, redistribution matrix, and artifact downloads — plus the minimal backend enrichment of `GET /runs` that powers the list page.

**Architecture:** Pure frontend work (Next.js 16 App Router, react-query, recharts, shadcn/ui) consuming the already-merged Fase 2 nodal API endpoints. One small backend change: `GET /runs` gains a `nodal: {network_name, zones, generators, branches} | null` field per run. Deterministic topology layout and LMP color math live in pure `lib/` functions so they are unit-testable without DOM.

**Tech Stack:** TypeScript strict, Next.js 16.3 App Router, @tanstack/react-query v5, recharts 3.10, Tailwind v4, Base UI shadcn components, vitest 4 + Testing Library, FastAPI (backend).

**Spec:** [`docs/superpowers/specs/2026-08-18-lmp-nodal-frontend-design.md`](../specs/2026-08-18-lmp-nodal-frontend-design.md)

## Global Constraints

- Branch: `feat/lmp-nodal-frontend` (already created; spec committed). All commits land here.
- Git commands MUST be prefixed: `PYENV_VERSION=system git ...` (pyenv hook breaks plain git).
- Backend gates (run from repo root): `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`.
- Frontend gates (run from `frontend/`): `pnpm lint`, `pnpm test`.
- No code comments unless the surrounding code already comments (repo convention).
- Every user-facing string goes through `t()` from `@/lib/i18n-context`; keys added to BOTH `es` and `en` dicts in `frontend/lib/i18n.ts` (es first). Existing strings use NO accents (`contrasena`, `ejecucion`, `comparacion`) — follow that.
- Zone/generator/branch names are data (network JSON), never translated.
- Next.js 16 has breaking changes vs training data: read `frontend/node_modules/next/dist/docs/` before writing page code. Pages under `app/(app)/` are `"use client"` and inherit the shell from `app/(app)/layout.tsx` (no per-page layout).
- Do NOT touch `app/model/`, `app/pipeline/case_builder.py`, or `app/nodal/` business logic. The only backend change is `GET /runs` enrichment in `services/api/main.py`.
- No `Co-Authored-By` or any AI attribution line in any commit message.

## File Structure

**Backend (1 file modified, 1 test modified):**
- `services/api/main.py` — add `_nodal_summary` helper; wire into `list_runs`.
- `tests/test_api_runs.py` — add nodal-summary tests.

**Frontend libs (types + pure functions, all unit-testable):**
- `frontend/lib/types.ts` — modify: `DispatchLevel` + `"lmp"`, `RunSummary.nodal`, `RunDetail.nodal`, new nodal interfaces.
- `frontend/lib/api-client.ts` — modify: `getRunNodalArtifact`, `downloadNodalArtifact`.
- `frontend/lib/nodal-layout.ts` — create: `computeZoneLayout`, `lmpColor` (pure, deterministic).
- `frontend/lib/nodal-chart-data.ts` — create: `hourFromTimestamp`, `toPriceCurveData`, `toNodalDispatchSeries`, `toBranchFlowSeries`, `zoneLmpAtHour` (pure).
- `frontend/lib/i18n.ts` — modify: `sidebar.nodal` + `nodal.*` keys (es + en).

**Frontend components:**
- `frontend/components/app-sidebar.tsx` — modify: add `/nodal` NAV_ITEM + active logic.
- `frontend/components/nodal/network-card.tsx`, `zonal-map.tsx`, `price-curves-chart.tsx`, `nodal-dispatch-chart.tsx`, `branch-flows-chart.tsx`, `differential-table.tsx`, `redistribution-matrix.tsx`, `nodal-artifact-downloads.tsx` — create.

**Frontend pages:**
- `frontend/app/(app)/nodal/page.tsx` — create (list of LMP runs).
- `frontend/app/(app)/runs/[id]/nodal/page.tsx` — create (dashboard).
- `frontend/app/(app)/runs/[id]/page.tsx` — modify (link to nodal dashboard when `data.nodal`).

**Tests (colocated, one per unit):**
- `tests/test_api_runs.py` — nodal summary in `GET /runs`.
- `frontend/lib/nodal-layout.test.ts`, `frontend/lib/nodal-chart-data.test.ts`, `frontend/lib/types.test.ts`, `frontend/lib/api-client.test.ts` (extend), `frontend/components/nodal/*.test.tsx` (7 files), `frontend/components/app-sidebar.test.tsx` (extend), `frontend/app/(app)/nodal/page.test.tsx`, `frontend/app/(app)/runs/[id]/nodal/page.test.tsx`, `frontend/app/(app)/runs/[id]/page.test.tsx` (extend).

**Commit sequence:** one commit per task; conventional messages (`feat:`, `test:`).

---

### Task 1: Backend — enrich `GET /runs` with nodal summary

**Files:**
- Modify: `services/api/main.py` (add helper near `_NODAL_ARTIFACT_PATHS`; modify `list_runs`)
- Test: `tests/test_api_runs.py`

**Interfaces:**
- Consumes: `queries.get_nodal_result(session, run_id) -> app.db.models.NodalResult | None` (already exists, `app/db/queries.py:113`); `queries.list_runs_for_user`, `queries.get_case`, `NodalRunResult` from `app.schemas`, `RunResult`, `DispatchCase`, `DispatchLevel`, `make_three_zone_network` from `tests.fixtures.nodal`.
- Produces: `GET /runs` response items gain `nodal: {network_name: str | None, zones: int, generators: int, branches: int} | None`. `GET /runs/{id}` is UNCHANGED.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api_runs.py` (imports to add at top: `from datetime import date`, `import pandas as pd`, `from app.db import queries`, `from app.schemas import DispatchCase, DispatchLevel, NodalRunResult, RunResult`, `from tests.fixtures.nodal import make_three_zone_network`):

```python
def _seed_done_nodal_run_with_network(api_client, tmp_path):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "lmp",
            "nodal_network": make_three_zone_network(congested=True).model_dump(),
        },
    )
    run_id = resp.json()["run_id"]

    run_out = tmp_path / "results" / run_id
    out_dir = run_out / "2024-04-18-lmp"
    out_dir.mkdir(parents=True)
    pd.DataFrame(
        [{"timestamp": "2024-04-18 00:00", "bus": "norte", "lmp": 20.0}]
    ).to_csv(out_dir / "lmp.csv", index=False)
    pd.DataFrame(
        [{"generator": "G_N", "zone": "norte", "fuel": "hydro", "hour": 0, "dispatch_mw": 100.0}]
    ).to_csv(out_dir / "dispatch.csv", index=False)
    pd.DataFrame([{"timestamp": "2024-04-18 00:00", "branch": "NC", "flow_mw": 10.0}]).to_csv(
        out_dir / "branch_flows.csv", index=False
    )
    pd.DataFrame(
        [{"zone": "norte", "hour": 0, "load_payment": 1.0, "gen_revenue": 1.0, "uplift": 0.0}]
    ).to_csv(out_dir / "settlement_status_quo.csv", index=False)
    pd.DataFrame([{"zone": "norte", "hour": 0, "load_payment": 1.0, "gen_revenue": 1.0}]).to_csv(
        out_dir / "settlement_lmp.csv", index=False
    )
    pd.DataFrame(
        [{"zone": "norte", "load_payment_a": 1.0, "load_payment_b": 2.0, "delta": 1.0}]
    ).to_csv(out_dir / "comparison.csv", index=False)
    (out_dir / "summary.json").write_text('{"metrics": {"total_cost": 100.0}}')

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.lmp)
    result = RunResult(
        case=case,
        ok=True,
        nodal=NodalRunResult(
            lmp_path=str(out_dir / "lmp.csv"),
            dispatch_path=str(out_dir / "dispatch.csv"),
            branch_flows_path=str(out_dir / "branch_flows.csv"),
            settlement_status_quo_path=str(out_dir / "settlement_status_quo.csv"),
            settlement_lmp_path=str(out_dir / "settlement_lmp.csv"),
            comparison_path=str(out_dir / "comparison.csv"),
            summary_path=str(out_dir / "summary.json"),
            metrics={"total_cost": 100.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={
                "name": "three_zone",
                "zones": [
                    {"name": "norte", "base_kv": 230.0},
                    {"name": "centro", "base_kv": 230.0},
                    {"name": "sur", "base_kv": 230.0},
                ],
                "generators": [
                    {"name": "G_N", "zone": "norte"},
                    {"name": "G_C", "zone": "centro"},
                    {"name": "G_S", "zone": "sur"},
                ],
                "branches": [
                    {"name": "NC", "from_zone": "norte", "to_zone": "centro"},
                    {"name": "CS", "from_zone": "centro", "to_zone": "sur"},
                ],
            },
        ),
    )
    queries.finish_nodal_run_ok(session, run, result, out_dir=str(run_out))
    session.close()
    return run_id


def test_list_runs_includes_nodal_summary_for_nodal_run(api_client, tmp_path):
    run_id = _seed_done_nodal_run_with_network(api_client, tmp_path)
    resp = api_client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()
    nodal_run = next(r for r in runs if r["run_id"] == run_id)
    assert nodal_run["nodal"] == {
        "network_name": "three_zone",
        "zones": 3,
        "generators": 3,
        "branches": 2,
    }


def test_list_runs_returns_nodal_null_for_classic_run(api_client):
    resp = api_client.post(
        "/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"}
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    resp = api_client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()
    classic_run = next(r for r in runs if r["run_id"] == run_id)
    assert classic_run["nodal"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_api_runs.py`
Expected: FAIL with `KeyError: 'nodal'` (key missing from response items).

- [ ] **Step 3: Implement `_nodal_summary` and wire it into `list_runs`**

In `services/api/main.py`, near `_NODAL_ARTIFACT_PATHS`, add:

```python
def _nodal_summary(session, run_id: str) -> dict | None:
    nodal = queries.get_nodal_result(session, run_id)
    if nodal is None or not nodal.network:
        return None
    net = nodal.network
    return {
        "network_name": net.get("name"),
        "zones": len(net.get("zones", [])),
        "generators": len(net.get("generators", [])),
        "branches": len(net.get("branches", [])),
    }
```

Modify `list_runs` (currently: `return [_run_summary(r, queries.get_case(session, r.case_id)) for r in runs]`) to:

```python
return [
    {
        **_run_summary(r, queries.get_case(session, r.case_id)),
        "nodal": _nodal_summary(session, r.id),
    }
    for r in runs
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_runs.py`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Full backend gates**

Run: `uv run pytest -q` then `uv run ruff check` then `uv run ruff format --check`
Expected: all pass (ruff may flag long lines — run `uv run ruff format services/api/main.py tests/test_api_runs.py` if so).

- [ ] **Step 6: Commit**

```bash
PYENV_VERSION=system git add services/api/main.py tests/test_api_runs.py
PYENV_VERSION=system git commit -m "feat(api): enrich GET /runs with nodal summary"
```

---

### Task 2: Frontend types — nodal interfaces

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/lib/types.test.ts`

**Interfaces:**
- Consumes: existing `RunSummary`, `RunDetail`, `DispatchLevel` definitions (do not rename).
- Produces: `NodalSummary`, `NodalArtifactName`, `NodalZone`, `NodalGenerator`, `NodalBranch`, `NodalBusLoad`, `NodalNetwork`, `NodalMetrics`, `NodalRedistributionRow`, `NodalGenRevenueRow`, `NodalResult`, `LmpRow`, `NodalDispatchRow`, `BranchFlowRow`, `SettlementRow`, `NodalSummaryTotals`, `NodalSummaryJson`; `DispatchLevel` gains `"lmp"`; `RunSummary` gains `nodal: NodalSummary | null`; `RunDetail` gains `nodal: NodalResult | null`.

- [ ] **Step 1: Write the failing test**

Create `frontend/lib/types.test.ts`:

```ts
import type { DispatchLevel, LmpRow, NodalDispatchRow, NodalResult, RunSummary } from "./types";

describe("nodal types", () => {
  it("accepts lmp dispatch level", () => {
    const level: DispatchLevel = "lmp";
    expect(level).toBe("lmp");
  });

  it("shapes RunSummary with nodal summary", () => {
    const summary: RunSummary = {
      run_id: "r1", status: "done", dispatch_date: "2024-04-18", level: "lmp",
      scenario_id: null, created_at: "2024-04-18T00:00:00Z", started_at: null,
      finished_at: null, error: null,
      nodal: { network_name: "three_zone", zones: 3, generators: 3, branches: 2 },
    };
    expect(summary.nodal?.zones).toBe(3);
  });

  it("shapes a full nodal result", () => {
    const result: NodalResult = {
      metrics: { total_cost: 100 },
      redistribution: [{ zone: "norte", load_payment_a: 1, load_payment_b: 2, delta: 1 }],
      gen_revenue_by_zone: [{ zone: "norte", fuel: "hydro", revenue_a: 1, revenue_b: 2, delta: 1 }],
      network: {
        name: "three_zone", baseMVA: 100, reference_zone: "norte",
        zones: [{ name: "norte", base_kv: 230 }],
        generators: [
          { name: "G_N", zone: "norte", p_min: 0, p_max: 500, marginal_cost: 20,
            no_load_cost: 0, fuel: "hydro", min_up_time: 1, min_down_time: 1,
            initial_status: 1, ramp_rate: null },
        ],
        branches: [{ name: "NC", from_zone: "norte", to_zone: "centro", reactance: 0.1, rating: 120 }],
        loads: [], demand_shares: { norte: 1 },
      },
      artifacts: { lmp: true, dispatch: true, branch_flows: true, settlement_status_quo: true, settlement_lmp: true, comparison: true, summary: true },
    };
    expect(result.network.zones[0].name).toBe("norte");
  });

  it("shapes LMP and nodal dispatch rows", () => {
    const lmp: LmpRow = { timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20 };
    const row: NodalDispatchRow = { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 };
    expect(lmp.bus).toBe("norte");
    expect(row.dispatch_mw).toBe(100);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm exec tsc --noEmit`
Expected: errors — `Type '"lmp"' is not assignable to type '"preideal" | "ideal"'` and `Property 'nodal' does not exist on type 'RunSummary'`.

- [ ] **Step 3: Implement the types**

In `frontend/lib/types.ts`:
- Change `DispatchLevel` to `"preideal" | "ideal" | "lmp"`.
- Add `nodal: NodalSummary | null;` to `RunSummary`.
- Add `nodal: NodalResult | null;` to `RunDetail`.

Append:

```ts
export interface NodalSummary {
  network_name: string | null;
  zones: number;
  generators: number;
  branches: number;
}

export type NodalArtifactName =
  | "lmp" | "dispatch" | "branch_flows"
  | "settlement_status_quo" | "settlement_lmp" | "comparison" | "summary";

export interface NodalZone { name: string; base_kv: number; }

export interface NodalGenerator {
  name: string; zone: string; p_min: number; p_max: number;
  marginal_cost: number; no_load_cost: number; fuel: string;
  min_up_time: number; min_down_time: number; initial_status: number;
  ramp_rate: number | null;
}

export interface NodalBranch {
  name: string; from_zone: string; to_zone: string;
  reactance: number; rating: number;
}

export interface NodalBusLoad { zone: string; p_load: number[]; }

export interface NodalNetwork {
  name: string; baseMVA: number; reference_zone: string;
  zones: NodalZone[]; generators: NodalGenerator[]; branches: NodalBranch[];
  loads: NodalBusLoad[]; demand_shares: Record<string, number>;
}

export type NodalMetrics = Record<string, number>;

export interface NodalRedistributionRow {
  zone: string; load_payment_a: number; load_payment_b: number; delta: number;
}

export interface NodalGenRevenueRow {
  zone: string; fuel: string; revenue_a: number; revenue_b: number; delta: number;
}

export interface NodalResult {
  metrics: NodalMetrics;
  redistribution: NodalRedistributionRow[];
  gen_revenue_by_zone: NodalGenRevenueRow[];
  network: NodalNetwork;
  artifacts: Record<NodalArtifactName, boolean>;
}

export interface LmpRow { timestamp: string; bus: string; lmp: number; }

export interface NodalDispatchRow {
  generator: string; zone: string; fuel: string; hour: number; dispatch_mw: number;
}

export interface BranchFlowRow { timestamp: string; branch: string; flow_mw: number; }

export interface SettlementRow {
  zone: string; hour: number; load_payment: number; gen_revenue: number;
  uplift?: number | null;
}

export interface NodalSummaryTotals {
  total_cost: number; total_load_payment_a: number; total_load_payment_b: number;
  total_gen_revenue_a: number; total_gen_revenue_b: number; congestion_rent_total: number;
}

export interface NodalSummaryJson {
  metrics: NodalMetrics; totals: NodalSummaryTotals;
  generator_count: number; branch_count: number;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm exec tsc --noEmit` then `pnpm test -- --run types.test.ts`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/lib/types.ts frontend/lib/types.test.ts
PYENV_VERSION=system git commit -m "feat(frontend): add nodal types"
```

---

### Task 3: API client — nodal artifact fetchers

**Files:**
- Modify: `frontend/lib/api-client.ts`
- Test: `frontend/lib/api-client.test.ts`

**Interfaces:**
- Consumes: `authHeader()`, `request<T>()`, `API_BASE_URL` (existing, unchanged); `NodalArtifactName` from `./types`.
- Produces: `getRunNodalArtifact<T>(id: string, artifact: NodalArtifactName): Promise<T>` and `downloadNodalArtifact(id: string, artifact: NodalArtifactName): Promise<Blob>`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/lib/api-client.test.ts` (it already stubs `./supabase` and `fetch`; reuse the existing `fetchMock` and `getSession` mock setup at the top of that file):

```ts
import { downloadNodalArtifact, getRunNodalArtifact } from "./api-client";
```

Then add these tests:

```ts
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `pnpm test -- --run api-client.test.ts`
Expected: FAIL — `getRunNodalArtifact is not a function` / `downloadNodalArtifact is not a function`.

- [ ] **Step 3: Implement the functions**

In `frontend/lib/api-client.ts`, add `NodalArtifactName` to the type import from `./types`, then append:

```ts
export async function getRunNodalArtifact<T>(
  id: string,
  artifact: NodalArtifactName,
): Promise<T> {
  return request<T>(`/runs/${id}/nodal/${artifact}`);
}

export async function downloadNodalArtifact(
  id: string,
  artifact: NodalArtifactName,
): Promise<Blob> {
  const headers = await authHeader();
  const resp = await fetch(`${API_BASE_URL}/runs/${id}/download/nodal/${artifact}`, { headers });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.blob();
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- --run api-client.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/lib/api-client.ts frontend/lib/api-client.test.ts
PYENV_VERSION=system git commit -m "feat(frontend): add nodal artifact fetchers"
```

---

### Task 4: `lib/nodal-layout.ts` — deterministic layout + LMP color

**Files:**
- Create: `frontend/lib/nodal-layout.ts`
- Test: `frontend/lib/nodal-layout.test.ts`

**Interfaces:**
- Consumes: nothing (pure).
- Produces: `computeZoneLayout(zones: string[], branches: {from: string; to: string}[]): Record<string, {x: number; y: number}>` (deterministic, circle init + ~200 Fruchterman–Reingold iterations, no randomness, output clamped to a 600×400 canvas); `lmpColor(lmp: number, min: number, max: number): string` (linear blue `#2563eb` → amber `#f59e0b` interpolation as `rgb(r, g, b)`; degenerate `min === max` returns `#71717a`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/lib/nodal-layout.test.ts`:

```ts
import { computeZoneLayout, lmpColor } from "./nodal-layout";

const THREE_ZONES = ["norte", "centro", "sur"];
const THREE_BRANCHES = [
  { from: "norte", to: "centro" },
  { from: "centro", to: "sur" },
];

describe("computeZoneLayout", () => {
  it("is deterministic for the same input", () => {
    const a = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    const b = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    expect(a).toEqual(b);
  });

  it("places one point per zone", () => {
    const layout = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    expect(Object.keys(layout).sort()).toEqual([...THREE_ZONES].sort());
  });

  it("keeps coordinates inside the canvas", () => {
    const layout = computeZoneLayout(THREE_ZONES, THREE_BRANCHES);
    for (const p of Object.values(layout)) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(600);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(400);
    }
  });

  it("returns empty for empty zones", () => {
    expect(computeZoneLayout([], [])).toEqual({});
  });

  it("handles branches referencing unknown zones", () => {
    const layout = computeZoneLayout(["a"], [{ from: "a", to: "missing" }]);
    expect(layout.a).toBeDefined();
  });
});

describe("lmpColor", () => {
  it("returns neutral for degenerate range", () => {
    expect(lmpColor(50, 50, 50)).toBe("#71717a");
  });
  it("returns blue at the minimum", () => {
    expect(lmpColor(0, 0, 100)).toBe("rgb(37, 99, 235)");
  });
  it("returns amber at the maximum", () => {
    expect(lmpColor(100, 0, 100)).toBe("rgb(245, 158, 11)");
  });
  it("clamps out-of-range values", () => {
    expect(lmpColor(-50, 0, 100)).toBe("rgb(37, 99, 235)");
    expect(lmpColor(500, 0, 100)).toBe("rgb(245, 158, 11)");
  });
  it("interpolates midpoints", () => {
    expect(lmpColor(50, 0, 100)).toMatch(/^rgb\(/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `pnpm test -- --run nodal-layout.test.ts`
Expected: FAIL — `Cannot find module './nodal-layout'`.

- [ ] **Step 3: Implement the module**

Create `frontend/lib/nodal-layout.ts`:

```ts
const CANVAS_WIDTH = 600;
const CANVAS_HEIGHT = 400;

interface Point { x: number; y: number; }

export interface ZoneEdge { from: string; to: string; }

export function computeZoneLayout(
  zones: string[],
  branches: ZoneEdge[],
): Record<string, Point> {
  const n = zones.length;
  if (n === 0) return {};
  const cx = CANVAS_WIDTH / 2;
  const cy = CANVAS_HEIGHT / 2;
  const radius = Math.min(CANVAS_WIDTH, CANVAS_HEIGHT) * 0.38;
  const pos: Record<string, Point> = {};
  zones.forEach((zone, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    pos[zone] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });
  if (n === 1) return pos;

  const k = Math.sqrt((CANVAS_WIDTH * CANVAS_HEIGHT) / n) * 0.35;
  const iterations = 200;
  const known = new Set(zones);

  for (let iter = 0; iter < iterations; iter++) {
    const temp = 1 - iter / iterations;
    const disp: Record<string, Point> = {};
    zones.forEach((zone) => { disp[zone] = { x: 0, y: 0 }; });

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = zones[i];
        const b = zones[j];
        let dx = pos[a].x - pos[b].x;
        let dy = pos[a].y - pos[b].y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
        const force = (k * k) / dist;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        disp[a].x += dx;
        disp[a].y += dy;
        disp[b].x -= dx;
        disp[b].y -= dy;
      }
    }

    for (const edge of branches) {
      if (!known.has(edge.from) || !known.has(edge.to)) continue;
      let dx = pos[edge.from].x - pos[edge.to].x;
      let dy = pos[edge.from].y - pos[edge.to].y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const force = (dist * dist) / k;
      dx = (dx / dist) * force;
      dy = (dy / dist) * force;
      disp[edge.from].x -= dx;
      disp[edge.from].y -= dy;
      disp[edge.to].x += dx;
      disp[edge.to].y += dy;
    }

    zones.forEach((zone) => {
      const d = Math.sqrt(disp[zone].x * disp[zone].x + disp[zone].y * disp[zone].y);
      const step = d > 0 ? Math.min(d, temp) / d : 0;
      pos[zone].x += disp[zone].x * step;
      pos[zone].y += disp[zone].y * step;
      pos[zone].x = Math.min(CANVAS_WIDTH - 30, Math.max(30, pos[zone].x));
      pos[zone].y = Math.min(CANVAS_HEIGHT - 30, Math.max(30, pos[zone].y));
    });
  }

  return pos;
}

const BLUE: [number, number, number] = [37, 99, 235];
const AMBER: [number, number, number] = [245, 158, 11];

export function lmpColor(lmp: number, min: number, max: number): string {
  if (min === max) return "#71717a";
  const t = Math.min(1, Math.max(0, (lmp - min) / (max - min)));
  const channels = BLUE.map((v, i) => Math.round(v + (AMBER[i] - v) * t));
  return `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- --run nodal-layout.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/lib/nodal-layout.ts frontend/lib/nodal-layout.test.ts
PYENV_VERSION=system git commit -m "feat(frontend): add deterministic nodal layout and lmp color"
```

---

### Task 5: `lib/nodal-chart-data.ts` — hourly series transforms

**Files:**
- Create: `frontend/lib/nodal-chart-data.ts`
- Test: `frontend/lib/nodal-chart-data.test.ts`

**Interfaces:**
- Consumes: `LmpRow`, `NodalDispatchRow`, `BranchFlowRow` from `./types`; `Lang` and `t` from `./i18n`.
- Produces:
  - `hourFromTimestamp(ts: string): number` — parses the hour from `"YYYY-MM-DD HH:MM:SS"` or ISO `"T"`-separated strings (0 on failure).
  - `toPriceCurveData(rows: LmpRow[]): { data: HourlyPoint[]; seriesKeys: string[] }` — one series per `bus`, 24 points `{hour, [zone]: lmp}`.
  - `toNodalDispatchSeries(rows: NodalDispatchRow[], lang: Lang = "es"): { data: HourlyPoint[]; seriesKeys: string[] }` — stacked by generator, top 6 + `"Others"` (`t(lang, "chart.others")`) when more than 6 generators, 24 points.
  - `toBranchFlowSeries(rows: BranchFlowRow[]): { data: HourlyPoint[]; seriesKeys: string[] }` — one series per `branch`, 24 points.
  - `zoneLmpAtHour(rows: LmpRow[], zone: string, hour: number): number | null`.
  - `HourlyPoint = { hour: number; [key: string]: number }`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/lib/nodal-chart-data.test.ts`:

```ts
import {
  hourFromTimestamp, toBranchFlowSeries, toNodalDispatchSeries,
  toPriceCurveData, zoneLmpAtHour,
} from "./nodal-chart-data";

describe("hourFromTimestamp", () => {
  it("parses space-separated timestamps", () => {
    expect(hourFromTimestamp("2024-04-18 13:45")).toBe(13);
  });
  it("parses ISO timestamps", () => {
    expect(hourFromTimestamp("2024-04-18T07:00:00Z")).toBe(7);
  });
  it("returns 0 for unparseable input", () => {
    expect(hourFromTimestamp("nope")).toBe(0);
  });
});

describe("toPriceCurveData", () => {
  const rows = [
    { timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20 },
    { timestamp: "2024-04-18 01:00", bus: "norte", lmp: 21 },
    { timestamp: "2024-04-18 00:00", bus: "sur", lmp: 30 },
  ];
  it("builds 24 hourly points with one series per zone", () => {
    const { data, seriesKeys } = toPriceCurveData(rows);
    expect(data).toHaveLength(24);
    expect(seriesKeys.sort()).toEqual(["norte", "sur"]);
    expect(data[0]).toMatchObject({ hour: 0, norte: 20, sur: 30 });
    expect(data[1]).toMatchObject({ hour: 1, norte: 21 });
  });
});

describe("toNodalDispatchSeries", () => {
  const rows = [
    { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 },
    { generator: "G_N", zone: "norte", fuel: "hydro", hour: 1, dispatch_mw: 110 },
    { generator: "G_S", zone: "sur", fuel: "coal", hour: 0, dispatch_mw: 40 },
    { generator: "G_S", zone: "sur", fuel: "coal", hour: 1, dispatch_mw: 40 },
  ];
  it("stacks dispatch by generator per hour", () => {
    const { data, seriesKeys } = toNodalDispatchSeries(rows, "es");
    expect(data).toHaveLength(24);
    expect(seriesKeys.sort()).toEqual(["G_N", "G_S"]);
    expect(data[0]).toMatchObject({ hour: 0, G_N: 100, G_S: 40 });
    expect(data[1]).toMatchObject({ hour: 1, G_N: 110, G_S: 40 });
  });
});

describe("toBranchFlowSeries", () => {
  const rows = [
    { timestamp: "2024-04-18 00:00", branch: "NC", flow_mw: 10 },
    { timestamp: "2024-04-18 01:00", branch: "NC", flow_mw: 15 },
  ];
  it("builds hourly flows per branch", () => {
    const { data, seriesKeys } = toBranchFlowSeries(rows);
    expect(data).toHaveLength(24);
    expect(seriesKeys).toEqual(["NC"]);
    expect(data[0]).toMatchObject({ hour: 0, NC: 10 });
    expect(data[1]).toMatchObject({ hour: 1, NC: 15 });
  });
});

describe("zoneLmpAtHour", () => {
  const rows = [
    { timestamp: "2024-04-18 00:00", bus: "norte", lmp: 20 },
    { timestamp: "2024-04-18 01:00", bus: "norte", lmp: 21 },
  ];
  it("returns the lmp for a zone and hour", () => {
    expect(zoneLmpAtHour(rows, "norte", 0)).toBe(20);
    expect(zoneLmpAtHour(rows, "norte", 5)).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `pnpm test -- --run nodal-chart-data.test.ts`
Expected: FAIL — `Cannot find module './nodal-chart-data'`.

- [ ] **Step 3: Implement the module**

Create `frontend/lib/nodal-chart-data.ts`:

```ts
import type { BranchFlowRow, LmpRow, NodalDispatchRow } from "./types";
import { t, type Lang } from "./i18n";

export interface HourlyPoint { hour: number; [key: string]: number; }

export function hourFromTimestamp(timestamp: string): number {
  const iso = timestamp.match(/T(\d{2})/);
  if (iso) return Number(iso[1]);
  const space = timestamp.split(" ");
  if (space.length > 1) return Number(space[1].split(":")[0] ?? 0);
  return 0;
}

export function toPriceCurveData(rows: LmpRow[]) {
  const byZone = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byZone.has(row.bus)) byZone.set(row.bus, new Map());
    byZone.get(row.bus)!.set(hourFromTimestamp(row.timestamp), row.lmp);
  }
  const seriesKeys = [...byZone.keys()];
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const point: HourlyPoint = { hour };
    for (const zone of seriesKeys) point[zone] = byZone.get(zone)?.get(hour) ?? 0;
    data.push(point);
  }
  return { data, seriesKeys };
}

export function toNodalDispatchSeries(rows: NodalDispatchRow[], lang: Lang = "es") {
  const byGen = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byGen.has(row.generator)) byGen.set(row.generator, new Map());
    const hours = byGen.get(row.generator)!;
    hours.set(row.hour, (hours.get(row.hour) ?? 0) + row.dispatch_mw);
  }
  const totals = [...byGen.entries()]
    .map(([gen, hours]) => [gen, [...hours.values()].reduce((a, b) => a + b, 0)] as const)
    .sort((a, b) => b[1] - a[1]);
  const top = totals.slice(0, 6).map(([gen]) => gen);
  const othersKey = t(lang, "chart.others");
  const useOthers = byGen.size > 6;
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const point: HourlyPoint = { hour };
    for (const gen of top) point[gen] = byGen.get(gen)?.get(hour) ?? 0;
    if (useOthers) {
      let others = 0;
      for (const [gen, hours] of byGen) {
        if (!top.includes(gen)) others += hours.get(hour) ?? 0;
      }
      point[othersKey] = others;
    }
    data.push(point);
  }
  const seriesKeys = useOthers ? [...top, othersKey] : top;
  return { data, seriesKeys };
}

export function toBranchFlowSeries(rows: BranchFlowRow[]) {
  const byBranch = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byBranch.has(row.branch)) byBranch.set(row.branch, new Map());
    byBranch.get(row.branch)!.set(hourFromTimestamp(row.timestamp), row.flow_mw);
  }
  const seriesKeys = [...byBranch.keys()];
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const point: HourlyPoint = { hour };
    for (const branch of seriesKeys) point[branch] = byBranch.get(branch)?.get(hour) ?? 0;
    data.push(point);
  }
  return { data, seriesKeys };
}

export function zoneLmpAtHour(rows: LmpRow[], zone: string, hour: number): number | null {
  const found = rows.find(
    (row) => row.bus === zone && hourFromTimestamp(row.timestamp) === hour,
  );
  return found ? found.lmp : null;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- --run nodal-chart-data.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/lib/nodal-chart-data.ts frontend/lib/nodal-chart-data.test.ts
PYENV_VERSION=system git commit -m "feat(frontend): add nodal chart data transforms"
```

---

### Task 6: i18n keys — `sidebar.nodal` + `nodal.*`

**Files:**
- Modify: `frontend/lib/i18n.ts`

**Interfaces:**
- Consumes: existing `dict` structure (`Record<Lang, Record<string, string>>`, es first then en), `t(lang, key)`.
- Produces: the exact keys below in both dicts. All later tasks reference these exact keys.

- [ ] **Step 1: Add the keys to the `es` dict**

In the `es` object, under `sidebar`, add `nodal: "Nodal"`. Then add a new top-level `nodal` namespace (place it after `marginalPlants` and before `log`):

```ts
nodal: {
  listTitle: "Corridas nodales",
  listSubtitle: "Corridas de despacho LMP con comparacion de precios",
  noRuns: "No hay corridas nodales aun",
  noRunsHint: "Crea una corrida con nivel LMP desde la pagina de ejecuciones",
  openDashboard: "Abrir dashboard",
  backToRun: "Volver al detalle",
  hour: "Hora",
  totalCost: "Costo total",
  loadPaymentDelta: "Delta pago demanda",
  genRevenueDelta: "Delta ingreso generacion",
  congestionRent: "Renta de congestion",
  priceAvg: "Precio promedio",
  priceVol: "Volatilidad",
  unitCop: "COP",
  unitCopMwh: "COP/MWh",
  unitMw: "MW",
  mapTitle: "Mapa zonal",
  mapSubtitle: "LMP por zona en la hora seleccionada",
  networkTitle: "Red utilizada",
  networkName: "Nombre",
  baseMva: "Base MVA",
  referenceZone: "Zona de referencia",
  zone: "Zona",
  generator: "Generador",
  fuel: "Combustible",
  marginalCost: "Costo marginal",
  branch: "Rama",
  fromTo: "Tramo",
  reactance: "Reactancia",
  rating: "Capacidad (MW)",
  load: "Carga",
  zoneGen: "Generacion de la zona",
  priceCurvesTitle: "Curvas de precio",
  priceCurvesSubtitle: "LMP por zona y precio unico (zona de referencia)",
  singlePrice: "Precio unico",
  dispatchTitle: "Despacho nodal",
  branchFlowsTitle: "Flujos de rama",
  differentialTitle: "Tabla de diferencial",
  loadPaymentA: "Pago demanda A",
  loadPaymentB: "Pago demanda B",
  delta: "Delta",
  genRevenueA: "Ingreso generacion A",
  genRevenueB: "Ingreso generacion B",
  revenueDelta: "Delta ingreso",
  redistributionTitle: "Matriz de redistribucion",
  redistributionSubtitle: "Cambio neto en pago de la demanda por zona (B - A)",
  downloadsTitle: "Descargas",
  noNodalData: "No hay datos nodales para esta corrida",
  dispatchNoData: "No hay datos de despacho nodal",
  branchFlowsNoData: "No hay datos de flujos de rama",
  artifact: {
    lmp: "LMP por zona CSV",
    dispatch: "Despacho nodal CSV",
    branch_flows: "Flujos de rama CSV",
    settlement_status_quo: "Liquidacion A (status quo) CSV",
    settlement_lmp: "Liquidacion B (LMP) CSV",
    comparison: "Comparacion CSV",
    summary: "Resumen JSON",
  },
},
```

- [ ] **Step 2: Add the keys to the `en` dict**

Mirror the same keys in the `en` object (same nesting; add `nodal: "Nodal"` to the `en` `sidebar` object too):

```ts
nodal: {
  listTitle: "Nodal runs",
  listSubtitle: "LMP dispatch runs with price comparison",
  noRuns: "No nodal runs yet",
  noRunsHint: "Create an LMP-level run from the runs page",
  openDashboard: "Open dashboard",
  backToRun: "Back to run detail",
  hour: "Hour",
  totalCost: "Total cost",
  loadPaymentDelta: "Load payment delta",
  genRevenueDelta: "Generation revenue delta",
  congestionRent: "Congestion rent",
  priceAvg: "Average price",
  priceVol: "Volatility",
  unitCop: "COP",
  unitCopMwh: "COP/MWh",
  unitMw: "MW",
  mapTitle: "Zonal map",
  mapSubtitle: "LMP per zone at the selected hour",
  networkTitle: "Network used",
  networkName: "Name",
  baseMva: "Base MVA",
  referenceZone: "Reference zone",
  zone: "Zone",
  generator: "Generator",
  fuel: "Fuel",
  marginalCost: "Marginal cost",
  branch: "Branch",
  fromTo: "Segment",
  reactance: "Reactance",
  rating: "Rating (MW)",
  load: "Load",
  zoneGen: "Zone generation",
  priceCurvesTitle: "Price curves",
  priceCurvesSubtitle: "LMP per zone and single price (reference zone)",
  singlePrice: "Single price",
  dispatchTitle: "Nodal dispatch",
  branchFlowsTitle: "Branch flows",
  differentialTitle: "Differential table",
  loadPaymentA: "Load payment A",
  loadPaymentB: "Load payment B",
  delta: "Delta",
  genRevenueA: "Generation revenue A",
  genRevenueB: "Generation revenue B",
  revenueDelta: "Revenue delta",
  redistributionTitle: "Redistribution matrix",
  redistributionSubtitle: "Net change in load payment per zone (B - A)",
  downloadsTitle: "Downloads",
  noNodalData: "No nodal data for this run",
  dispatchNoData: "No nodal dispatch data",
  branchFlowsNoData: "No branch flow data",
  artifact: {
    lmp: "Zonal LMP CSV",
    dispatch: "Nodal dispatch CSV",
    branch_flows: "Branch flows CSV",
    settlement_status_quo: "Settlement A (status quo) CSV",
    settlement_lmp: "Settlement B (LMP) CSV",
    comparison: "Comparison CSV",
    summary: "Summary JSON",
  },
},
```

- [ ] **Step 3: Verify**

Run (from `frontend/`): `pnpm test` then `pnpm exec tsc --noEmit`
Expected: all PASS, tsc clean.

- [ ] **Step 4: Commit**

```bash
PYENV_VERSION=system git add frontend/lib/i18n.ts
PYENV_VERSION=system git commit -m "feat(frontend): add nodal i18n keys"
```

---

### Task 7: Sidebar — `/nodal` nav item + active logic

**Files:**
- Modify: `frontend/components/app-sidebar.tsx`
- Test: `frontend/components/app-sidebar.test.tsx`

**Interfaces:**
- Consumes: `NAV_ITEMS` array and existing Link styling (unchanged shape), `usePathname`, `useT`, `cn`, lucide icons.
- Produces: new item `{ href: "/nodal", labelKey: "sidebar.nodal", icon: Network }`; active detection that also marks the item active on `/runs/[id]/nodal`.

- [ ] **Step 1: Write the failing test**

In `frontend/components/app-sidebar.test.tsx`, change the `next/navigation` mock to a mutable pathname variable (existing file uses a static mock):

```tsx
const pathname = { current: "/runs" };
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
}));
```

Add tests:

```tsx
it("shows a Nodal nav item linking to /nodal", () => {
  render(
    <ThemeProvider><I18nProvider><AppSidebar /></I18nProvider></ThemeProvider>,
  );
  const link = screen.getByRole("link", { name: /nodal/i });
  expect(link).toHaveAttribute("href", "/nodal");
});

it("marks the Nodal item active on /nodal", () => {
  pathname.current = "/nodal";
  render(<ThemeProvider><I18nProvider><AppSidebar /></I18nProvider></ThemeProvider>);
  expect(screen.getByRole("link", { name: /nodal/i })).toHaveClass("text-amber-400");
});

it("marks the Nodal item active on a nodal dashboard route", () => {
  pathname.current = "/runs/some-id/nodal";
  render(<ThemeProvider><I18nProvider><AppSidebar /></I18nProvider></ThemeProvider>);
  expect(screen.getByRole("link", { name: /nodal/i })).toHaveClass("text-amber-400");
});
```

(Adapt the wrapper to match the file's existing test wrapper.)

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `pnpm test -- --run app-sidebar.test.tsx`
Expected: FAIL — link with name `/nodal/i` not found.

- [ ] **Step 3: Implement**

In `frontend/components/app-sidebar.tsx`:
- Add `Network` to the lucide-react import.
- Add to `NAV_ITEMS`: `{ href: "/nodal", labelKey: "sidebar.nodal", icon: Network }`.
- Change the active check to:

```tsx
const active = href === "/nodal" ? pathname?.includes("/nodal") : pathname?.startsWith(href);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- --run app-sidebar.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/app-sidebar.tsx frontend/components/app-sidebar.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add Nodal sidebar item"
```

---

### Task 8: `components/nodal/network-card.tsx`

**Files:**
- Create: `frontend/components/nodal/network-card.tsx`
- Test: `frontend/components/nodal/network-card.test.tsx`

**Interfaces:**
- Consumes: `NodalNetwork` from `@/lib/types`; `useT` from `@/lib/i18n-context`; shadcn `Card`, `Table` primitives.
- Produces: `<NetworkCard network={NodalNetwork} />` — renders the network name, baseMVA, reference zone, and three tables (zones, generators with zone/fuel/marginal cost, branches with from→to/reactance/rating).

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/network-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run network-card.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/network-card.tsx`:

```tsx
"use client";

import { useT } from "@/lib/i18n-context";
import type { NodalNetwork } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

interface NetworkCardProps { network: NodalNetwork; }

export function NetworkCard({ network }: NetworkCardProps) {
  const { t } = useT();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("nodal.networkTitle")}</CardTitle>
        <CardDescription>
          {network.name} — {t("nodal.referenceZone")}: {network.reference_zone}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="text-muted-foreground">{t("nodal.networkName")}: {network.name}</span>
          <span className="text-muted-foreground">{t("nodal.baseMva")}: {network.baseMVA}</span>
          <span className="text-muted-foreground">{t("nodal.referenceZone")}: {network.reference_zone}</span>
        </div>
        <div className="space-y-4">
          <p className="text-sm font-medium">{t("nodal.zone")}</p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodal.zone")}</TableHead>
                  <TableHead>{t("nodal.baseMva")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {network.zones.map((zone) => (
                  <TableRow key={zone.name}>
                    <TableCell className="font-medium">{zone.name}</TableCell>
                    <TableCell>{zone.base_kv}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        <div className="space-y-4">
          <p className="text-sm font-medium">{t("nodal.generator")}</p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodal.generator")}</TableHead>
                  <TableHead>{t("nodal.zone")}</TableHead>
                  <TableHead>{t("nodal.fuel")}</TableHead>
                  <TableHead>{t("nodal.marginalCost")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {network.generators.map((gen) => (
                  <TableRow key={gen.name}>
                    <TableCell className="font-medium">{gen.name}</TableCell>
                    <TableCell>{gen.zone}</TableCell>
                    <TableCell>{gen.fuel}</TableCell>
                    <TableCell>{gen.marginal_cost}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        <div className="space-y-4">
          <p className="text-sm font-medium">{t("nodal.branch")}</p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodal.branch")}</TableHead>
                  <TableHead>{t("nodal.fromTo")}</TableHead>
                  <TableHead>{t("nodal.reactance")}</TableHead>
                  <TableHead>{t("nodal.rating")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {network.branches.map((branch) => (
                  <TableRow key={branch.name}>
                    <TableCell className="font-medium">{branch.name}</TableCell>
                    <TableCell>{branch.from_zone} → {branch.to_zone}</TableCell>
                    <TableCell>{branch.reactance}</TableCell>
                    <TableCell>{branch.rating}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run network-card.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/network-card.tsx frontend/components/nodal/network-card.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add network card"
```

---

### Task 9: `components/nodal/zonal-map.tsx`

**Files:**
- Create: `frontend/components/nodal/zonal-map.tsx`
- Test: `frontend/components/nodal/zonal-map.test.tsx`

**Interfaces:**
- Consumes: `computeZoneLayout`, `lmpColor` from `@/lib/nodal-layout`; `zoneLmpAtHour` from `@/lib/nodal-chart-data`; `LmpRow`, `NodalBranch`, `NodalGenerator`, `NodalZone` from `@/lib/types`.
- Produces: `<ZonalMap zones branches generators lmpRows hour />` — an `<svg viewBox="0 0 600 400">` with one `<line>` per branch and one `<circle>` per zone, colored by LMP at the selected hour; tooltip via `<title>` on each zone group.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/zonal-map.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow } from "@/lib/types";
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

describe("ZonalMap", () => {
  it("renders one node per zone and one edge per branch", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelectorAll("circle")).toHaveLength(3);
    expect(container.querySelectorAll("line")).toHaveLength(2);
  });

  it("colors nodes by lmp at the selected hour", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} hour={0} />
      </I18nProvider>,
    );
    const fills = [...container.querySelectorAll("circle")].map((c) => c.getAttribute("fill"));
    expect(fills).toContain("rgb(37, 99, 235)");
    expect(fills).toContain("rgb(245, 158, 11)");
  });

  it("includes a tooltip title per zone", () => {
    const { container } = render(
      <I18nProvider>
        <ZonalMap zones={ZONES} branches={BRANCHES} generators={GENERATORS} lmpRows={LMP_ROWS} hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelector("title")?.textContent).toContain("norte");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run zonal-map.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/zonal-map.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import { computeZoneLayout, lmpColor } from "@/lib/nodal-layout";
import { zoneLmpAtHour } from "@/lib/nodal-chart-data";
import type { LmpRow, NodalBranch, NodalGenerator, NodalZone } from "@/lib/types";

interface ZonalMapProps {
  zones: NodalZone[];
  branches: NodalBranch[];
  generators: NodalGenerator[];
  lmpRows: LmpRow[];
  hour: number;
}

export function ZonalMap({ zones, branches, generators, lmpRows, hour }: ZonalMapProps) {
  const layout = useMemo(
    () => computeZoneLayout(zones.map((zone) => zone.name), branches),
    [zones, branches],
  );
  const zoneValues = zones
    .map((zone) => zoneLmpAtHour(lmpRows, zone.name, hour))
    .filter((value): value is number => value !== null);
  const min = zoneValues.length ? Math.min(...zoneValues) : 0;
  const max = zoneValues.length ? Math.max(...zoneValues) : 0;
  const zoneLoad = (zone: string) =>
    generators.filter((g) => g.zone === zone).reduce((sum, g) => sum + g.p_max, 0);

  return (
    <svg viewBox="0 0 600 400" className="h-auto w-full" role="img">
      {branches.map((branch) => {
        const from = layout[branch.from_zone];
        const to = layout[branch.to_zone];
        if (!from || !to) return null;
        return (
          <line key={branch.name} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            stroke="#3f3f46" strokeWidth={2} />
        );
      })}
      {zones.map((zone) => {
        const point = layout[zone.name];
        if (!point) return null;
        const lmp = zoneLmpAtHour(lmpRows, zone.name, hour);
        const fill = lmp === null ? "#71717a" : lmpColor(lmp, min, max);
        return (
          <g key={zone.name}>
            <title>{`${zone.name} - LMP: ${lmp ?? "-"} - ${zoneLoad(zone.name)} MW`}</title>
            <circle cx={point.x} cy={point.y} r={30} fill={fill} stroke="#18181b" strokeWidth={2} />
            <text x={point.x} y={point.y + 4} textAnchor="middle" fill="#fafafa" fontSize={13} fontWeight={600}>
              {zone.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run zonal-map.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/zonal-map.tsx frontend/components/nodal/zonal-map.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add zonal lmp map"
```

---

### Task 10: `components/nodal/price-curves-chart.tsx`

**Files:**
- Create: `frontend/components/nodal/price-curves-chart.tsx`
- Test: `frontend/components/nodal/price-curves-chart.test.tsx`

**Interfaces:**
- Consumes: `toPriceCurveData` from `@/lib/nodal-chart-data`; `formatNumber` from `@/lib/chart-format`; `useChartZoom` from `@/hooks/use-chart-zoom`; `ChartLegend`, `ChartTooltip` from existing components; recharts; `LmpRow` type.
- Produces: `<PriceCurvesChart rows referenceZone hour />` — line per zone over 24h, reference zone styled dashed + labeled `t("nodal.singlePrice")`, vertical `ReferenceLine` at the selected hour, zoom/pan/reset, legend toggle, empty state `t("chart.pricesNoData")`.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/price-curves-chart.test.tsx` (copy the wrapper pattern from `components/price-series-chart.test.tsx`):

```tsx
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow } from "@/lib/types";
import { PriceCurvesChart } from "./price-curves-chart";

const ROWS: LmpRow[] = Array.from({ length: 24 }, (_, hour) => [
  { timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`, bus: "norte", lmp: 20 + hour },
  { timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`, bus: "sur", lmp: 30 + hour },
]).flat();

describe("PriceCurvesChart", () => {
  it("renders a chart with one line per zone plus the single price", () => {
    const { container } = render(
      <I18nProvider>
        <PriceCurvesChart rows={ROWS} referenceZone="norte" hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><PriceCurvesChart rows={[]} referenceZone="norte" hour={0} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run price-curves-chart.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/price-curves-chart.tsx`, following the `price-series-chart.tsx` structure:

```tsx
"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChartLegend, type ChartLegendItem } from "@/components/chart-legend";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { formatNumber } from "@/lib/chart-format";
import { useT } from "@/lib/i18n-context";
import { toPriceCurveData } from "@/lib/nodal-chart-data";
import type { LmpRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];

interface PriceCurvesChartProps {
  rows: LmpRow[];
  referenceZone: string;
  hour: number;
}

export function PriceCurvesChart({ rows, referenceZone, hour }: PriceCurvesChartProps) {
  const { t } = useT();
  const { data, seriesKeys } = useMemo(() => toPriceCurveData(rows), [rows]);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{t("chart.pricesNoData")}</div>;
  }

  const legendItems: ChartLegendItem[] = seriesKeys.map((key, index) => ({
    key,
    name: key === referenceZone ? t("nodal.singlePrice") : key,
    color: PALETTE[index % PALETTE.length],
  }));

  const toggleSeries = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div>
      <div
        {...getWrapperProps()}
        ref={wrapperRef}
        title={t("chart.zoomHint")}
        className={cn("w-full", isZoomed ? "cursor-grab select-none active:cursor-grabbing" : "cursor-crosshair")}
        style={{ minHeight: 320 }}
      >
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={visibleData} margin={{ top: 8, right: 16, left: 8, bottom: 32 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="hour" tick={{ fill: "#a1a1aa" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{ value: t("chart.hour"), position: "bottom", offset: 8, fill: "#a1a1aa" }} />
            <YAxis tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: "#a1a1aa" }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{ value: t("runDetail.copMwh"), angle: -90, position: "insideLeft", fill: "#a1a1aa" }} />
            <Tooltip content={<ChartTooltip unit={t("runDetail.copMwh")} hourLabel={t("chart.hourLabel")} />} />
            <ReferenceLine x={hour} stroke="#f59e0b" strokeDasharray="4 4" />
            {seriesKeys.map((key, index) => (
              <Line key={key} type="monotone" dataKey={key}
                name={key === referenceZone ? t("nodal.singlePrice") : key}
                stroke={PALETTE[index % PALETTE.length]} dot={false}
                strokeWidth={key === referenceZone ? 3 : 2}
                strokeDasharray={key === referenceZone ? "6 4" : undefined}
                hide={hidden.has(key)} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {isZoomed && (
        <div className="mt-2 flex items-center justify-end gap-3 text-xs text-muted-foreground">
          <span className="hidden sm:inline">{t("chart.zoomHint")}</span>
          <button onClick={reset}
            className="rounded-full border border-zinc-700 px-3 py-1 text-zinc-200 hover:border-zinc-500">
            {t("chart.resetZoom")}
          </button>
        </div>
      )}
      <ChartLegend items={legendItems} hidden={hidden} onToggle={toggleSeries} />
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run price-curves-chart.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/price-curves-chart.tsx frontend/components/nodal/price-curves-chart.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add price curves chart"
```

---

### Task 11: `components/nodal/nodal-dispatch-chart.tsx`

**Files:**
- Create: `frontend/components/nodal/nodal-dispatch-chart.tsx`
- Test: `frontend/components/nodal/nodal-dispatch-chart.test.tsx`

**Interfaces:**
- Consumes: `toNodalDispatchSeries` from `@/lib/nodal-chart-data`; `NodalDispatchRow`; chart primitives (pattern: `components/dispatch-chart.tsx` — stacked `AreaChart`).
- Produces: `<NodalDispatchChart rows />` — stacked area by generator over 24h, unit `t("nodal.unitMw")`, legend toggle, zoom/pan/reset, empty state `t("nodal.dispatchNoData")`.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/nodal-dispatch-chart.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalDispatchRow } from "@/lib/types";
import { NodalDispatchChart } from "./nodal-dispatch-chart";

const ROWS: NodalDispatchRow[] = [
  { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 },
  { generator: "G_S", zone: "sur", fuel: "coal", hour: 0, dispatch_mw: 40 },
];

describe("NodalDispatchChart", () => {
  it("renders a stacked area per generator", () => {
    const { container } = render(
      <I18nProvider><NodalDispatchChart rows={ROWS} /></I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-area")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><NodalDispatchChart rows={[]} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de despacho nodal/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run nodal-dispatch-chart.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/nodal-dispatch-chart.tsx` — mirror `components/dispatch-chart.tsx` but source data from `toNodalDispatchSeries(rows)` and duplicate the `PALETTE` constant:

```tsx
"use client";

import { useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartLegend, type ChartLegendItem } from "@/components/chart-legend";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartZoom } from "@/hooks/use-chart-zoom";
import { formatNumber } from "@/lib/chart-format";
import { useT } from "@/lib/i18n-context";
import { toNodalDispatchSeries } from "@/lib/nodal-chart-data";
import type { NodalDispatchRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];

interface NodalDispatchChartProps { rows: NodalDispatchRow[]; }

export function NodalDispatchChart({ rows }: NodalDispatchChartProps) {
  const { t } = useT();
  const { data, seriesKeys } = useMemo(() => toNodalDispatchSeries(rows), [rows]);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{t("nodal.dispatchNoData")}</div>;
  }

  const legendItems: ChartLegendItem[] = seriesKeys.map((key, index) => ({
    key, name: key, color: PALETTE[index % PALETTE.length],
  }));

  const toggleSeries = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div>
      <div {...getWrapperProps()} ref={wrapperRef} title={t("chart.zoomHint")}
        className={cn("w-full", isZoomed ? "cursor-grab select-none active:cursor-grabbing" : "cursor-crosshair")}
        style={{ minHeight: 320 }}>
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={visibleData} margin={{ top: 8, right: 16, left: 8, bottom: 32 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="hour" tick={{ fill: "#a1a1aa" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{ value: t("chart.hour"), position: "bottom", offset: 8, fill: "#a1a1aa" }} />
            <YAxis tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: "#a1a1aa" }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={{ stroke: "rgba(255,255,255,0.1)" }}
              label={{ value: t("nodal.unitMw"), angle: -90, position: "insideLeft", fill: "#a1a1aa" }} />
            <Tooltip content={<ChartTooltip unit={t("nodal.unitMw")} hourLabel={t("chart.hourLabel")} />} />
            {seriesKeys.map((key, index) => (
              <Area key={key} type="monotone" dataKey={key} name={key} stackId="1"
                stroke={PALETTE[index % PALETTE.length]} fill={PALETTE[index % PALETTE.length]}
                fillOpacity={0.5} hide={hidden.has(key)} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {isZoomed && (
        <div className="mt-2 flex items-center justify-end gap-3 text-xs text-muted-foreground">
          <span className="hidden sm:inline">{t("chart.zoomHint")}</span>
          <button onClick={reset}
            className="rounded-full border border-zinc-700 px-3 py-1 text-zinc-200 hover:border-zinc-500">
            {t("chart.resetZoom")}
          </button>
        </div>
      )}
      <ChartLegend items={legendItems} hidden={hidden} onToggle={toggleSeries} />
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run nodal-dispatch-chart.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/nodal-dispatch-chart.tsx frontend/components/nodal/nodal-dispatch-chart.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add nodal dispatch chart"
```

---

### Task 12: `components/nodal/branch-flows-chart.tsx`

**Files:**
- Create: `frontend/components/nodal/branch-flows-chart.tsx`
- Test: `frontend/components/nodal/branch-flows-chart.test.tsx`

**Interfaces:**
- Consumes: `toBranchFlowSeries` from `@/lib/nodal-chart-data`; `BranchFlowRow`; the `LineChart` pattern from Task 10 (identical structure, unit `t("nodal.unitMw")`, empty state `t("nodal.branchFlowsNoData")`).
- Produces: `<BranchFlowsChart rows />` — line per branch over 24h with legend toggle and zoom.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/branch-flows-chart.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "@/lib/i18n-context";
import type { BranchFlowRow } from "@/lib/types";
import { BranchFlowsChart } from "./branch-flows-chart";

const ROWS: BranchFlowRow[] = [
  { timestamp: "2024-04-18 00:00", branch: "NC", flow_mw: 10 },
  { timestamp: "2024-04-18 01:00", branch: "NC", flow_mw: 15 },
  { timestamp: "2024-04-18 00:00", branch: "CS", flow_mw: -4 },
];

describe("BranchFlowsChart", () => {
  it("renders one line per branch", () => {
    const { container } = render(
      <I18nProvider><BranchFlowsChart rows={ROWS} /></I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><BranchFlowsChart rows={[]} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de flujos de rama/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run branch-flows-chart.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/branch-flows-chart.tsx` with the same structure as `price-curves-chart.tsx` from Task 10, substituting: `toBranchFlowSeries(rows)`, `LineChart` with one `<Line>` per branch (uniform `strokeWidth={2}`, no dash, no ReferenceLine), unit `t("nodal.unitMw")` for the Y-axis label and tooltip, and empty state `t("nodal.branchFlowsNoData")`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run branch-flows-chart.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/branch-flows-chart.tsx frontend/components/nodal/branch-flows-chart.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add branch flows chart"
```

---

### Task 13: `components/nodal/differential-table.tsx`

**Files:**
- Create: `frontend/components/nodal/differential-table.tsx`
- Test: `frontend/components/nodal/differential-table.test.tsx`

**Interfaces:**
- Consumes: `NodalRedistributionRow`, `NodalGenRevenueRow` from `@/lib/types`; `formatNumber` from `@/lib/chart-format`; `useT`; shadcn `Table`.
- Produces: `<DifferentialTable redistribution genRevenue />` — two tables: load payment A/B/delta per zone (delta emerald when ≤0, red when >0), and generation revenue A/B/delta per zone+fuel.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/differential-table.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "@/lib/i18n-context";
import type { NodalGenRevenueRow, NodalRedistributionRow } from "@/lib/types";
import { DifferentialTable } from "./differential-table";

const REDISTRIBUTION: NodalRedistributionRow[] = [
  { zone: "norte", load_payment_a: 100, load_payment_b: 120, delta: 20 },
  { zone: "sur", load_payment_a: 100, load_payment_b: 80, delta: -20 },
];
const GEN_REVENUE: NodalGenRevenueRow[] = [
  { zone: "norte", fuel: "hydro", revenue_a: 50, revenue_b: 70, delta: 20 },
];

describe("DifferentialTable", () => {
  it("renders load payment deltas per zone", () => {
    render(<I18nProvider><DifferentialTable redistribution={REDISTRIBUTION} genRevenue={GEN_REVENUE} /></I18nProvider>);
    expect(screen.getByText("norte")).toBeInTheDocument();
    expect(screen.getByText("sur")).toBeInTheDocument();
    expect(screen.getByText(/Pago demanda A/i)).toBeInTheDocument();
    expect(screen.getByText(/Delta/i)).toBeInTheDocument();
  });

  it("renders generation revenue per zone and fuel", () => {
    render(<I18nProvider><DifferentialTable redistribution={REDISTRIBUTION} genRevenue={GEN_REVENUE} /></I18nProvider>);
    expect(screen.getByText("hydro")).toBeInTheDocument();
    expect(screen.getByText(/Ingreso generacion A/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run differential-table.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/differential-table.tsx`:

```tsx
"use client";

import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import type { NodalGenRevenueRow, NodalRedistributionRow } from "@/lib/types";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

interface DifferentialTableProps {
  redistribution: NodalRedistributionRow[];
  genRevenue: NodalGenRevenueRow[];
}

function deltaClass(delta: number): string {
  return delta <= 0 ? "text-emerald-400" : "text-red-400";
}

export function DifferentialTable({ redistribution, genRevenue }: DifferentialTableProps) {
  const { t } = useT();
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium">{t("nodal.loadPaymentA")} / {t("nodal.loadPaymentB")}</p>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("nodal.zone")}</TableHead>
                <TableHead>{t("nodal.loadPaymentA")}</TableHead>
                <TableHead>{t("nodal.loadPaymentB")}</TableHead>
                <TableHead>{t("nodal.delta")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {redistribution.map((row) => (
                <TableRow key={row.zone}>
                  <TableCell className="font-medium">{row.zone}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.load_payment_a)}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.load_payment_b)}</TableCell>
                  <TableCell className={`tabular-nums ${deltaClass(row.delta)}`}>{formatNumber(row.delta)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium">{t("nodal.genRevenueA")} / {t("nodal.genRevenueB")}</p>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("nodal.zone")}</TableHead>
                <TableHead>{t("nodal.fuel")}</TableHead>
                <TableHead>{t("nodal.genRevenueA")}</TableHead>
                <TableHead>{t("nodal.genRevenueB")}</TableHead>
                <TableHead>{t("nodal.delta")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {genRevenue.map((row) => (
                <TableRow key={`${row.zone}-${row.fuel}`}>
                  <TableCell className="font-medium">{row.zone}</TableCell>
                  <TableCell>{row.fuel}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.revenue_a)}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(row.revenue_b)}</TableCell>
                  <TableCell className={`tabular-nums ${deltaClass(row.delta)}`}>{formatNumber(row.delta)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run differential-table.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/differential-table.tsx frontend/components/nodal/differential-table.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add differential table"
```

---

### Task 14: `components/nodal/redistribution-matrix.tsx`

**Files:**
- Create: `frontend/components/nodal/redistribution-matrix.tsx`
- Test: `frontend/components/nodal/redistribution-matrix.test.tsx`

**Interfaces:**
- Consumes: `NodalRedistributionRow`; `formatNumber`; `useT`.
- Produces: `<RedistributionMatrix rows />` — a diverging heatmap: one cell per zone, background interpolated emerald (negative delta) → red (positive delta), intensity by magnitude relative to the largest |delta|; neutral when delta ≈ 0.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/redistribution-matrix.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
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
    expect(screen.getByText(/Matriz de redistribucion/i)).toBeInTheDocument();
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run redistribution-matrix.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/redistribution-matrix.tsx`:

```tsx
"use client";

import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";
import type { NodalRedistributionRow } from "@/lib/types";

const EMERALD: [number, number, number] = [16, 185, 129];
const RED: [number, number, number] = [239, 68, 68];

function deltaColor(delta: number, maxAbs: number): string {
  if (maxAbs === 0 || delta === 0) return "rgba(63, 63, 70, 0.35)";
  const intensity = Math.min(1, Math.abs(delta) / maxAbs);
  const target = delta > 0 ? RED : EMERALD;
  const r = Math.round(63 + (target[0] - 63) * intensity);
  const g = Math.round(63 + (target[1] - 63) * intensity);
  const b = Math.round(70 + (target[2] - 70) * intensity);
  return `rgba(${r}, ${g}, ${b}, 0.55)`;
}

interface RedistributionMatrixProps { rows: NodalRedistributionRow[]; }

export function RedistributionMatrix({ rows }: RedistributionMatrixProps) {
  const { t } = useT();
  const maxAbs = Math.max(1, ...rows.map((row) => Math.abs(row.delta)));
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{t("nodal.redistributionSubtitle")}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((row) => (
          <div key={row.zone} data-zone={row.zone} data-delta={row.delta}
            className="rounded-lg border border-border p-3"
            style={{ backgroundColor: deltaColor(row.delta, maxAbs) }}>
            <p className="text-sm font-medium">{row.zone}</p>
            <p className="mt-1 font-mono text-sm tabular-nums">{formatNumber(row.delta)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run redistribution-matrix.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/redistribution-matrix.tsx frontend/components/nodal/redistribution-matrix.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add redistribution matrix"
```

---

### Task 15: `components/nodal/nodal-artifact-downloads.tsx`

**Files:**
- Create: `frontend/components/nodal/nodal-artifact-downloads.tsx`
- Test: `frontend/components/nodal/nodal-artifact-downloads.test.tsx`

**Interfaces:**
- Consumes: `downloadNodalArtifact` from `@/lib/api-client`; `NodalArtifactName`; `useT`; Button/Download icon (pattern: `components/artifact-downloads.tsx`).
- Produces: `<NodalArtifactDownloads runId artifacts />` — one download button per available nodal artifact (7), each downloading via `downloadNodalArtifact`; `.csv` extension except `summary` → `.json`; empty state `t("artifacts.noData")` when none available; error `role="alert"`.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/nodal-artifact-downloads.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
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
    expect(screen.getByText(/sin datos disponibles/i)).toBeInTheDocument();
  });
});
```

(Stub `URL.createObjectURL`/`URL.revokeObjectURL` via `vi.stubGlobal` if the click handler throws in jsdom — see `components/artifact-downloads.test.tsx` for the existing pattern if present.)

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run nodal-artifact-downloads.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/components/nodal/nodal-artifact-downloads.tsx` (mirror `artifact-downloads.tsx`):

```tsx
"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadNodalArtifact } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import type { NodalArtifactName } from "@/lib/types";

const NODAL_ARTIFACTS: { name: NodalArtifactName; labelKey: string; ext: string }[] = [
  { name: "lmp", labelKey: "nodal.artifact.lmp", ext: ".csv" },
  { name: "dispatch", labelKey: "nodal.artifact.dispatch", ext: ".csv" },
  { name: "branch_flows", labelKey: "nodal.artifact.branch_flows", ext: ".csv" },
  { name: "settlement_status_quo", labelKey: "nodal.artifact.settlement_status_quo", ext: ".csv" },
  { name: "settlement_lmp", labelKey: "nodal.artifact.settlement_lmp", ext: ".csv" },
  { name: "comparison", labelKey: "nodal.artifact.comparison", ext: ".csv" },
  { name: "summary", labelKey: "nodal.artifact.summary", ext: ".json" },
];

interface NodalArtifactDownloadsProps {
  runId: string;
  artifacts: Record<NodalArtifactName, boolean>;
}

export function NodalArtifactDownloads({ runId, artifacts }: NodalArtifactDownloadsProps) {
  const { t } = useT();
  const [error, setError] = useState<string | null>(null);
  const available = NODAL_ARTIFACTS.filter((artifact) => artifacts[artifact.name]);

  const handleDownload = async (name: NodalArtifactName, ext: string) => {
    try {
      setError(null);
      const blob = await downloadNodalArtifact(runId, name);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}-${runId}${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (available.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("artifacts.noData")}</p>;
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {available.map((artifact) => (
          <Button key={artifact.name} variant="outline" size="sm"
            onClick={() => handleDownload(artifact.name, artifact.ext)}>
            <Download className="size-3.5" />
            {t(artifact.labelKey)}
          </Button>
        ))}
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run nodal-artifact-downloads.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add frontend/components/nodal/nodal-artifact-downloads.tsx frontend/components/nodal/nodal-artifact-downloads.test.tsx
PYENV_VERSION=system git commit -m "feat(frontend): add nodal artifact downloads"
```

---

### Task 16: `/nodal` list page

**Files:**
- Create: `frontend/app/(app)/nodal/page.tsx`
- Test: `frontend/app/(app)/nodal/page.test.tsx`

**Interfaces:**
- Consumes: `listRuns` from `@/lib/api-client`; `formatBogotaTime`; `useT`; `useQuery`; shadcn Card/Table/Button; lucide `Network`; `Link`.
- Produces: `/nodal` — filters runs by `level === "lmp"`, shows one row per run (date, status pill, run_id mono, network name + chips `N zonas · M generadores · K ramas` from `run.nodal`, "Abrir dashboard" link only when `status === "done"` and `nodal` present), empty state when no LMP runs.

- [ ] **Step 1: Write the failing test**

Create `frontend/app/(app)/nodal/page.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "@/lib/i18n-context";
import { listRuns } from "@/lib/api-client";
import Page from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/nodal",
}));
vi.mock("@/lib/api-client", () => ({ listRuns: vi.fn() }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ session: null, loading: false, signOut: vi.fn() }),
}));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <I18nProvider>{children}</I18nProvider>
  </QueryClientProvider>
);

describe("Nodal list page", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.mocked(listRuns).mockResolvedValue([
      {
        run_id: "run-nodal-1", status: "done", dispatch_date: "2024-04-18",
        level: "lmp", scenario_id: null, created_at: "2024-04-18T12:00:00Z",
        started_at: null, finished_at: null, error: null,
        nodal: { network_name: "three_zone", zones: 3, generators: 3, branches: 2 },
      },
      {
        run_id: "run-classic-1", status: "done", dispatch_date: "2024-04-18",
        level: "preideal", scenario_id: null, created_at: "2024-04-18T11:00:00Z",
        started_at: null, finished_at: null, error: null, nodal: null,
      },
    ]);
  });

  it("lists only lmp runs", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("run-nodal-1")).toBeInTheDocument());
    expect(screen.queryByText("run-classic-1")).not.toBeInTheDocument();
  });

  it("shows network topology chips", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("three_zone")).toBeInTheDocument());
    expect(screen.getByText(/3 zonas/i)).toBeInTheDocument();
    expect(screen.getByText(/3 generadores/i)).toBeInTheDocument();
  });

  it("links done nodal runs to the dashboard", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Abrir dashboard/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Abrir dashboard/i })).toHaveAttribute(
      "href", "/runs/run-nodal-1/nodal",
    );
  });

  it("shows an empty state when there are no lmp runs", async () => {
    vi.mocked(listRuns).mockResolvedValue([]);
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/No hay corridas nodales aun/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run "nodal/page.test.tsx"`
Expected: FAIL — no test file / module not found.

- [ ] **Step 3: Implement**

Create `frontend/app/(app)/nodal/page.tsx` (follow `app/(app)/runs/page.tsx` structure):

```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Network } from "lucide-react";
import { listRuns } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import { formatBogotaTime } from "@/lib/format-date";
import type { RunStatus } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const STATUS_CLASSES: Record<RunStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  running: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  done: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border border-red-500/20",
};

export default function NodalPage() {
  const { t } = useT();
  const { data: runs, isLoading, isError } = useQuery({ queryKey: ["runs"], queryFn: listRuns });
  const nodalRuns = (runs ?? []).filter((run) => run.level === "lmp");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("nodal.listTitle")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("nodal.listSubtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.listTitle")}</CardTitle>
          <CardDescription>{t("nodal.listSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">{t("runs.loading")}</p>}
          {isError && (
            <p role="alert" className="py-8 text-center text-sm text-red-400">{t("runs.loadError")}</p>
          )}
          {!isLoading && !isError && nodalRuns.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <Network className="size-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">{t("nodal.noRuns")}</p>
              <p className="text-xs text-muted-foreground">{t("nodal.noRunsHint")}</p>
            </div>
          )}
          {nodalRuns.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("runsTable.date")}</TableHead>
                    <TableHead>{t("runsTable.status")}</TableHead>
                    <TableHead>Run ID</TableHead>
                    <TableHead>{t("nodal.networkName")}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {nodalRuns.map((run) => (
                    <TableRow key={run.run_id}>
                      <TableCell>{formatBogotaTime(run.created_at)}</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs ${STATUS_CLASSES[run.status]}`}>
                          {t(`status.${run.status}`)}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{run.run_id}</TableCell>
                      <TableCell>
                        {run.nodal ? (
                          <div className="space-y-1">
                            <p className="text-sm font-medium">{run.nodal.network_name ?? "—"}</p>
                            <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                              <span>{run.nodal.zones} {t("nodal.zone")}</span>
                              <span>·</span>
                              <span>{run.nodal.generators} {t("nodal.generator")}</span>
                              <span>·</span>
                              <span>{run.nodal.branches} {t("nodal.branch")}</span>
                            </div>
                          </div>
                        ) : (
                          <span className="text-sm text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {run.status === "done" && run.nodal && (
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/runs/${run.run_id}/nodal`}>
                              <Network className="size-3.5" />
                              {t("nodal.openDashboard")}
                            </Link>
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

Check `app/(app)/runs/page.tsx` for the exact loading/error i18n keys (`runs.loading`, `runs.loadError`) and table header keys (`runsTable.date`, `runsTable.status`) and reuse the existing ones — adjust the keys above and the test if the existing file names them differently. If the repo's `Button` does not support `asChild`, render `<Link>` directly with the button classes instead.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- --run "nodal/page.test.tsx"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYENV_VERSION=system git add "frontend/app/(app)/nodal/page.tsx" "frontend/app/(app)/nodal/page.test.tsx"
PYENV_VERSION=system git commit -m "feat(frontend): add nodal runs list page"
```

---

### Task 17: `/runs/[id]/nodal` dashboard page + run-detail link

**Files:**
- Create: `frontend/app/(app)/runs/[id]/nodal/page.tsx`
- Create: `frontend/app/(app)/runs/[id]/nodal/page.test.tsx`
- Modify: `frontend/app/(app)/runs/[id]/page.tsx` (add link to the nodal dashboard when `data.nodal` exists)
- Modify: `frontend/app/(app)/runs/[id]/page.test.tsx` (extend: link renders only when nodal present)

**Interfaces:**
- Consumes: `useRunDetail` from `@/hooks/use-run-detail`; `getRunNodalArtifact` from `@/lib/api-client`; the 6 nodal components from Tasks 8–15; `useT`; `STATUS_CLASSES` pattern; shadcn Card.
- Produces: `/runs/{id}/nodal` — header (back link, run_id, date + `lmp` badge, timestamp, status pill), hour selector (native `<select>` 0–23), metric card grid, zonal map + network card, price curves, dispatch + branch flows, differential table, redistribution matrix, downloads. Fetches `lmp`/`dispatch`/`branch_flows` artifacts via react-query with `enabled: Boolean(nodal?.artifacts.<name>)`. Empty state when run has no nodal data. Error `role="alert"`.

- [ ] **Step 1: Write the failing test**

Create `frontend/app/(app)/runs/[id]/nodal/page.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "@/lib/i18n-context";
import { getRun, getRunNodalArtifact } from "@/lib/api-client";
import type { RunDetail } from "@/lib/types";
import Page from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "run-1" }),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/runs/run-1/nodal",
}));
vi.mock("@/lib/api-client", () => ({
  getRun: vi.fn(), getRunNodalArtifact: vi.fn(), listRuns: vi.fn(),
}));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ session: null, loading: false, signOut: vi.fn() }),
}));

const NODAL_RUN: RunDetail = {
  run_id: "run-1", status: "done", dispatch_date: "2024-04-18", level: "lmp",
  scenario_id: null, created_at: "2024-04-18T12:00:00Z", started_at: null,
  finished_at: null, error: null,
  metrics: null,
  artifacts: { dispatch: false, prices: false, bess: false, marginal_plants: false },
  price_series: null,
  nodal: {
    metrics: {
      total_cost: 100000, load_payment_delta: 5000, gen_revenue_delta: -2000,
      congestion_rent_total: 7200, price_avg_norte: 90, price_avg_sur: 110,
      price_vol_norte: 5, price_vol_sur: 8,
    },
    redistribution: [
      { zone: "norte", load_payment_a: 100, load_payment_b: 120, delta: 20 },
      { zone: "sur", load_payment_a: 100, load_payment_b: 80, delta: -20 },
    ],
    gen_revenue_by_zone: [{ zone: "norte", fuel: "hydro", revenue_a: 50, revenue_b: 70, delta: 20 }],
    network: {
      name: "three_zone", baseMVA: 100, reference_zone: "norte",
      zones: [{ name: "norte", base_kv: 230 }, { name: "sur", base_kv: 230 }],
      generators: [
        { name: "G_N", zone: "norte", p_min: 0, p_max: 500, marginal_cost: 20,
          no_load_cost: 0, fuel: "hydro", min_up_time: 1, min_down_time: 1,
          initial_status: 1, ramp_rate: null },
      ],
      branches: [{ name: "NC", from_zone: "norte", to_zone: "sur", reactance: 0.1, rating: 120 }],
      loads: [], demand_shares: { norte: 0.5, sur: 0.5 },
    },
    artifacts: {
      lmp: true, dispatch: true, branch_flows: true, settlement_status_quo: true,
      settlement_lmp: true, comparison: true, summary: true,
    },
  },
};

const LMP_ROWS = Array.from({ length: 24 }, (_, hour) => [
  { timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`, bus: "norte", lmp: 20 + hour },
  { timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`, bus: "sur", lmp: 30 + hour },
]).flat();

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <I18nProvider>{children}</I18nProvider>
  </QueryClientProvider>
);

describe("Nodal dashboard page", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.mocked(getRun).mockResolvedValue(NODAL_RUN);
    vi.mocked(getRunNodalArtifact).mockImplementation((_id, artifact) => {
      if (artifact === "lmp") return Promise.resolve(LMP_ROWS);
      if (artifact === "dispatch")
        return Promise.resolve([
          { generator: "G_N", zone: "norte", fuel: "hydro", hour: 0, dispatch_mw: 100 },
        ]);
      return Promise.resolve([{ timestamp: "2024-04-18 00:00", branch: "NC", flow_mw: 10 }]);
    });
  });

  it("renders the header and metric cards", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText("run-1")).toBeInTheDocument());
    expect(screen.getByText(/Costo total/i)).toBeInTheDocument();
    expect(screen.getByText(/Delta pago demanda/i)).toBeInTheDocument();
    expect(screen.getByText(/Renta de congestion/i)).toBeInTheDocument();
  });

  it("renders the zonal map and network card", async () => {
    const { container } = render(<Page />, { wrapper });
    await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    expect(screen.getByText(/Red utilizada/i)).toBeInTheDocument();
    expect(screen.getByText("three_zone")).toBeInTheDocument();
  });

  it("renders the price curves, dispatch and branch flows charts", async () => {
    const { container } = render(<Page />, { wrapper });
    await waitFor(() => {
      expect(container.querySelectorAll(".recharts-wrapper, svg").length).toBeGreaterThanOrEqual(3);
    });
  });

  it("shows the differential table and redistribution matrix", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Tabla de diferencial/i)).toBeInTheDocument());
    expect(screen.getByText(/Matriz de redistribucion/i)).toBeInTheDocument();
    expect(screen.getByText("norte")).toBeInTheDocument();
  });

  it("changes the selected hour via the selector", async () => {
    render(<Page />, { wrapper });
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "3" } });
    expect(screen.getByRole("combobox")).toHaveValue("3");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `pnpm test -- --run "runs/[id]/nodal/page.test.tsx"`
Expected: FAIL — no test file / module not found.

- [ ] **Step 3: Implement the dashboard page**

Create `frontend/app/(app)/runs/[id]/nodal/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowDownUp, Coins, Loader2, TrendingUp, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useT } from "@/lib/i18n-context";
import { useRunDetail } from "@/hooks/use-run-detail";
import { getRunNodalArtifact } from "@/lib/api-client";
import { formatNumber } from "@/lib/chart-format";
import { formatBogotaTime } from "@/lib/format-date";
import type { BranchFlowRow, LmpRow, NodalDispatchRow, RunStatus } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { NetworkCard } from "@/components/nodal/network-card";
import { ZonalMap } from "@/components/nodal/zonal-map";
import { PriceCurvesChart } from "@/components/nodal/price-curves-chart";
import { NodalDispatchChart } from "@/components/nodal/nodal-dispatch-chart";
import { BranchFlowsChart } from "@/components/nodal/branch-flows-chart";
import { DifferentialTable } from "@/components/nodal/differential-table";
import { RedistributionMatrix } from "@/components/nodal/redistribution-matrix";
import { NodalArtifactDownloads } from "@/components/nodal/nodal-artifact-downloads";

const STATUS_CLASSES: Record<RunStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  running: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  done: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border border-red-500/20",
};

interface MetricCardProps { label: string; value: string; icon: LucideIcon; }

function MetricCard({ label, value, icon: Icon }: MetricCardProps) {
  return (
    <Card size="sm">
      <CardContent className="py-3">
        <Icon className="size-4 text-muted-foreground" />
        <p className="mt-2 text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 font-heading text-lg font-bold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

export default function NodalDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useT();
  const run = useRunDetail(id);
  const [hour, setHour] = useState(0);
  const nodal = run.data?.nodal ?? null;

  const lmpQuery = useQuery({
    queryKey: ["nodal-lmp", id],
    queryFn: () => getRunNodalArtifact<LmpRow[]>(id, "lmp"),
    enabled: Boolean(nodal?.artifacts.lmp),
  });
  const dispatchQuery = useQuery({
    queryKey: ["nodal-dispatch", id],
    queryFn: () => getRunNodalArtifact<NodalDispatchRow[]>(id, "dispatch"),
    enabled: Boolean(nodal?.artifacts.dispatch),
  });
  const branchFlowsQuery = useQuery({
    queryKey: ["nodal-branch_flows", id],
    queryFn: () => getRunNodalArtifact<BranchFlowRow[]>(id, "branch_flows"),
    enabled: Boolean(nodal?.artifacts.branch_flows),
  });

  if (run.isLoading) {
    return (
      <div className="flex items-center gap-3 py-12 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> {t("runDetail.loading")}
      </div>
    );
  }
  if (run.isError || !run.data || !nodal) {
    return (
      <Card className="border-red-500/20 bg-red-500/5">
        <CardContent className="py-6">
          <p role="alert" className="text-sm text-red-400">{t("nodal.noNodalData")}</p>
        </CardContent>
      </Card>
    );
  }

  const { metrics } = nodal;
  const priceAvgKeys = Object.keys(metrics).filter((key) => key.startsWith("price_avg_"));
  const priceVolKeys = Object.keys(metrics).filter((key) => key.startsWith("price_vol_"));

  const metricCards: MetricCardProps[] = [
    { label: t("nodal.totalCost"), value: formatNumber(metrics.total_cost), icon: Wallet },
    { label: t("nodal.loadPaymentDelta"), value: formatNumber(metrics.load_payment_delta), icon: ArrowDownUp },
    { label: t("nodal.genRevenueDelta"), value: formatNumber(metrics.gen_revenue_delta), icon: TrendingUp },
    { label: t("nodal.congestionRent"), value: formatNumber(metrics.congestion_rent_total), icon: Coins },
    ...priceAvgKeys.map((key) => ({
      label: `${t("nodal.priceAvg")} ${key.replace("price_avg_", "")}`,
      value: formatNumber(metrics[key]),
      icon: Wallet,
    })),
    ...priceVolKeys.map((key) => ({
      label: `${t("nodal.priceVol")} ${key.replace("price_vol_", "")}`,
      value: formatNumber(metrics[key]),
      icon: TrendingUp,
    })),
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 py-4">
          <Button asChild variant="ghost" size="sm">
            <Link href={`/runs/${id}`}>
              <ArrowLeft className="size-4" /> {t("nodal.backToRun")}
            </Link>
          </Button>
          <div className="min-w-0">
            <p className="truncate font-mono text-xs text-muted-foreground">{run.data.run_id}</p>
            <h1 className="font-heading text-xl font-bold">
              {run.data.dispatch_date}
              <span className="ml-2 text-sm font-normal text-muted-foreground">{run.data.level}</span>
            </h1>
            <p className="text-xs text-muted-foreground">{formatBogotaTime(run.data.created_at)}</p>
          </div>
          <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs ${STATUS_CLASSES[run.data.status]}`}>
            {t(`status.${run.data.status}`)}
          </span>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-heading text-lg font-bold">{t("nodal.hour")}</h2>
          <select
            aria-label={t("nodal.hour")}
            value={hour}
            onChange={(e) => setHour(Number(e.target.value))}
            className="mt-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          >
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>{h}:00</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {metricCards.map((card) => (
          <MetricCard key={card.label} {...card} />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("nodal.mapTitle")}</CardTitle>
            <CardDescription>{t("nodal.mapSubtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ZonalMap
              zones={nodal.network.zones}
              branches={nodal.network.branches}
              generators={nodal.network.generators}
              lmpRows={lmpQuery.data ?? []}
              hour={hour}
            />
          </CardContent>
        </Card>
        <NetworkCard network={nodal.network} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.priceCurvesTitle")}</CardTitle>
          <CardDescription>{t("nodal.priceCurvesSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <PriceCurvesChart rows={lmpQuery.data ?? []} referenceZone={nodal.network.reference_zone} hour={hour} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("nodal.dispatchTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <NodalDispatchChart rows={dispatchQuery.data ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("nodal.branchFlowsTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <BranchFlowsChart rows={branchFlowsQuery.data ?? []} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.differentialTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <DifferentialTable redistribution={nodal.redistribution} genRevenue={nodal.gen_revenue_by_zone} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.redistributionTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <RedistributionMatrix rows={nodal.redistribution} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.downloadsTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <NodalArtifactDownloads runId={id} artifacts={nodal.artifacts} />
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Add the run-detail link**

In `frontend/app/(app)/runs/[id]/page.tsx`, in the header Card, when `data.nodal` exists add a link to the nodal dashboard. Reuse the `Button asChild` + `Link` pattern:

```tsx
{data.nodal && (
  <Button asChild variant="outline" size="sm">
    <Link href={`/runs/${id}/nodal`}>{t("nodal.openDashboard")}</Link>
  </Button>
)}
```

Add `Link` from `next/link` and `Button` to the imports if not already present. Extend `frontend/app/(app)/runs/[id]/page.test.tsx` (create it if the file does not exist — there is currently no test for that route): mock `getRun` from `@/lib/api-client` with a `RunDetail` that has `nodal` set, render in `QueryClientProvider` + `I18nProvider`, and assert `screen.getByRole("link", { name: /Abrir dashboard/i })` has `href="/runs/run-1/nodal"`. Also test the negative: with `nodal: null`, the link is absent (`queryByRole` returns null).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pnpm test -- --run "runs/[id]/nodal/page.test.tsx" "runs/[id]/page.test.tsx"`
Expected: PASS.

- [ ] **Step 6: Full frontend gates**

Run: `pnpm lint` then `pnpm test` then `pnpm exec tsc --noEmit`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
PYENV_VERSION=system git add "frontend/app/(app)/runs/[id]/nodal/page.tsx" "frontend/app/(app)/runs/[id]/nodal/page.test.tsx" "frontend/app/(app)/runs/[id]/page.tsx" "frontend/app/(app)/runs/[id]/page.test.tsx"
PYENV_VERSION=system git commit -m "feat(frontend): add nodal dashboard page"
```

---

## Final Integration & Verification

**Files:** repo root + `frontend/`

- [ ] **Step 1: Backend gates**

Run (from repo root): `uv run pytest -q && uv run ruff check && uv run ruff format --check`
Expected: all pass.

- [ ] **Step 2: Frontend gates**

Run (from `frontend/`): `pnpm lint && pnpm test && pnpm exec tsc --noEmit`
Expected: all pass.

- [ ] **Step 3: End-to-end smoke against the real API (optional, requires local env)**

Run the API (see `services/api/README` or the Fase 2 spec) plus the frontend dev server, then:
1. `GET /runs` returns `nodal` for a done LMP run and `null` for classic runs.
2. `/nodal` lists only LMP runs with topology chips.
3. A done LMP run's detail page shows the "Análisis nodal" link; the dashboard renders map, curves, dispatch, flows, tables, matrix, and downloads.

- [ ] **Step 4: Commit any integration fixes on the branch** (conventional message; no AI attribution).

---

## Self-Review Checklist (run by the plan author before handoff)

- [ ] **Spec coverage:** Every section of `2026-08-18-lmp-nodal-frontend-design.md` maps to a task — `GET /runs` enrichment → Task 1; types → Task 2; api-client → Task 3; lib layout/color → Task 4; chart data transforms → Task 5; i18n → Task 6; sidebar → Task 7; network card → Task 8; zonal map → Task 9; price curves → Task 10; dispatch → Task 11; branch flows → Task 12; differential table → Task 13; redistribution matrix → Task 14; downloads → Task 15; `/nodal` page → Task 16; dashboard + run-detail link → Task 17.
- [ ] **Placeholder scan:** no TBD/TODO; every code step contains full code.
- [ ] **Type consistency:** `NodalArtifactName` values match the backend `_NODAL_ARTIFACT_PATHS` keys (`lmp`, `dispatch`, `branch_flows`, `settlement_status_quo`, `settlement_lmp`, `comparison`, `summary`); `NodalMetrics` keys match `compare.py` (`total_cost`, `load_payment_delta`, `gen_revenue_delta`, `congestion_rent_total`, `price_avg_*`, `price_vol_*`); component prop names used in Task 17 match the props defined in Tasks 8–15.