# LMP Weighted-Average Price + Congestion Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute a demand-weighted average price ("precio promedio ponderado") and per-zone congestion for `level=lmp` runs from data the engine already produces (`NodalSolution.lmp`, `.loads`), fix the status-quo settlement bug that currently uses an arbitrary reference-zone LMP instead, and add a comparison of the weighted-average price against the real bolsa price (`PrecBolsNaci`), mirroring what already exists for `level=ideal`.

**Architecture:** Pure post-processing on top of the existing (unmodified) EGRET btheta dispatch — `app/nodal/engine/pricing.py` computes `lmp_avg[t] = Σ(lmp[zone][t]·load[zone][t]) / Σload[zone][t]` and `lmp_congestion[zone][t] = lmp[zone][t] − lmp_avg[t]` from `NodalSolution.lmp`/`.loads`, called once at the end of `EgretNodalEngine.solve()`. Carried through `NodalSolution` → `status_quo.py` (fixes a real settlement bug) → `reporting.py` (extra columns on the existing `lmp.csv` artifact) → API (`load_reference_price` gains an `lmp` branch, reused by a new nodal price-comparison helper) → frontend (new "precio promedio" line decoupled from `referenceZone`, new congestion chart, reused `PriceSeriesChart` for the bolsa comparison).

**Correction from the first draft of this plan:** an earlier version of this plan switched the engine's per-hour DCOPF from btheta to EGRET's PTDF formulation to get its native `LMP = LMPE + LMPC` decomposition. That was verified wrong *before* implementation: `egret/data/ptdf_utils.py:576` (`return self._insert_reference_bus(LMP, LMPE)`) defines the reference bus's LMP as `LMPE` by construction, not because that bus is economically congestion-free — so `LMPE == λ_reference_zone`, the exact same arbitrary quantity as the original bug, confirmed empirically by varying `reference_zone` on the unmodified engine (`lmp[norte]`/`lmp[centro]` stay 20.0/80.0 regardless of which zone is `reference_zone`; only which one gets exposed as `lmp[reference_zone]` changes). This plan therefore does **not** touch the EGRET engine's dispatch formulation at all — the weighted-average price is pure post-processing, and the engine-formulation-change risk from the first draft is gone entirely.

**Tech Stack:** Python (backend engine, pure functions — no Pyomo/EGRET API surface touched), FastAPI (`services/api/main.py`), Next.js/React/Recharts/Vitest (frontend), pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-lmp-energia-congestion-design.md`

## Global Constraints

- Backend gates: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`.
- Frontend gates: `pnpm lint`, `pnpm test` (run from `frontend/`).
- No `Co-Authored-By` or AI attribution in any commit message, ever.
- Work happens on a feature branch (`fase6g-lmp-precio-promedio` or similar) off `develop`; no direct commits to `develop` for code changes (spec/plan docs are the only exception already committed).
- No backfill of existing LMP runs — they're test data and get discarded (confirmed by user).
- DC-OPF stays lossless; no loss term is introduced by this work. The EGRET dispatch formulation (`btheta_power_flow`) is not changed by any task in this plan.
- Naming: the computed quantity is called **"precio promedio ponderado"** (weighted-average price) everywhere user-visible — never "precio único" or "LMPE". Code identifiers use `lmp_avg` / `avg_price` / `avgPrice`.

---

## Task 1: `app/nodal/engine/pricing.py` — demand-weighted average price + congestion

**Files:**
- Create: `app/nodal/engine/pricing.py`
- Modify: `app/nodal/engine/base.py`
- Modify: `app/nodal/engine/egret_engine.py`
- Test: `tests/test_nodal_pricing.py` (new)
- Test: `tests/test_nodal_egret_engine.py`

**Interfaces:**
- Produces: `demand_weighted_average_price(lmp, loads, buses, n_hours) -> list[float]`. `congestion_component(lmp, avg_price, buses, n_hours) -> dict[str, list[float]]`. `NodalSolution.lmp_avg: list[float]`, `NodalSolution.lmp_congestion: dict[str, list[float]]`.
- Consumes: nothing new — `EgretNodalEngine().solve(net, ...)` keeps its existing signature; `dispatch`/`branch_flows`/`total_cost`/`lmp` are all unchanged (this task adds fields, it never modifies dispatch logic).

- [ ] **Step 1: Write the failing unit tests for the pure functions**

Create `tests/test_nodal_pricing.py`:

```python
import math

from app.nodal.engine.pricing import congestion_component, demand_weighted_average_price


def test_demand_weighted_average_equal_loads_is_simple_average():
    lmp = {"norte": [20.0], "centro": [80.0], "sur": [80.0]}
    loads = {"norte": [100.0], "centro": [100.0], "sur": [100.0]}
    avg = demand_weighted_average_price(lmp, loads, ["norte", "centro", "sur"], 1)
    assert math.isclose(avg[0], 60.0, abs_tol=1e-9)


def test_demand_weighted_average_weights_by_load():
    lmp = {"norte": [20.0], "centro": [80.0]}
    loads = {"norte": [300.0], "centro": [100.0]}
    avg = demand_weighted_average_price(lmp, loads, ["norte", "centro"], 1)
    # (20*300 + 80*100) / 400 = 35.0
    assert math.isclose(avg[0], 35.0, abs_tol=1e-9)


def test_congestion_component_identity_and_zero_sum():
    lmp = {"norte": [20.0], "centro": [80.0], "sur": [80.0]}
    loads = {"norte": [100.0], "centro": [100.0], "sur": [100.0]}
    avg = demand_weighted_average_price(lmp, loads, ["norte", "centro", "sur"], 1)
    congestion = congestion_component(lmp, avg, ["norte", "centro", "sur"], 1)
    assert math.isclose(congestion["norte"][0], -40.0, abs_tol=1e-9)
    assert math.isclose(congestion["centro"][0], 20.0, abs_tol=1e-9)
    assert math.isclose(congestion["sur"][0], 20.0, abs_tol=1e-9)
    # load-weighted congestion sums to zero -- pure redistribution
    weighted_sum = sum(loads[b][0] * congestion[b][0] for b in ("norte", "centro", "sur"))
    assert math.isclose(weighted_sum, 0.0, abs_tol=1e-6)
    # identity: lmp == avg + congestion, per bus
    for b in ("norte", "centro", "sur"):
        assert math.isclose(lmp[b][0], avg[0] + congestion[b][0], abs_tol=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_nodal_pricing.py -v`
Expected: FAILS with `ModuleNotFoundError: No module named 'app.nodal.engine.pricing'`.

- [ ] **Step 3: Implement `pricing.py`**

Create `app/nodal/engine/pricing.py`:

```python
from __future__ import annotations


def demand_weighted_average_price(
    lmp: dict[str, list[float]],
    loads: dict[str, list[float]],
    buses: list[str],
    n_hours: int,
) -> list[float]:
    return [
        sum(lmp[b][t] * loads[b][t] for b in buses) / sum(loads[b][t] for b in buses)
        for t in range(n_hours)
    ]


def congestion_component(
    lmp: dict[str, list[float]],
    avg_price: list[float],
    buses: list[str],
    n_hours: int,
) -> dict[str, list[float]]:
    return {b: [lmp[b][t] - avg_price[t] for t in range(n_hours)] for b in buses}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_nodal_pricing.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Add the fields to `NodalSolution`**

In `app/nodal/engine/base.py`, add two fields to the dataclass (after `lmp`, before `dispatch`):

```python
@dataclass
class NodalSolution:
    timestamps: list[str]
    buses: list[str]
    reference_zone: str
    lmp: dict[str, list[float]]
    lmp_avg: list[float]
    lmp_congestion: dict[str, list[float]]
    dispatch: dict[str, list[float]]
    loads: dict[str, list[float]]
    branch_flows: dict[str, list[float]]
    commitment: dict[str, list[float]]
    gen_cost: dict[str, list[float]]
    gen_zone: dict[str, str]
    gen_fuel: dict[str, str]
    total_cost: float
    uc_total_cost: float | None = None
```

- [ ] **Step 6: Write the failing engine-level test**

Add to `tests/test_nodal_egret_engine.py`:

```python
def test_congested_lmp_avg_and_congestion_are_load_weighted():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True), use_unit_commitment=False
    )
    t = 0
    assert math.isclose(sol.lmp_avg[t], 60.0, abs_tol=1e-6)
    assert math.isclose(sol.lmp_congestion["norte"][t], -40.0, abs_tol=1e-4)
    assert math.isclose(sol.lmp_congestion["centro"][t], 20.0, abs_tol=1e-4)
    assert math.isclose(sol.lmp_congestion["sur"][t], 20.0, abs_tol=1e-4)
    for bus in sol.buses:
        for h in range(24):
            assert math.isclose(
                sol.lmp[bus][h], sol.lmp_avg[h] + sol.lmp_congestion[bus][h], abs_tol=1e-6
            )


def test_uncongested_lmp_avg_equals_lmp_no_congestion():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=False), use_unit_commitment=False
    )
    for t in range(24):
        assert math.isclose(sol.lmp_avg[t], 20.0, abs_tol=1e-6)
        for bus in sol.buses:
            assert math.isclose(sol.lmp_congestion[bus][t], 0.0, abs_tol=1e-6)
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/test_nodal_egret_engine.py -v`
Expected: the 2 new tests FAIL with `AttributeError: 'NodalSolution' object has no attribute 'lmp_avg'`. The pre-existing 3 tests still PASS.

- [ ] **Step 8: Wire the computation into `EgretNodalEngine.solve()`**

In `app/nodal/engine/egret_engine.py`, add the import:

```python
from app.nodal.engine.pricing import congestion_component, demand_weighted_average_price
```

Immediately before the existing `total_cost = sum(sum(v) for v in gen_cost.values())` line, insert:

```python
        zone_names = [z.name for z in net.zones]
        lmp_avg = demand_weighted_average_price(lmp, loads, zone_names, len(time_keys))
        lmp_congestion = congestion_component(lmp, lmp_avg, zone_names, len(time_keys))

```

Then add the two fields to the `NodalSolution(...)` construction (after `lmp=lmp,`):

```python
        return NodalSolution(
            timestamps=time_keys,
            buses=[z.name for z in net.zones],
            reference_zone=net.reference_zone,
            lmp=lmp,
            lmp_avg=lmp_avg,
            lmp_congestion=lmp_congestion,
            dispatch=dispatch,
            ...
```

(keep every other line of the constructor call exactly as it is today — only the two new keyword arguments are added).

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_nodal_egret_engine.py tests/test_nodal_pricing.py -v`
Expected: all 8 tests PASS (2 new engine tests, 3 pre-existing engine tests confirming `dispatch`/`total_cost`/`branch_flows`/`lmp` are byte-for-byte unchanged, 3 pricing unit tests).

- [ ] **Step 10: Commit**

```bash
git add app/nodal/engine/pricing.py app/nodal/engine/base.py app/nodal/engine/egret_engine.py tests/test_nodal_pricing.py tests/test_nodal_egret_engine.py
git commit -m "feat(nodal): add demand-weighted average price and per-zone congestion as pure post-processing"
```

---

## Task 2: Fix status-quo settlement to use the weighted-average price

**Files:**
- Modify: `app/nodal/settlement/status_quo.py`
- Modify: `tests/fixtures/nodal.py`
- Test: `tests/test_nodal_settlement_status_quo.py`

**Interfaces:**
- Consumes: `NodalSolution.lmp_avg` (Task 1).
- Produces: no new public interface — `settle_status_quo(sol)` keeps its existing signature and `Settlement` shape; only `energy_price`'s values change (now correct and reference-zone-independent).

- [ ] **Step 1: Add a `reference_zone` override to the test fixture**

In `tests/fixtures/nodal.py`, add an optional keyword so a test can put the angle reference bus somewhere other than the cheap zone, proving the fix doesn't depend on that choice:

```python
def make_three_zone_network(*, congested: bool = False, reference_zone: str = "norte") -> NodalNetwork:
    rating = 120.0 if congested else 400.0
    return NodalNetwork(
        name="three_zone",
        baseMVA=100.0,
        reference_zone=reference_zone,
        zones=[Zone(name="norte"), Zone(name="centro"), Zone(name="sur")],
```

(Only the `reference_zone=` line and the function signature change — the rest of the body is unchanged.)

- [ ] **Step 2: Write the failing test**

Add to `tests/test_nodal_settlement_status_quo.py`:

```python
def test_status_quo_energy_price_independent_of_reference_zone_choice():
    # "centro" is the expensive, congested zone (marginal cost 80) -- under
    # the old bug (energy_price = lmp[reference_zone]) this would have
    # wrongly reported 80.0. The weighted-average price is 60.0 (equal
    # 100 MW loads in all three zones -> simple average of 20/80/80)
    # regardless of which zone is picked as the DC-OPF angle reference.
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True, reference_zone="centro"),
        use_unit_commitment=False,
    )
    s = settle_status_quo(sol)
    assert math.isclose(s.energy_price[0], 60.0, abs_tol=1e-6)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_nodal_settlement_status_quo.py -v`
Expected: FAILS — `s.energy_price[0]` is `80.0` (today's `sol.lmp[sol.reference_zone][0]` with `reference_zone="centro"`), not `60.0`.

- [ ] **Step 4: Fix `settle_status_quo`**

In `app/nodal/settlement/status_quo.py`, replace:

```python
    energy_price = [sol.lmp[sol.reference_zone][t] for t in range(n)]
```

with:

```python
    energy_price = list(sol.lmp_avg)
```

- [ ] **Step 5: Update the pre-existing congested test — it hardcodes the old (buggy) price**

`test_status_quo_congested_hour_zero` currently asserts `energy_price[0] == 20.0` (the old `lmp[reference_zone]` value, `reference_zone="norte"` by default). Under the fix it's `60.0` (the weighted average — this fixture's loads are 100 MW in all three zones, so `(20+80+80)/3 = 60`; this is independent of which zone is `reference_zone`, so the default-fixture test changes too, not just the new one from Step 2). Every downstream assertion that multiplies by the old `20` must change to `60`. In `tests/test_nodal_settlement_status_quo.py`, replace the body of `test_status_quo_congested_hour_zero` (keep the function signature and the `sol`/`s`/`t` setup lines unchanged) from:

```python
    assert math.isclose(s.energy_price[t], 20.0)
    assert math.isclose(s.congestion_rent[t], 7200.0, abs_tol=1e-4)
    assert math.isclose(s.uplift[t], 7200.0, abs_tol=1e-4)
    # uplift split by load share (100/300 each zone)
    assert math.isclose(s.zone_load_payment["norte"][t], 20 * 100 + 7200 * 100 / 300, abs_tol=1e-4)
    assert math.isclose(s.zone_load_payment["centro"][t], 20 * 100 + 7200 * 100 / 300, abs_tol=1e-4)
    # generation paid the single price
    assert math.isclose(s.gen_revenue["G_N"][t], 20 * 220, abs_tol=1e-4)
    assert math.isclose(s.gen_revenue["G_C"][t], 20 * 80, abs_tol=1e-4)
    # identity: load payments == gen revenue + congestion rent
    assert math.isclose(s.total_load_payment, s.total_gen_revenue + 24 * 7200, rel_tol=1e-6)
```

to:

```python
    assert math.isclose(s.energy_price[t], 60.0)
    assert math.isclose(s.congestion_rent[t], 7200.0, abs_tol=1e-4)
    assert math.isclose(s.uplift[t], 7200.0, abs_tol=1e-4)
    # uplift split by load share (100/300 each zone)
    assert math.isclose(s.zone_load_payment["norte"][t], 60 * 100 + 7200 * 100 / 300, abs_tol=1e-4)
    assert math.isclose(s.zone_load_payment["centro"][t], 60 * 100 + 7200 * 100 / 300, abs_tol=1e-4)
    # generation paid the weighted-average price
    assert math.isclose(s.gen_revenue["G_N"][t], 60 * 220, abs_tol=1e-4)
    assert math.isclose(s.gen_revenue["G_C"][t], 60 * 80, abs_tol=1e-4)
    # identity: load payments == gen revenue + congestion rent (price-level independent)
    assert math.isclose(s.total_load_payment, s.total_gen_revenue + 24 * 7200, rel_tol=1e-6)
```

`test_status_quo_uncongested` needs no change — uncongested LMP is 20.0 everywhere, so the weighted average is still 20.0, identical to the old `lmp[reference_zone]` value.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_nodal_settlement_status_quo.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/nodal/settlement/status_quo.py tests/fixtures/nodal.py tests/test_nodal_settlement_status_quo.py
git commit -m "fix(nodal): status-quo settlement uses the demand-weighted average price, not an arbitrary reference-zone LMP"
```

---

## Task 3: Persist `lmp_avg`/`lmp_congestion` on the existing `lmp.csv` artifact

**Files:**
- Modify: `app/nodal/reporting.py`
- Test: `tests/test_nodal_reporting.py`

**Interfaces:**
- Consumes: `NodalSolution.lmp_avg`, `NodalSolution.lmp_congestion` (Task 1).
- Produces: `lmp.csv` (via `save_nodal_artifacts`) gains two columns, `lmp_avg` and `lmp_congestion`, alongside the existing `timestamp,bus,lmp`. No new artifact file, no new `NodalResult` DB column — same `lmp_path`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_nodal_reporting.py`:

```python
import pandas as pd


def test_lmp_csv_includes_avg_and_congestion_columns(tmp_path):
    paths = _run(str(tmp_path))
    lmp_csv = tmp_path / paths["lmp"].split("/")[-1]
    df = pd.read_csv(lmp_csv)
    assert {"timestamp", "bus", "lmp", "lmp_avg", "lmp_congestion"}.issubset(df.columns)
    row0 = df[(df["timestamp"] == "H00") & (df["bus"] == "centro")].iloc[0]
    assert math.isclose(row0["lmp"], row0["lmp_avg"] + row0["lmp_congestion"], abs_tol=1e-6)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_nodal_reporting.py -v`
Expected: FAILS (missing `lmp_avg`/`lmp_congestion` columns).

- [ ] **Step 3: Add the columns**

In `app/nodal/reporting.py`, replace the `lmp_rows` comprehension:

```python
    lmp_rows = [
        {"timestamp": ts, "bus": bus, "lmp": sol.lmp[bus][t]}
        for t, ts in enumerate(sol.timestamps)
        for bus in sol.buses
    ]
```

with:

```python
    lmp_rows = [
        {
            "timestamp": ts,
            "bus": bus,
            "lmp": sol.lmp[bus][t],
            "lmp_avg": sol.lmp_avg[t],
            "lmp_congestion": sol.lmp_congestion[bus][t],
        }
        for t, ts in enumerate(sol.timestamps)
        for bus in sol.buses
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_nodal_reporting.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/nodal/reporting.py tests/test_nodal_reporting.py
git commit -m "feat(nodal): write lmp_avg/lmp_congestion columns onto the lmp.csv artifact"
```

---

## Task 4: `load_reference_price` gains an `lmp` branch

**Files:**
- Modify: `app/data/actuals.py`
- Test: `tests/test_actuals.py`

**Interfaces:**
- Produces: `load_reference_price(dispatch_date, level="lmp", data_dir=...)` now returns the real bolsa price (same as `level="ideal"`), falling back to iMAR MPO when bolsa isn't published yet. `level="preideal"` behavior is unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_actuals.py`:

```python
def test_load_reference_price_lmp_uses_bolsa_like_ideal(tmp_path):
    (tmp_path / "precio_bolsa").mkdir()
    rows = [f"2024-04-18 {h:02d}:00:00,{h + 1}" for h in range(24)]
    (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").write_text(
        "datetime,precio_bolsa\n" + "\n".join(rows) + "\n"
    )
    (tmp_path / "2024-04-18").mkdir()
    mpo = ",".join(str(float(i)) for i in range(24))
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text('"MPO",' + mpo + "\n")

    lmp = load_reference_price(date(2024, 4, 18), level="lmp", data_dir=str(tmp_path))
    assert lmp[0] == 1000.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_actuals.py -v`
Expected: FAILS — today `level="lmp"` falls through to `load_actual_price` (iMAR MPO), so `lmp[0]` is `0.0`, not `1000.0`.

- [ ] **Step 3: Add the branch**

In `app/data/actuals.py`, change:

```python
    if level == "ideal":
        try:
            return load_actual_bolsa(dispatch_date, data_dir=data_dir)
        except (FileNotFoundError, ValueError):
            return load_actual_price(dispatch_date, data_dir=data_dir)
    return load_actual_price(dispatch_date, data_dir=data_dir)
```

to:

```python
    if level in ("ideal", "lmp"):
        try:
            return load_actual_bolsa(dispatch_date, data_dir=data_dir)
        except (FileNotFoundError, ValueError):
            return load_actual_price(dispatch_date, data_dir=data_dir)
    return load_actual_price(dispatch_date, data_dir=data_dir)
```

Also update the docstring's first line from `ideal -> real bolsa price...` to `ideal/lmp -> real bolsa price (PrecBolsNaci): the value the ideal dispatch determines, and the target the LMP weighted-average price is compared against; falls back to iMAR MPO when not yet published.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_actuals.py -v`
Expected: all tests PASS, including pre-existing `ideal`/`preideal` ones.

- [ ] **Step 5: Commit**

```bash
git add app/data/actuals.py tests/test_actuals.py
git commit -m "feat(actuals): load_reference_price treats level=lmp like ideal (real bolsa target)"
```

---

## Task 5: API — precio promedio ponderado vs. bolsa real comparison

**Files:**
- Modify: `services/api/main.py`
- Test: `tests/test_api_nodal.py`

**Interfaces:**
- Consumes: `load_reference_price` (Task 4), `nodal_result.lmp_path` (existing `NodalRunResult` field, unchanged), `lmp_avg` column on `lmp.csv` (Task 3).
- Produces: `GET /runs/{run_id}` response gains `body["nodal"]["price_series"]: list[{datetime, model_mpo, xm_mpo}] | None`, same shape as the existing top-level `price_series` field used for `ideal`/`preideal` runs.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_nodal.py` (add `import math` at top):

```python
def test_get_nodal_run_detail_includes_price_series(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.api.main.load_reference_price",
        lambda dispatch_date, level, data_dir="data": [float(i) for i in range(24)],
    )
    run_id = _seed_done_nodal_run(api_client, tmp_path)

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    price_series = resp.json()["nodal"]["price_series"]

    assert len(price_series) == 24
    assert price_series[0]["datetime"] == "2024-04-18T00:00:00"
    assert math.isclose(price_series[0]["model_mpo"], 20.0)
    assert math.isclose(price_series[0]["xm_mpo"], 0.0)
    assert math.isclose(price_series[23]["model_mpo"], 43.0)
    assert math.isclose(price_series[23]["xm_mpo"], 23.0)
```

Also update `_seed_done_nodal_run`'s `lmp_rows` in `tests/test_api_nodal.py` to match the real artifact shape from Task 3:

```python
    lmp_rows = [
        {
            "timestamp": f"2024-04-18 {h:02d}:00",
            "bus": z,
            "lmp": 20.0 + h,
            "lmp_avg": 20.0 + h,
            "lmp_congestion": 0.0,
        }
        for h in range(24)
        for z in ZONES
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_api_nodal.py -v`
Expected: FAILS with `KeyError: 'price_series'`.

- [ ] **Step 3: Add the comparison helper and wire it in**

In `services/api/main.py`, add after `_price_series`:

```python
def _nodal_price_comparison_df(nodal_result, case) -> pd.DataFrame | None:
    """Precio promedio ponderado (lmp_avg, from the lmp.csv artifact) aligned
    with the real bolsa price, one row per hour. None when either source is
    missing."""
    if nodal_result is None or nodal_result.lmp_path is None:
        return None
    storage = get_storage(".")
    if not storage.exists(nodal_result.lmp_path):
        return None
    try:
        with storage.open(nodal_result.lmp_path) as f:
            df = pd.read_csv(f)
        xm = load_reference_price(case.dispatch_date, level=case.level, data_dir="data")
    except (FileNotFoundError, ValueError):
        return None
    hourly = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    model_avg = hourly["lmp_avg"].astype(float).tolist()
    n = min(len(model_avg), len(xm))
    return pd.DataFrame(
        {
            "datetime": [f"{case.dispatch_date}T{h:02d}:00:00" for h in range(n)],
            "model_mpo": model_avg[:n],
            "xm_mpo": [float(x) for x in xm[:n]],
        }
    )


def _nodal_price_series(nodal_result, case) -> list[dict] | None:
    df = _nodal_price_comparison_df(nodal_result, case)
    if df is None:
        return None
    return df.to_dict(orient="records")
```

Then in `get_run_detail`, add one key to the `nodal` dict:

```python
    nodal_result = queries.get_nodal_result(session, run.id)
    out["nodal"] = (
        {
            "metrics": nodal_result.metrics,
            "redistribution": nodal_result.redistribution,
            "gen_revenue_by_zone": nodal_result.gen_revenue_by_zone,
            "network": nodal_result.network,
            "price_series": _nodal_price_series(nodal_result, case),
            "artifacts": {
                name: getattr(nodal_result, attr) is not None
                for name, attr in _NODAL_ARTIFACT_PATHS.items()
            },
        }
        if nodal_result
        else None
    )
```

(Only the new `"price_series": _nodal_price_series(nodal_result, case),` line is added.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_nodal.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/main.py tests/test_api_nodal.py
git commit -m "feat(api): expose precio promedio ponderado vs bolsa real comparison for lmp runs"
```

---

## Task 6: Frontend types — `LmpRow` and `NodalResult`

**Files:**
- Modify: `frontend/lib/types.ts`

**Interfaces:**
- Produces: `LmpRow` gains `lmp_avg: number; lmp_congestion: number;`. `NodalResult` gains `price_series: PricePoint[] | null;`.

- [ ] **Step 1: Edit `LmpRow`**

Change:

```typescript
export interface LmpRow { timestamp: string; bus: string; lmp: number; }
```

to:

```typescript
export interface LmpRow {
  timestamp: string; bus: string; lmp: number;
  lmp_avg: number; lmp_congestion: number;
}
```

- [ ] **Step 2: Edit `NodalResult`**

Change:

```typescript
export interface NodalResult {
  metrics: NodalMetrics;
  redistribution: NodalRedistributionRow[];
  gen_revenue_by_zone: NodalGenRevenueRow[];
  network: NodalNetwork;
  artifacts: Record<NodalArtifactName, boolean>;
}
```

to:

```typescript
export interface NodalResult {
  metrics: NodalMetrics;
  redistribution: NodalRedistributionRow[];
  gen_revenue_by_zone: NodalGenRevenueRow[];
  network: NodalNetwork;
  price_series: PricePoint[] | null;
  artifacts: Record<NodalArtifactName, boolean>;
}
```

`PricePoint` is already defined earlier in the same file.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm lint`
Expected: no new type errors beyond call sites fixed in Tasks 7-9 (expected — they get fixed in their own tasks).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat(types): add lmp_avg/lmp_congestion to LmpRow, price_series to NodalResult"
```

---

## Task 7: Frontend chart-data helpers — average price and congestion series

**Files:**
- Modify: `frontend/lib/nodal-chart-data.ts`
- Test: `frontend/lib/nodal-chart-data.test.ts`

**Interfaces:**
- Produces: `toAvgPriceData(rows: LmpRow[]): HourlyPoint[]` (24 points, each `{ hour, lmp_avg }`). `toCongestionCurveData(rows: LmpRow[]): { data: HourlyPoint[]; seriesKeys: string[] }` (same shape as `toPriceCurveData`, keyed by zone, valued by `lmp_congestion`).
- Consumes: `LmpRow` (Task 6), `hourFromTimestamp` (existing, unchanged).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/lib/nodal-chart-data.test.ts` (add `toAvgPriceData, toCongestionCurveData` to the existing import list):

```typescript
describe("toAvgPriceData", () => {
  const rows = [
    { timestamp: "H00", bus: "norte", lmp: 20, lmp_avg: 60, lmp_congestion: -40 },
    { timestamp: "H00", bus: "sur", lmp: 80, lmp_avg: 60, lmp_congestion: 20 },
    { timestamp: "H01", bus: "norte", lmp: 21, lmp_avg: 61, lmp_congestion: -40 },
  ];
  it("builds 24 hourly points with one value per hour, deduped across zones", () => {
    const data = toAvgPriceData(rows);
    expect(data).toHaveLength(24);
    expect(data[0]).toMatchObject({ hour: 0, lmp_avg: 60 });
    expect(data[1]).toMatchObject({ hour: 1, lmp_avg: 61 });
  });
});

describe("toCongestionCurveData", () => {
  const rows = [
    { timestamp: "H00", bus: "norte", lmp: 20, lmp_avg: 60, lmp_congestion: -40 },
    { timestamp: "H00", bus: "sur", lmp: 80, lmp_avg: 60, lmp_congestion: 20 },
  ];
  it("builds 24 hourly points with one series per zone, valued by congestion", () => {
    const { data, seriesKeys } = toCongestionCurveData(rows);
    expect(data).toHaveLength(24);
    expect(seriesKeys.sort()).toEqual(["norte", "sur"]);
    expect(data[0]).toMatchObject({ hour: 0, norte: -40, sur: 20 });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm test nodal-chart-data`
Expected: FAILS — `toAvgPriceData`/`toCongestionCurveData` are not exported yet.

- [ ] **Step 3: Implement the two functions**

In `frontend/lib/nodal-chart-data.ts`, add after `toPriceCurveData`:

```typescript
export function toAvgPriceData(rows: LmpRow[]): HourlyPoint[] {
  const byHour = new Map<number, number>();
  for (const row of rows) byHour.set(hourFromTimestamp(row.timestamp), row.lmp_avg);
  const data: HourlyPoint[] = [];
  for (let hour = 0; hour < 24; hour++) data.push({ hour, lmp_avg: byHour.get(hour) ?? 0 });
  return data;
}

export function toCongestionCurveData(rows: LmpRow[]) {
  const byZone = new Map<string, Map<number, number>>();
  for (const row of rows) {
    if (!byZone.has(row.bus)) byZone.set(row.bus, new Map());
    byZone.get(row.bus)!.set(hourFromTimestamp(row.timestamp), row.lmp_congestion);
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm test nodal-chart-data`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/nodal-chart-data.ts frontend/lib/nodal-chart-data.test.ts
git commit -m "feat(nodal-chart-data): add toAvgPriceData and toCongestionCurveData"
```

---

## Task 8: `PriceCurvesChart` — precio promedio ponderado as its own series, not a `referenceZone` alias

**Files:**
- Modify: `frontend/components/nodal/price-curves-chart.tsx`
- Modify: `frontend/lib/i18n.ts`
- Test: `frontend/components/nodal/price-curves-chart.test.tsx`

**Interfaces:**
- Produces: `PriceCurvesChart` no longer takes a `referenceZone` prop. Its average-price line is always rendered, sourced from `lmp_avg`, independent of zone selection.
- Consumes: `toPriceCurveData`, `toAvgPriceData` (Task 7), `LmpRow` (Task 6).

- [ ] **Step 1: Rename the i18n key and its text**

In `frontend/lib/i18n.ts`, Spanish (`es`) block, replace:

```typescript
    "nodal.singlePrice": "Precio unico",
```

with:

```typescript
    "nodal.avgPrice": "Precio promedio ponderado",
```

English (`en`) block, replace:

```typescript
    "nodal.singlePrice": "Single price",
```

with:

```typescript
    "nodal.avgPrice": "Weighted average price",
```

(This is a rename, not an addition — the old `nodal.singlePrice` key is gone; nothing else in the untouched codebase references it since Task 8's own rewrite of `price-curves-chart.tsx`, in the same commit, is the only consumer.)

- [ ] **Step 2: Update the failing test**

Replace `frontend/components/nodal/price-curves-chart.test.tsx` in full:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow } from "@/lib/types";
import { PriceCurvesChart } from "./price-curves-chart";

const ROWS: LmpRow[] = Array.from({ length: 24 }, (_, hour) => [
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "norte", lmp: 20 + hour, lmp_avg: 20 + hour, lmp_congestion: 0,
  },
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "sur", lmp: 30 + hour, lmp_avg: 20 + hour, lmp_congestion: 10,
  },
]).flat();

describe("PriceCurvesChart", () => {
  it("renders one line per zone plus the always-present weighted-average line", () => {
    const { container } = render(
      <I18nProvider>
        <PriceCurvesChart rows={ROWS} hour={0} />
      </I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    // 2 zone lines (norte, sur) + 1 weighted-average (lmp_avg) line
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(3);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><PriceCurvesChart rows={[]} hour={0} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && pnpm test price-curves-chart`
Expected: FAILS — today only 2 `.recharts-line` render (no always-present average-price line yet).

- [ ] **Step 4: Rewrite the component**

Replace `frontend/components/nodal/price-curves-chart.tsx` in full:

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
import { toAvgPriceData, toPriceCurveData } from "@/lib/nodal-chart-data";
import type { LmpRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];
const AVG_PRICE_KEY = "lmp_avg";
const AVG_PRICE_COLOR = "#ffffff";

interface PriceCurvesChartProps {
  rows: LmpRow[];
  hour: number;
}

export function PriceCurvesChart({ rows, hour }: PriceCurvesChartProps) {
  const t = useT();
  const { data: zoneData, seriesKeys } = useMemo(() => toPriceCurveData(rows), [rows]);
  const avgData = useMemo(() => toAvgPriceData(rows), [rows]);
  const data = useMemo(
    () => zoneData.map((point, i) => ({ ...point, [AVG_PRICE_KEY]: avgData[i]?.lmp_avg ?? 0 })),
    [zoneData, avgData],
  );
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{t("chart.pricesNoData")}</div>;
  }

  const legendItems: ChartLegendItem[] = [
    ...seriesKeys.map((key, index) => ({ key, name: key, color: PALETTE[index % PALETTE.length] })),
    { key: AVG_PRICE_KEY, name: t("nodal.avgPrice"), color: AVG_PRICE_COLOR },
  ];

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
              <Line key={key} type="monotone" dataKey={key} name={key}
                stroke={PALETTE[index % PALETTE.length]} dot={false} strokeWidth={2}
                hide={hidden.has(key)} />
            ))}
            <Line key={AVG_PRICE_KEY} type="monotone" dataKey={AVG_PRICE_KEY}
              name={t("nodal.avgPrice")} stroke={AVG_PRICE_COLOR} dot={false}
              strokeWidth={3} strokeDasharray="6 4" hide={hidden.has(AVG_PRICE_KEY)} />
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm test price-curves-chart`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/nodal/price-curves-chart.tsx frontend/components/nodal/price-curves-chart.test.tsx frontend/lib/i18n.ts
git commit -m "fix(nodal): average-price line is its own weighted series, not aliased to referenceZone"
```

---

## Task 9: New `CongestionCurvesChart` component

**Files:**
- Create: `frontend/components/nodal/congestion-curves-chart.tsx`
- Test: `frontend/components/nodal/congestion-curves-chart.test.tsx`

**Interfaces:**
- Produces: `CongestionCurvesChart({ rows: LmpRow[]; hour: number })` — one line per zone, valued by `lmp_congestion`. No aggregation across zones (kept granular for a future interpolated map, per explicit user request).
- Consumes: `toCongestionCurveData` (Task 7).

- [ ] **Step 1: Write the failing test**

Create `frontend/components/nodal/congestion-curves-chart.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import type { LmpRow } from "@/lib/types";
import { CongestionCurvesChart } from "./congestion-curves-chart";

const ROWS: LmpRow[] = Array.from({ length: 24 }, (_, hour) => [
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "norte", lmp: 20 + hour, lmp_avg: 20 + hour, lmp_congestion: -20,
  },
  {
    timestamp: `2024-04-18 ${String(hour).padStart(2, "0")}:00`,
    bus: "sur", lmp: 30 + hour, lmp_avg: 20 + hour, lmp_congestion: 10,
  },
]).flat();

describe("CongestionCurvesChart", () => {
  it("renders one line per zone", () => {
    const { container } = render(
      <I18nProvider><CongestionCurvesChart rows={ROWS} hour={0} /></I18nProvider>,
    );
    expect(container.querySelector(".recharts-wrapper, svg")).toBeTruthy();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
  });

  it("shows an empty state when there are no rows", () => {
    render(<I18nProvider><CongestionCurvesChart rows={[]} hour={0} /></I18nProvider>);
    expect(screen.getByText(/no hay datos de precios/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test congestion-curves-chart`
Expected: FAILS — module doesn't exist yet.

- [ ] **Step 3: Implement the component**

Create `frontend/components/nodal/congestion-curves-chart.tsx`:

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
import { toCongestionCurveData } from "@/lib/nodal-chart-data";
import type { LmpRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];

interface CongestionCurvesChartProps {
  rows: LmpRow[];
  hour: number;
}

export function CongestionCurvesChart({ rows, hour }: CongestionCurvesChartProps) {
  const t = useT();
  const { data, seriesKeys } = useMemo(() => toCongestionCurveData(rows), [rows]);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const { wrapperRef, visibleData, isZoomed, reset, getWrapperProps } = useChartZoom(data);

  if (rows.length === 0) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{t("chart.pricesNoData")}</div>;
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
              <Line key={key} type="monotone" dataKey={key} name={key}
                stroke={PALETTE[index % PALETTE.length]} dot={false} strokeWidth={2}
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm test congestion-curves-chart`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/nodal/congestion-curves-chart.tsx frontend/components/nodal/congestion-curves-chart.test.tsx
git commit -m "feat(nodal): add CongestionCurvesChart, per-zone congestion over 24h"
```

---

## Task 10: `PriceSeriesChart` — optional label overrides for reuse

**Files:**
- Modify: `frontend/components/price-series-chart.tsx`
- Modify: `frontend/lib/i18n.ts`
- Test: `frontend/components/price-series-chart.test.tsx`

**Interfaces:**
- Produces: `PriceSeriesChart({ points, modelLabelKey?, xmLabelKey? })` — `modelLabelKey`/`xmLabelKey` default to `"runDetail.modelMpo"`/`"runDetail.xmMpo"` (today's behavior, byte-identical for existing callers that don't pass them).

- [ ] **Step 1: Add the two new i18n keys**

In `frontend/lib/i18n.ts`, Spanish (`es`) block, add near the other `nodal.*` keys:

```typescript
    "nodal.avgPriceModelLabel": "Precio promedio ponderado",
    "nodal.bolsaRealLabel": "Bolsa real",
```

English (`en`) block:

```typescript
    "nodal.avgPriceModelLabel": "Weighted average price",
    "nodal.bolsaRealLabel": "Real bolsa price",
```

- [ ] **Step 2: Write the failing test**

Add to `frontend/components/price-series-chart.test.tsx` (match the file's existing import style for `render`/`screen`/`I18nProvider`):

```tsx
it("uses custom label keys when provided", () => {
  render(
    <I18nProvider>
      <PriceSeriesChart
        points={[{ datetime: "2024-04-18T00:00:00", model_mpo: 10, xm_mpo: 20 }]}
        modelLabelKey="nodal.avgPriceModelLabel"
        xmLabelKey="nodal.bolsaRealLabel"
      />
    </I18nProvider>,
  );
  expect(screen.getByText("Precio promedio ponderado")).toBeInTheDocument();
  expect(screen.getByText("Bolsa real")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && pnpm test price-series-chart`
Expected: FAILS — `modelLabelKey`/`xmLabelKey` props don't exist yet.

- [ ] **Step 4: Add the props**

In `frontend/components/price-series-chart.tsx`, change:

```tsx
export function PriceSeriesChart({ points }: { points: PricePoint[] | null }) {
  const t = useT();
```

to:

```tsx
interface PriceSeriesChartProps {
  points: PricePoint[] | null;
  modelLabelKey?: string;
  xmLabelKey?: string;
}

export function PriceSeriesChart({
  points,
  modelLabelKey = "runDetail.modelMpo",
  xmLabelKey = "runDetail.xmMpo",
}: PriceSeriesChartProps) {
  const t = useT();
```

Then change the `legendItems` line:

```tsx
  const legendItems = SERIES.map((s) => ({
    key: s.key,
    name: t(s.key === "model_mpo" ? "runDetail.modelMpo" : "runDetail.xmMpo"),
    color: s.color,
  }));
```

to:

```tsx
  const legendItems = SERIES.map((s) => ({
    key: s.key,
    name: t(s.key === "model_mpo" ? modelLabelKey : xmLabelKey),
    color: s.color,
  }));
```

and the `<Line name={...}>` prop inside the `SERIES.map` JSX:

```tsx
                name={t(s.key === "model_mpo" ? "runDetail.modelMpo" : "runDetail.xmMpo")}
```

to:

```tsx
                name={t(s.key === "model_mpo" ? modelLabelKey : xmLabelKey)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm test price-series-chart`
Expected: all tests PASS, including pre-existing ones (default label keys keep old behavior identical).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/price-series-chart.tsx frontend/components/price-series-chart.test.tsx frontend/lib/i18n.ts
git commit -m "feat(price-series-chart): optional label keys so the component works for LMP vs bolsa too"
```

---

## Task 11: Wire the new charts into the nodal dashboard page

**Files:**
- Modify: `frontend/app/(app)/runs/[id]/nodal/page.tsx`
- Modify: `frontend/lib/i18n.ts`

**Interfaces:**
- Consumes: `CongestionCurvesChart` (Task 9), `PriceSeriesChart` with label overrides (Task 10), `nodal.price_series` (Task 6), updated `PriceCurvesChart` without `referenceZone` (Task 8).
- Produces: no new exports — page-level wiring, the final visible deliverable.

- [ ] **Step 1: Add the remaining i18n keys**

In `frontend/lib/i18n.ts`, Spanish (`es`) block — replace:

```typescript
    "nodal.priceCurvesSubtitle": "LMP por zona y precio unico (zona de referencia)",
```

with:

```typescript
    "nodal.priceCurvesSubtitle": "LMP por zona y precio promedio ponderado por demanda",
```

and add, right after `"nodal.artifact.summary": "Resumen JSON",`:

```typescript
    "nodal.congestionCurvesTitle": "Congestion por zona",
    "nodal.congestionCurvesSubtitle": "LMP menos precio promedio ponderado, por zona y hora",
    "nodal.priceComparisonTitle": "Precio promedio ponderado vs. bolsa real",
    "nodal.priceComparisonSubtitle": "Precio promedio ponderado por demanda vs. precio de bolsa real (PrecBolsNaci)",
```

English (`en`) block — replace:

```typescript
    "nodal.priceCurvesSubtitle": "LMP per zone and single price (reference zone)",
```

with:

```typescript
    "nodal.priceCurvesSubtitle": "LMP per zone and demand-weighted average price",
```

and add, right after `"nodal.artifact.summary": "Summary JSON",`:

```typescript
    "nodal.congestionCurvesTitle": "Congestion per zone",
    "nodal.congestionCurvesSubtitle": "LMP minus the weighted average price, per zone and hour",
    "nodal.priceComparisonTitle": "Weighted average price vs. real bolsa price",
    "nodal.priceComparisonSubtitle": "Demand-weighted average price vs. the real bolsa price (PrecBolsNaci)",
```

- [ ] **Step 2: Update the page**

In `frontend/app/(app)/runs/[id]/nodal/page.tsx`, add imports with the other component imports:

```tsx
import { CongestionCurvesChart } from "@/components/nodal/congestion-curves-chart";
import { PriceSeriesChart } from "@/components/price-series-chart";
```

Change the price-curves card to drop the removed `referenceZone` prop:

```tsx
      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.priceCurvesTitle")}</CardTitle>
          <CardDescription>{t("nodal.priceCurvesSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <PriceCurvesChart rows={lmpQuery.data ?? []} hour={hour} />
        </CardContent>
      </Card>
```

Immediately after that card (before the dispatch/branch-flows grid), add two new cards:

```tsx
      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.congestionCurvesTitle")}</CardTitle>
          <CardDescription>{t("nodal.congestionCurvesSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <CongestionCurvesChart rows={lmpQuery.data ?? []} hour={hour} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("nodal.priceComparisonTitle")}</CardTitle>
          <CardDescription>{t("nodal.priceComparisonSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <PriceSeriesChart
            points={nodal.price_series}
            modelLabelKey="nodal.avgPriceModelLabel"
            xmLabelKey="nodal.bolsaRealLabel"
          />
        </CardContent>
      </Card>
```

- [ ] **Step 3: Manual verification in the browser**

With the dev stack running (`docker compose --project-directory . --env-file .env -f docker/docker-compose.dev.yaml up -d --build`, or hot-reload if already up), open a `level=lmp` run's nodal dashboard at `http://localhost:3000/runs/<id>/nodal` and confirm:
- The price-curves chart shows a "Precio promedio ponderado" line, visually distinct from any single zone's line.
- A "Congestion por zona" chart renders below it, one line per zone.
- A "Precio promedio ponderado vs. bolsa real" chart renders (or shows the empty state if no real bolsa data exists locally — expected without real `data/`).

- [ ] **Step 4: Run the full frontend test suite and lint**

Run: `cd frontend && pnpm lint && pnpm test`
Expected: all PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `uv run ruff check && uv run ruff format --check && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/\(app\)/runs/\[id\]/nodal/page.tsx frontend/lib/i18n.ts
git commit -m "feat(nodal): wire congestion chart and precio promedio ponderado vs bolsa comparison into the dashboard"
```

---

## Self-Review Notes

- **Spec coverage:** (1) demand-weighted average price — Task 1+2+8. (2) per-zone congestion, separate, granular — Task 1+3+7+9. (3) comparison vs bolsa real — Task 4+5+11. All three spec objectives have tasks; zero engine-formulation risk (confirmed — no task touches EGRET's dispatch model).
- **No backfill / no DB migration:** confirmed — `lmp_avg`/`lmp_congestion` ride on the existing `lmp.csv` artifact and `lmp_path` column.
- **Naming consistency checked:** every "precio único"/"LMPE"/`lmp_energy`/`toSinglePriceData`/`SINGLE_PRICE_KEY`/`nodal.singlePrice` from the first draft is renamed throughout to "precio promedio ponderado"/`lmp_avg`/`toAvgPriceData`/`AVG_PRICE_KEY`/`nodal.avgPrice` — Task 1 (engine fields) → Task 2/3 (consumers) → Task 6 (frontend type) → Task 7 (chart-data helpers) → Task 8/9/10/11 (components, i18n, page).
- **Type consistency:** `NodalSolution.lmp_avg`/`lmp_congestion` (Task 1) → `status_quo.py` (Task 2), `reporting.py` (Task 3) consume identically. `LmpRow.lmp_avg`/`lmp_congestion` (Task 6) → `toAvgPriceData`/`toCongestionCurveData` (Task 7) → `PriceCurvesChart`/`CongestionCurvesChart` (Tasks 8-9). `NodalResult.price_series` (Task 6) → `_nodal_price_series` (Task 5) → page (Task 11) via `PriceSeriesChart`'s optional props (Task 10).
