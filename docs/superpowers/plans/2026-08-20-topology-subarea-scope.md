# Topology subarea-scope builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope `scrape-topology`'s default zone granularity from per-substation ("node", 500+ zones) to per-subárea-operativa ("subarea", 21 zones), behind a shared `TopologyBuilder` interface that also carries the existing node-level builder and a stub for a future area-level one, selected via a new `--scope` CLI flag.

**Architecture:** New `app/data/topology/builders/` package with one function per scope (`build_subarea_network`, `build_node_network`, `build_area_network`) behind a `BUILDERS` registry dict, all sharing one call signature. `build_subarea_network` derives zones from the `subarea` field PARATEC already puts on every substation, sources inter-subarea branches primarily from a newly-added PARATEC map endpoint (`TransmissionMap/getLines`, which gives clean structured substation pairs — no free-text parsing), falls back to the existing `Line/getAll` free-text split only to fill the small gap of lines absent from the map, and fuses same-subarea lines into an informational (non-schema) summary instead of emitting them as branches. `build_node_network` is the existing `build_network` unchanged, wrapped for interface parity. `app/data/topology/cli.py` gains `--scope subarea|node|area` (default `subarea`) and dispatches through the registry.

**Tech Stack:** Python 3.12, pydantic v2 (`app/nodal/network/schemas.py`, untouched), Typer, pytest, `app.storage.get_storage` for I/O — same stack as the existing scraper, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-topology-subarea-scope-design.md` — this plan argues from the spec; executors read both. The spec documents the empirical evidence (SIMEM catalog cross-check, `TransmissionMap/getLines` coverage numbers) this plan builds on.

## Global Constraints

- **`node`/`area` scope are explicitly out of scope for behavior changes.** `build_node_network` wraps the existing `build_network` from `app/data/topology/build.py` **unchanged** — do not fix its dangling-reference-crashes-pydantic bug as part of this plan (it's a separate, already-diagnosed issue, deferred by the spec). `build_area_network` is interface-only, always raises `NotImplementedError`.
- **No new runtime dependencies.** Everything needed (`httpx`, pydantic, Typer) is already in `pyproject.toml`.
- **All I/O through `app.storage.get_storage`** (`exists`, `open`, `list_dir`). Never `open()` directly.
- **`data/` is git-ignored**; raw cache lives under `data/topology/raw/`. Fixtures go in `tests/fixtures/` (new subdirectory `tests/fixtures/topology_subarea/` for this plan, kept separate from the existing `tests/fixtures/topology/` node-scope golden fixtures — do not modify those).
- **No commits to `develop`.** Branch: `fase6c-topologia-subarea` (already created and checked out).
- **Ruff bloqueante** (select E,F,I, line-length 100) via pre-commit; `uv run pytest -q -m "not live"` for the offline suite.
- **PARATEC headers required** (`PARATEC_HEADERS` in `fetch.py`) — already defined, reused as-is for the new endpoint (same host, same CORS policy, verified live in this session).
- **No AI attribution in commits** (no `Co-Authored-By`, no `🤖`).
- **Combination formula (from spec, verified in-session):** for lines in parallel — same subarea pair, or fused within one subarea — `rating_total = Σ ratings`, and reactance combines in the **per-unit domain** as `1/X_pu_total = Σ (1/X_pu_i)` (each line's own Ω→pu conversion happens first via `reactance_pu`, using that line's own kV — no shared/nominal kV is invented for the combined branch).

---

## File Structure

| File | Responsibility |
|---|---|
| `app/data/topology/units.py` | `reactance_pu(ohm, kv, base_mva=100.0)` — extracted from `build.py` so both `build.py` and `builders/subarea.py` share one conversion, not two copies |
| `app/data/topology/build.py` | Unchanged except importing `reactance_pu` from `units.py` instead of defining it locally |
| `app/data/topology/fetch.py` | Modified: `ENDPOINTS` gains `"lines_map"` |
| `app/data/topology/parse.py` | Modified: `parse_lines` gains a `subarea` key per line; new `parse_map_lines(payload)` |
| `app/data/topology/builders/__init__.py` | `BUILDERS: dict[str, TopologyBuilder]` registry (`"subarea"`, `"node"`, `"area"`) |
| `app/data/topology/builders/base.py` | `TopologyBuilder` Protocol — the shared call signature |
| `app/data/topology/builders/node.py` | `build_node_network` — wraps `build.build_network` |
| `app/data/topology/builders/subarea.py` | `build_subarea_network`, `_combine_parallel`, `_classify_and_collect` — the new logic |
| `app/data/topology/cli.py` | Modified: `--scope` option, dispatch via `BUILDERS`, writes an optional sidecar summary |
| `tests/test_topology_units.py` | Tests for `reactance_pu` |
| `tests/test_topology_parse.py` | Modified: add tests for `parse_map_lines` and the new `subarea` key on `parse_lines` |
| `tests/test_topology_builders_node.py` | `BUILDERS["node"]`/`BUILDERS["area"]` registry tests |
| `tests/test_topology_build_subarea.py` | Unit tests for `build_subarea_network` and its helpers |
| `tests/test_topology_cli.py` | Modified: add `lines_map` to existing fakes, add `--scope` tests |
| `tests/fixtures/topology_subarea/*.json`, `ddem.txt` | New fixture set (2 subareas), separate from the existing node-scope fixtures |
| `tests/test_topology_golden_subarea.py` | Golden test for the subarea scope + a `live` regression guard on map/`Line/getAll` name coverage |
| `README.md` | Note on `--scope` |

---

### Task 1: `fetch.py` — add the `TransmissionMap/getLines` endpoint

**Files:**
- Modify: `app/data/topology/fetch.py`
- Test: `tests/test_topology_fetch.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ENDPOINTS["lines_map"] = f"{PARATEC_BASE}/mapas/api/TransmissionMap/getLines"`. `fetch_all` already iterates `ENDPOINTS` generically, so it now fetches/caches this endpoint too with zero other code changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology_fetch.py — append this test
def test_endpoints_includes_transmission_map():
    assert fetch.ENDPOINTS["lines_map"] == (
        "https://paratecbackend.xm.com.co/mapas/api/TransmissionMap/getLines"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_fetch.py::test_endpoints_includes_transmission_map -q`
Expected: FAIL — `KeyError: 'lines_map'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/fetch.py — inside ENDPOINTS, add one entry
ENDPOINTS: dict[str, str] = {
    "substations": f"{PARATEC_BASE}/reportetransmision/api/Substation/SubstationInfo",
    "lines": f"{PARATEC_BASE}/reportetransmision/api/Line/getAll",
    "lines_map": f"{PARATEC_BASE}/mapas/api/TransmissionMap/getLines",
    "capacity": (
        f"{PARATEC_BASE}/reportegeneracion/api/NetEffectiveCapacities/getNetEffectiveCapacity"
    ),
    "thermal_fuel": f"{PARATEC_BASE}/reportegeneracion/api/ThermalPlant/getAllFuel",
    "hydro": (f"{PARATEC_BASE}/reportegeneracion/api/HydraulicPlant/HydraulicPlantInfo"),
    "solar": f"{PARATEC_BASE}/reportegeneracion/api/SolarPlant/getAll",
    "wind": f"{PARATEC_BASE}/reportegeneracion/api/WindPlant/WindPlantInfo",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_topology_fetch.py -q`
Expected: PASS (all tests, including the existing `test_fetch_all_caches_raw_json`, which asserts `hits["n"] == len(fetch.ENDPOINTS)` — this passes automatically since it derives the count from `ENDPOINTS` itself).

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/fetch.py tests/test_topology_fetch.py
git commit -m "feat(topology): add TransmissionMap/getLines endpoint"
```

---

### Task 2: `parse.py` — `parse_map_lines` + `subarea` on `parse_lines`

**Files:**
- Modify: `app/data/topology/parse.py`
- Test: `tests/test_topology_parse.py`

**Interfaces:**
- Consumes: `{"data": [...]}` GeoJSON-`Feature`-shaped payload from `ENDPOINTS["lines_map"]`.
- Produces:
  - `parse_lines(payload) -> list[dict]` — same as before, **plus a `"subarea"` key** (from the row's own `subArea` field, distinct from the `subStation` split).
  - `parse_map_lines(payload: Any) -> list[dict]` — `{"name": str, "sub1": str, "sub2": str}` per line. Deliberately does **not** carry reactance/rating/kv — the map payload doesn't have them (verified live: its `properties` keys are `nameLine, color, energy, sub1, sub2, operator, longitude, emergencyLimit, ratedCurrent, subArea1, subArea2` — no reactance field at all). Electrical parameters are cross-referenced from `parse_lines`' output by exact `name` match in the build layer (Task 4) — confirmed live that 100% of `getLines`' 805 `nameLine` values have an exact match in `Line/getAll`'s `name`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_topology_parse.py — append these tests
def test_parse_lines_includes_own_subarea():
    payload = {
        "data": [
            {
                "name": "AGUABLANCA - ALFEREZ II 1 115 kV",
                "subStation": "AGUABLANCA - ALFEREZ II",
                "subArea": "SubArea Valle",
                "ratedVoltage": "115",
                "thermalLimit": 600,
                "length": 5.63,
                "typeLines": [{"reactance": 1.23, "length": 5.63}],
            }
        ]
    }
    lines = parse.parse_lines(payload)
    assert lines[0]["subarea"] == "SubArea Valle"


def test_parse_map_lines_extracts_structured_endpoints():
    payload = {
        "data": [
            {
                "type": "Feature",
                "properties": {
                    "nameLine": "CALLE67 - LA PAZ (BOGOTA) 1 115 kV",
                    "sub1": "CALLE67",
                    "sub2": "LA PAZ (BOGOTA)",
                    "subArea1": 2,
                    "subArea2": 2,
                    "emergencyLimit": 920,
                    "ratedCurrent": 800,
                },
                "geometry": {"type": "LineString", "coordinates": [[-74.06, 4.65], [-74.12, 4.63]]},
            }
        ]
    }
    lines = parse.parse_map_lines(payload)
    assert lines == [
        {
            "name": "CALLE67 - LA PAZ (BOGOTA) 1 115 kV",
            "sub1": "CALLE67",
            "sub2": "LA PAZ (BOGOTA)",
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_topology_parse.py -k "own_subarea or map_lines" -q`
Expected: FAIL — `test_parse_lines_includes_own_subarea` fails with `KeyError: 'subarea'`; `test_parse_map_lines_extracts_structured_endpoints` fails with `AttributeError: module 'app.data.topology.parse' has no attribute 'parse_map_lines'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/parse.py — modify parse_lines' returned dict (add one key)
        lines.append(
            {
                "name": row.get("name") or sub,
                "from_zone": from_zone,
                "to_zone": to_zone,
                "reactance_ohm": reactance_ohm,
                "kv": kv,
                "rating": rating,
                "subarea": row.get("subArea") or "",
            }
        )
```

```python
# app/data/topology/parse.py — append this function
def parse_map_lines(payload: Any) -> list[dict]:
    """Parse TransmissionMap/getLines GeoJSON into structured line endpoints.

    Only identity fields (sub1/sub2 are exact substation elementName strings,
    no free-text split needed). Electrical parameters aren't in this payload;
    the build layer cross-references them from parse_lines() output by name.
    """
    lines = []
    for feature in _data(payload):
        props = feature["properties"]
        lines.append(
            {
                "name": props["nameLine"],
                "sub1": props["sub1"],
                "sub2": props["sub2"],
            }
        )
    return lines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_topology_parse.py -q`
Expected: PASS (all tests, including the pre-existing ones — the new `subarea` key doesn't break `test_parse_lines_computes_reactance_ohm_and_rating_mw`, which asserts individual keys, not full-dict equality).

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/parse.py tests/test_topology_parse.py
git commit -m "feat(topology): parse map-endpoint lines and expose line subarea"
```

---

### Task 3: builders package scaffold — `units.py`, `base.py`, `node.py`, registry

**Files:**
- Create: `app/data/topology/units.py`
- Modify: `app/data/topology/build.py` (use `units.reactance_pu` instead of a local copy)
- Create: `app/data/topology/builders/__init__.py`
- Create: `app/data/topology/builders/base.py`
- Create: `app/data/topology/builders/node.py`
- Test: `tests/test_topology_units.py`
- Test: `tests/test_topology_builders_node.py`

**Interfaces:**
- Consumes: `app.data.topology.build.build_network` (existing, Task 3 of the fase6b plan), `app.nodal.network.schemas.NodalNetwork`.
- Produces:
  - `units.reactance_pu(ohm: float, kv: float, base_mva: float = 100.0) -> float`
  - `builders.base.TopologyBuilder` — a `Protocol` with `__call__(subs, lines, gens, demand, *, map_lines=None, demand_split="capacity", reference_zone=None) -> tuple[NodalNetwork, dict[str, Any]]`. **Every implementation returns this same `(network, extra)` shape** — `extra` is scope-specific, non-schema auxiliary data (empty dict when there's none). This is what later tasks/consumers (`cli.py`) rely on.
  - `builders.node.build_node_network(...)` — same signature, wraps `build_network`, always returns `extra={}`.
  - `builders.BUILDERS: dict[str, TopologyBuilder]` with `"node"` and `"area"` registered (`"subarea"` added in Task 4).
  - `builders.build_area_network(...)` — same signature, always raises `NotImplementedError`.

- [ ] **Step 1: Write the failing test for `units.py`**

```python
# tests/test_topology_units.py
from app.data.topology.units import reactance_pu


def test_reactance_pu_formula():
    # X_pu = X_ohm × baseMVA / kV²
    assert reactance_pu(66.125, 115.0) == 66.125 * 100.0 / (115.0**2)


def test_reactance_pu_zero_kv_returns_zero():
    assert reactance_pu(10.0, 0.0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_units.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.data.topology.units'`

- [ ] **Step 3: Write `units.py` and update `build.py` to use it**

```python
# app/data/topology/units.py
from __future__ import annotations


def reactance_pu(ohm: float, kv: float, base_mva: float = 100.0) -> float:
    """Convert Ω (total line reactance) to per-unit on baseMVA at the line's kV."""
    if kv <= 0:
        return 0.0
    return ohm * base_mva / (kv * kv)
```

```python
# app/data/topology/build.py — replace the top of the file (imports + drop the local
# _reactance_pu def) and update its one call site

from __future__ import annotations

import math

from app.data.topology.units import reactance_pu
from app.nodal.network.schemas import (
    Branch,
    Generator,
    NodalNetwork,
    Zone,
)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

# (the old `def _reactance_pu(...): ...` block is deleted — it now lives in units.py)
```

```python
# app/data/topology/build.py — inside build_network's branch list comprehension,
# change the call from _reactance_pu(...) to reactance_pu(...)
    branches = [
        Branch(
            name=line["name"],
            from_zone=line["from_zone"],
            to_zone=line["to_zone"],
            reactance=reactance_pu(line["reactance_ohm"], line["kv"]),
            rating=line["rating"],
        )
        for line in lines
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_topology_units.py tests/test_topology_build.py -q`
Expected: PASS — `test_topology_build.py::test_build_converts_reactance_to_per_unit` still passes unchanged (same formula, new location).

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/units.py app/data/topology/build.py tests/test_topology_units.py
git commit -m "refactor(topology): extract reactance_pu into units.py"
```

- [ ] **Step 6: Write the failing test for the builders registry**

```python
# tests/test_topology_builders_node.py
import pytest

from app.data.topology.builders import BUILDERS

SUBS = [
    {"name": "CALI", "base_kv": 115.0, "subarea": "SubArea Valle", "latitude": 3.4, "longitude": -76.5},
    {"name": "YUMBO", "base_kv": 115.0, "subarea": "SubArea Valle", "latitude": 3.5, "longitude": -76.5},
]
LINES = [
    {
        "name": "CALI - YUMBO 1",
        "from_zone": "CALI",
        "to_zone": "YUMBO",
        "reactance_ohm": 66.125,
        "kv": 115.0,
        "rating": 120.0,
        "subarea": "SubArea Valle",
    },
]
GENS = [
    {
        "name": "H_CALI",
        "capacity": 200.0,
        "fuel": "hydro",
        "marginal_cost": 0.0,
        "subarea": "SubArea Valle",
        "latitude": 3.41,
        "longitude": -76.49,
    },
]
DEMAND = {"SubArea Valle": [100.0] * 24}


def test_node_builder_registered_and_matches_build_network_directly():
    from app.data.topology.build import build_network

    network_direct = build_network(SUBS, LINES, GENS, DEMAND)
    network_via_registry, extra = BUILDERS["node"](SUBS, LINES, GENS, DEMAND, map_lines=[])

    assert network_via_registry.model_dump() == network_direct.model_dump()
    assert extra == {}


def test_area_builder_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        BUILDERS["area"](SUBS, LINES, GENS, DEMAND, map_lines=[])
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_builders_node.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.data.topology.builders'`

- [ ] **Step 8: Write minimal implementation**

```python
# app/data/topology/builders/base.py
from __future__ import annotations

from typing import Any, Protocol

from app.nodal.network.schemas import NodalNetwork


class TopologyBuilder(Protocol):
    """Shared contract for every zone-granularity implementation.

    Every implementation accepts the same arguments (map_lines is ignored by
    scopes that don't need it) and returns (network, extra) — extra is
    scope-specific auxiliary data not part of the NodalNetwork schema itself
    (an empty dict when the scope has none).
    """

    def __call__(
        self,
        subs: list[dict],
        lines: list[dict],
        gens: list[dict],
        demand: dict[str, list[float]],
        *,
        map_lines: list[dict] | None = None,
        demand_split: str = "capacity",
        reference_zone: str | None = None,
    ) -> tuple[NodalNetwork, dict[str, Any]]: ...
```

```python
# app/data/topology/builders/node.py
from __future__ import annotations

from typing import Any

from app.data.topology.build import build_network
from app.nodal.network.schemas import NodalNetwork


def build_node_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    map_lines: list[dict] | None = None,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> tuple[NodalNetwork, dict[str, Any]]:
    """Node (per-substation) scope: thin wrapper around the existing build_network.

    map_lines is accepted for interface uniformity but unused at this scope.
    """
    network = build_network(
        subs, lines, gens, demand, demand_split=demand_split, reference_zone=reference_zone
    )
    return network, {}
```

```python
# app/data/topology/builders/__init__.py
from __future__ import annotations

from typing import Any

from app.data.topology.builders.node import build_node_network
from app.nodal.network.schemas import NodalNetwork


def build_area_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    map_lines: list[dict] | None = None,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> tuple[NodalNetwork, dict[str, Any]]:
    """Area scope: not implemented.

    PARATEC has no line-level data at area granularity (only 8 areas, no
    branch source) — this would require aggregating subarea results, which
    is out of scope for this change.
    """
    raise NotImplementedError(
        "scope='area' has no line-level PARATEC data source; "
        "requires subarea-to-area aggregation, not yet implemented"
    )


BUILDERS = {
    "node": build_node_network,
    "area": build_area_network,
}
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_topology_builders_node.py -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add app/data/topology/builders/ tests/test_topology_builders_node.py
git commit -m "feat(topology): add TopologyBuilder registry with node/area scopes"
```

---

### Task 4: `builders/subarea.py` — the subarea-scope builder

**Files:**
- Create: `app/data/topology/builders/subarea.py`
- Modify: `app/data/topology/builders/__init__.py` (register `"subarea"`)
- Test: `tests/test_topology_build_subarea.py`

**Interfaces:**
- Consumes: `parse_substations`/`parse_lines`/`parse_generators`/`parse_demand`/`parse_map_lines` output shapes (Tasks 1-2 of this plan + the existing `parse.py`), `units.reactance_pu` (Task 3), `NodalNetwork`/`Zone`/`Generator`/`Branch` schemas.
- Produces:
  - `build_subarea_network(subs, lines, gens, demand, *, map_lines=None, demand_split="capacity", reference_zone=None) -> tuple[NodalNetwork, dict[str, dict]]` — matches the `TopologyBuilder` protocol; the returned dict is `{subarea_name: {"rating_mw": float, "n_lines": int}}` for lines fused within one subarea (not part of the schema, not consumed by the dispatch engine).
  - `_combine_parallel(entries: list[tuple[float, float]]) -> tuple[float, float]` — internal helper, `entries` are `(reactance_pu, rating)` pairs; returns the combined `(reactance_pu, rating)`.
  - `_classify_and_collect(map_lines, lines, sub_to_subarea) -> tuple[dict[frozenset[str], list[tuple[float, float]]], dict[str, list[tuple[float, float]]]]` — internal helper, returns `(inter, intra)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_topology_build_subarea.py
from app.data.topology.builders import subarea

SUBS = [
    {"name": "A1", "base_kv": 230.0, "subarea": "SubArea Valle", "latitude": 3.4, "longitude": -76.5},
    {"name": "A2", "base_kv": 115.0, "subarea": "SubArea Valle", "latitude": 3.5, "longitude": -76.5},
    {"name": "B1", "base_kv": 230.0, "subarea": "SubArea Bogota", "latitude": 4.6, "longitude": -74.1},
]
# A2 - GHOST_TAP and FOO - BAR are Line/getAll-only entries not present in the
# map endpoint (map coverage gap): GHOST_TAP/FOO/BAR are not substations, they
# simulate a generator-tap spur and a fully-unresolved line respectively.
LINES = [
    {
        "name": "A1 - B1 1", "from_zone": "A1", "to_zone": "B1",
        "reactance_ohm": 50.0, "kv": 230.0, "rating": 100.0, "subarea": "SubArea Valle",
    },
    {
        "name": "A1 - A2 1", "from_zone": "A1", "to_zone": "A2",
        "reactance_ohm": 20.0, "kv": 115.0, "rating": 80.0, "subarea": "SubArea Valle",
    },
    {
        "name": "A2 - GHOST_TAP 1", "from_zone": "A2", "to_zone": "GHOST_TAP",
        "reactance_ohm": 30.0, "kv": 115.0, "rating": 40.0, "subarea": "SubArea Valle",
    },
    {
        "name": "FOO - BAR 1", "from_zone": "FOO", "to_zone": "BAR",
        "reactance_ohm": 10.0, "kv": 115.0, "rating": 20.0, "subarea": "SubArea Valle",
    },
]
# Only the first two lines are in the map (by name) — the other two exercise
# the Line/getAll gap-fill path.
MAP_LINES = [
    {"name": "A1 - B1 1", "sub1": "A1", "sub2": "B1"},
    {"name": "A1 - A2 1", "sub1": "A1", "sub2": "A2"},
]
GENS = [
    {
        "name": "G1", "capacity": 50.0, "fuel": "hydro", "marginal_cost": 0.0,
        "subarea": "SubArea Valle", "latitude": None, "longitude": None,
    },
]
DEMAND = {"SubArea Valle": [100.0] * 24, "SubArea Bogota": [300.0] * 24}


def test_combine_parallel_two_identical_lines_halves_reactance():
    x_total, rating_total = subarea._combine_parallel([(0.1, 50.0), (0.1, 50.0)])
    assert rating_total == 100.0
    assert abs(x_total - 0.05) < 1e-12


def test_build_subarea_network_zones_from_substation_subarea():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert {z.name for z in network.zones} == {"SubArea Valle", "SubArea Bogota"}
    assert network.reference_zone in {"SubArea Valle", "SubArea Bogota"}


def test_build_subarea_network_inter_zone_branch_from_map_endpoint():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert len(network.branches) == 1
    branch = network.branches[0]
    assert {branch.from_zone, branch.to_zone} == {"SubArea Valle", "SubArea Bogota"}
    assert branch.rating == 100.0


def test_build_subarea_network_fuses_intra_zone_and_gap_lines():
    # A1-A2 (intra, via map), A2-GHOST_TAP (intra via gap-fill, one side unresolved),
    # FOO-BAR (intra via gap-fill, both sides unresolved, falls back to the line's
    # own `subarea` field) — all three fuse into "SubArea Valle", none becomes a Branch.
    _, intra_summary = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert intra_summary["SubArea Valle"]["n_lines"] == 3
    assert intra_summary["SubArea Valle"]["rating_mw"] == 140.0
    assert "SubArea Bogota" not in intra_summary


def test_build_subarea_network_generator_zone_is_its_own_subarea():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    gen = network.generators[0]
    assert gen.zone == "SubArea Valle"
    assert gen.p_max == 50.0


def test_build_subarea_network_demand_shares_sum_to_one():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert set(network.demand_shares) == {"SubArea Valle", "SubArea Bogota"}
    assert abs(network.demand_shares["SubArea Valle"] - 0.25) < 1e-9
    assert abs(network.demand_shares["SubArea Bogota"] - 0.75) < 1e-9
    assert abs(sum(network.demand_shares.values()) - 1.0) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_topology_build_subarea.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.data.topology.builders.subarea'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/builders/subarea.py
from __future__ import annotations

from app.data.topology.units import reactance_pu
from app.nodal.network.schemas import Branch, Generator, NodalNetwork, Zone

# Border/frontier subareas — never populated by real domestic substations
# (verified live against PARATEC), but excluded explicitly and defensively
# in case that ever changes. See the design spec §3.4.
EXCLUDED_SUBAREAS = {
    "",
    "SubArea Ecuador138",
    "SubArea Ecuador230",
    "SubArea Venezuela_Corozo",
    "SubArea Venezuela_Cuatricentenario",
}


def _combine_parallel(entries: list[tuple[float, float]]) -> tuple[float, float]:
    """Combine (reactance_pu, rating) pairs of parallel lines into one.

    rating: capacities in parallel add. reactance: per-unit impedances in
    parallel combine as 1/X_total = Σ(1/X_i) — the standard electrical
    parallel-combination formula. Entries with zero reactance are dropped
    from the harmonic sum to avoid a division by zero (not expected in real
    PARATEC data, a defensive bookkeeping edge case only).
    """
    total_rating = sum(rating for _, rating in entries)
    inv_sum = sum(1.0 / x for x, _ in entries if x > 0)
    total_reactance = 1.0 / inv_sum if inv_sum > 0 else 0.0
    return total_reactance, total_rating


def _classify_and_collect(
    map_lines: list[dict],
    lines: list[dict],
    sub_to_subarea: dict[str, str],
) -> tuple[dict[frozenset[str], list[tuple[float, float]]], dict[str, list[tuple[float, float]]]]:
    """Split every line into an inter-subarea branch candidate or intra-subarea fusion.

    Primary source: map_lines (TransmissionMap/getLines) — sub1/sub2 are exact
    substation names, resolved via sub_to_subarea, electrical parameters
    cross-referenced from `lines` (parse_lines output) by exact line name.

    Gap-fill: any line present in `lines` but absent from `map_lines` (by
    name) is classified via its own from_zone/to_zone (the parse_lines
    subStation split). If neither endpoint resolves to a known substation,
    fall back to the line's own `subarea` field (always present on
    Line/getAll rows) — this can only ever produce an intra-zone fusion,
    never a cross-zone branch, since there is only one subarea to anchor it
    to.

    Returns (inter, intra):
      inter: {frozenset({subarea_a, subarea_b}): [(reactance_pu, rating), ...]}
      intra: {subarea: [(reactance_pu, rating), ...]}
    """
    line_by_name = {line["name"]: line for line in lines}
    inter: dict[frozenset[str], list[tuple[float, float]]] = {}
    intra: dict[str, list[tuple[float, float]]] = {}
    seen_names: set[str] = set()

    for ml in map_lines:
        matched = line_by_name.get(ml["name"])
        if matched is None:
            continue  # map line with no Line/getAll electrical record — skip
        seen_names.add(ml["name"])
        subarea_a = sub_to_subarea.get(ml["sub1"], "")
        subarea_b = sub_to_subarea.get(ml["sub2"], "")
        entry = (reactance_pu(matched["reactance_ohm"], matched["kv"]), matched["rating"])
        if subarea_a and subarea_b and subarea_a != subarea_b:
            inter.setdefault(frozenset({subarea_a, subarea_b}), []).append(entry)
        else:
            zone = subarea_a or subarea_b
            if zone:
                intra.setdefault(zone, []).append(entry)

    for line in lines:
        if line["name"] in seen_names:
            continue
        subarea_a = sub_to_subarea.get(line["from_zone"], "")
        subarea_b = sub_to_subarea.get(line["to_zone"], "")
        entry = (reactance_pu(line["reactance_ohm"], line["kv"]), line["rating"])
        if subarea_a and subarea_b and subarea_a != subarea_b:
            inter.setdefault(frozenset({subarea_a, subarea_b}), []).append(entry)
        else:
            zone = subarea_a or subarea_b or line["subarea"]
            if zone:
                intra.setdefault(zone, []).append(entry)
            # else: neither endpoint nor the line's own subArea resolves — drop.

    return inter, intra


def build_subarea_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    map_lines: list[dict] | None = None,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> tuple[NodalNetwork, dict[str, dict]]:
    """Build a NodalNetwork at subarea granularity.

    demand_split is accepted for interface parity with the node scope but
    unused here: demand is already published per-subarea by XM, so there is
    no split to perform at this granularity.
    """
    map_lines = map_lines or []
    sub_to_subarea = {s["name"]: s["subarea"] for s in subs}
    subarea_names = sorted(
        {sa for sa in sub_to_subarea.values() if sa and sa not in EXCLUDED_SUBAREAS}
    )
    if not subarea_names:
        raise ValueError("no domestic subareas found in substations")

    zones = [Zone(name=name) for name in subarea_names]

    generators = [
        Generator(
            name=g["name"],
            zone=g["subarea"],
            p_max=g["capacity"],
            marginal_cost=g["marginal_cost"],
            fuel=g["fuel"],
        )
        for g in gens
        if g["subarea"] in subarea_names
    ]

    inter, intra = _classify_and_collect(map_lines, lines, sub_to_subarea)

    branches = []
    for pair, entries in inter.items():
        a, b = sorted(pair)
        combined_reactance, combined_rating = _combine_parallel(entries)
        branches.append(
            Branch(
                name=f"{a} - {b}",
                from_zone=a,
                to_zone=b,
                reactance=combined_reactance,
                rating=combined_rating,
            )
        )

    intra_summary: dict[str, dict] = {}
    for zone, entries in intra.items():
        if zone not in subarea_names:
            continue
        _, combined_rating = _combine_parallel(entries)
        intra_summary[zone] = {"rating_mw": combined_rating, "n_lines": len(entries)}

    subarea_total = {name: sum(vals) for name, vals in demand.items()}
    shares = {name: subarea_total.get(name, 0.0) for name in subarea_names}
    total = sum(shares.values())
    if total <= 0:
        raise ValueError("demand produced zero total energy; check demand source/date")
    demand_shares = {z: v / total for z, v in shares.items()}

    ref = reference_zone or subarea_names[0]
    network = NodalNetwork(
        reference_zone=ref,
        zones=zones,
        generators=generators,
        branches=branches,
        demand_shares=demand_shares,
    )
    return network, intra_summary
```

```python
# app/data/topology/builders/__init__.py — add the import and registration
from app.data.topology.builders.subarea import build_subarea_network
# ... (keep the existing build_node_network import and build_area_network def)

BUILDERS = {
    "subarea": build_subarea_network,
    "node": build_node_network,
    "area": build_area_network,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_topology_build_subarea.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/builders/subarea.py app/data/topology/builders/__init__.py tests/test_topology_build_subarea.py
git commit -m "feat(topology): build subarea-scope NodalNetwork from map endpoint + gap-fill"
```

---

### Task 5: `cli.py` — `--scope` option and dispatch

**Files:**
- Modify: `app/data/topology/cli.py`
- Modify: `tests/test_topology_cli.py`

**Interfaces:**
- Consumes: `BUILDERS` (Tasks 3-4), `parse.parse_map_lines` (Task 2), `fetch.ENDPOINTS["lines_map"]` (Task 1).
- Produces: `scrape_topology_cmd` gains `--scope subarea|node|area` (default `"subarea"`); writes `topology/network_summary.json` alongside the network file when the chosen builder returns a non-empty `extra`.

- [ ] **Step 1: Modify the two existing fakes and write the failing tests**

```python
# tests/test_topology_cli.py — add "lines_map": {"data": []} to BOTH existing
# fake_fetch_all return dicts (test_scrape_topology_writes_network_json and
# test_scrape_topology_default_out_relative_to_data_dir), e.g.:
    def fake_fetch_all(storage, *, refresh=False):
        return {
            "substations": {
                "data": [
                    {
                        "elementName": "CALI",
                        "subAreaName": "SubArea Valle",
                        "voltageLevel": [115],
                        "latitude": 3.4,
                        "longitude": -76.5,
                    }
                ]
            },
            "lines": {"data": []},
            "lines_map": {"data": []},
            "capacity": {"dataReport": []},
            "thermal_fuel": {"data": []},
            "hydro": {"data": []},
            "solar": {"data": []},
            "wind": {"data": []},
        }
```

```python
# tests/test_topology_cli.py — append these tests
def test_scrape_topology_scope_node_produces_substation_zone(tmp_path, monkeypatch):
    out = tmp_path / "network.json"

    def fake_fetch_all(storage, *, refresh=False):
        return {
            "substations": {
                "data": [
                    {
                        "elementName": "CALI",
                        "subAreaName": "SubArea Valle",
                        "voltageLevel": [115],
                        "latitude": 3.4,
                        "longitude": -76.5,
                    }
                ]
            },
            "lines": {"data": []},
            "lines_map": {"data": []},
            "capacity": {"dataReport": []},
            "thermal_fuel": {"data": []},
            "hydro": {"data": []},
            "solar": {"data": []},
            "wind": {"data": []},
        }

    def fake_fetch_demand(storage, d, source):
        return "SubArea Valle,1.0\n"

    monkeypatch.setattr("app.data.topology.fetch.fetch_all", fake_fetch_all)
    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    result = runner.invoke(
        cli.app,
        ["scrape-topology", "--date", "2024-04-18", "--scope", "node", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["zones"] == [{"name": "CALI", "base_kv": 115.0}]


def test_scrape_topology_scope_area_not_implemented(tmp_path, monkeypatch):
    def fake_fetch_all(storage, *, refresh=False):
        return {
            "substations": {"data": []},
            "lines": {"data": []},
            "lines_map": {"data": []},
            "capacity": {"dataReport": []},
            "thermal_fuel": {"data": []},
            "hydro": {"data": []},
            "solar": {"data": []},
            "wind": {"data": []},
        }

    def fake_fetch_demand(storage, d, source):
        return "SubArea Valle,1.0\n"

    monkeypatch.setattr("app.data.topology.fetch.fetch_all", fake_fetch_all)
    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    result = runner.invoke(cli.app, ["scrape-topology", "--date", "2024-04-18", "--scope", "area"])
    assert result.exit_code != 0


def test_scrape_topology_rejects_bad_scope(tmp_path):
    result = runner.invoke(
        cli.app,
        ["scrape-topology", "--date", "2024-04-18", "--scope", "bogus"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_topology_cli.py -q`
Expected: the 2 pre-existing tests still PASS (cli.py hasn't changed yet, so the
extra `"lines_map"` key in their fakes is simply unused). The 3 new tests FAIL
with `Error: No such option: --scope`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/cli.py — full new content
from __future__ import annotations

import json
from datetime import datetime

import typer

from app.data.topology import fetch, parse
from app.data.topology.builders import BUILDERS
from app.storage import get_storage


def scrape_topology_cmd(
    d: str = typer.Option(..., "--date", help="Case date (YYYY-MM-DD)."),
    demand_source: str = typer.Option("ddem", "--demand-source"),
    demand_split: str = typer.Option("capacity", "--demand-split"),
    scope: str = typer.Option("subarea", "--scope", help="subarea|node|area"),
    out: str = typer.Option("topology/network.json", "--out"),
    refresh: bool = typer.Option(False, "--refresh"),
    data_dir: str = typer.Option("data", "--data-dir"),
) -> None:
    """Build a NodalNetwork topology from PARATEC data for a given date."""
    if demand_source not in ("ddem", "pron"):
        raise typer.BadParameter(f"must be 'ddem' or 'pron', got {demand_source!r}")
    if scope not in BUILDERS:
        raise typer.BadParameter(f"scope must be one of {sorted(BUILDERS)}, got {scope!r}")
    dispatch_date = datetime.strptime(d, "%Y-%m-%d").date()
    storage = get_storage(data_dir)
    raw = fetch.fetch_all(storage, refresh=refresh)
    demand_text = fetch.fetch_demand(storage, dispatch_date, demand_source)

    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    gens = parse.parse_generators(
        raw["capacity"],
        raw["thermal_fuel"],
        raw["hydro"],
        raw["solar"],
        raw["wind"],
    )
    demand = parse.parse_demand(demand_text, demand_source)

    builder = BUILDERS[scope]
    network, extra = builder(
        subs, lines, gens, demand, map_lines=map_lines, demand_split=demand_split
    )

    with storage.open(out, "w") as fh:
        json.dump(network.model_dump(), fh, indent=2, ensure_ascii=False)

    extra_msg = ""
    if extra:
        summary_path = "topology/network_summary.json"
        with storage.open(summary_path, "w") as fh:
            json.dump(extra, fh, indent=2, ensure_ascii=False)
        extra_msg = f" Intra-zone summary written to {summary_path}."

    typer.echo(
        f"Topology written to {out} (scope={scope}): {len(network.zones)} zones, "
        f"{len(network.generators)} generators, {len(network.branches)} branches."
        f"{extra_msg}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_topology_cli.py -q`
Expected: PASS — all tests, including the two pre-existing ones (default `--scope subarea` on a 1-substation/0-line/0-generator fixture produces a valid single-zone network with `demand_shares={"SubArea Valle": 1.0}` and no dangling refs, so `"zones" in data` still holds).

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/cli.py tests/test_topology_cli.py
git commit -m "feat(topology): add --scope option to scrape-topology CLI"
```

---

### Task 6: Golden fixture (2 subareas) + live regression guard

**Files:**
- Create: `tests/fixtures/topology_subarea/substations.json`
- Create: `tests/fixtures/topology_subarea/lines.json`
- Create: `tests/fixtures/topology_subarea/lines_map.json`
- Create: `tests/fixtures/topology_subarea/capacity.json`
- Create: `tests/fixtures/topology_subarea/thermal_fuel.json`
- Create: `tests/fixtures/topology_subarea/hydro.json`
- Create: `tests/fixtures/topology_subarea/solar.json`
- Create: `tests/fixtures/topology_subarea/wind.json`
- Create: `tests/fixtures/topology_subarea/ddem.txt`
- Test: `tests/test_topology_golden_subarea.py`

**Interfaces:**
- Consumes: `parse.*` (Task 2, existing), `builders.subarea.build_subarea_network` (Task 4).
- Produces: an offline golden test reconstructing a 2-subarea network from raw-shaped fixtures, plus a `live`-marked test that re-verifies the empirical `TransmissionMap/getLines` ⊆ `Line/getAll` name-coverage finding this whole plan is built on (a regression guard — PARATEC could change either endpoint later).

- [ ] **Step 1: Write the fixture files**

```json
// tests/fixtures/topology_subarea/substations.json
{"header": {"code": 200}, "data": [
  {"elementName": "A1", "subAreaName": "SubArea Valle", "voltageLevel": [230], "latitude": 3.4, "longitude": -76.5},
  {"elementName": "A2", "subAreaName": "SubArea Valle", "voltageLevel": [115], "latitude": 3.5, "longitude": -76.5},
  {"elementName": "B1", "subAreaName": "SubArea Bogota", "voltageLevel": [230], "latitude": 4.6, "longitude": -74.1}
]}
```

```json
// tests/fixtures/topology_subarea/lines.json
{"data": [
  {"name": "A1 - B1 1", "subStation": "A1 - B1", "subArea": "SubArea Valle",
   "ratedVoltage": "230", "thermalLimit": 251, "length": 10.0,
   "typeLines": [{"reactance": 5.0, "length": 10.0}]},
  {"name": "A1 - A2 1", "subStation": "A1 - A2", "subArea": "SubArea Valle",
   "ratedVoltage": "115", "thermalLimit": 401, "length": 10.0,
   "typeLines": [{"reactance": 2.0, "length": 10.0}]},
  {"name": "A2 - GHOST_TAP 1", "subStation": "A2 - GHOST_TAP", "subArea": "SubArea Valle",
   "ratedVoltage": "115", "thermalLimit": 201, "length": 10.0,
   "typeLines": [{"reactance": 3.0, "length": 10.0}]},
  {"name": "FOO - BAR 1", "subStation": "FOO - BAR", "subArea": "SubArea Valle",
   "ratedVoltage": "115", "thermalLimit": 100, "length": 10.0,
   "typeLines": [{"reactance": 1.0, "length": 10.0}]}
]}
```

```json
// tests/fixtures/topology_subarea/lines_map.json
{"data": [
  {"type": "Feature",
   "properties": {"nameLine": "A1 - B1 1", "sub1": "A1", "sub2": "B1", "subArea1": 0, "subArea2": 1},
   "geometry": {"type": "LineString", "coordinates": [[-76.5, 3.4], [-74.1, 4.6]]}},
  {"type": "Feature",
   "properties": {"nameLine": "A1 - A2 1", "sub1": "A1", "sub2": "A2", "subArea1": 0, "subArea2": 0},
   "geometry": {"type": "LineString", "coordinates": [[-76.5, 3.4], [-76.5, 3.5]]}}
]}
```

```json
// tests/fixtures/topology_subarea/capacity.json
{"dataReport": [{"name": "Planta Hidraulica", "dispatchedType": [
  {"name": "Despachada", "generatorTypes": [
    {"name": "Hidraulica", "elements": [
      {"elementName": "G1", "netEffectiveCapacity": 50.0,
       "subArea": "SubArea Valle", "latitude": 3.41, "longitude": -76.49}
    ]}
  ]}
]}]}
```

```json
// tests/fixtures/topology_subarea/thermal_fuel.json
{"data": []}
```

```json
// tests/fixtures/topology_subarea/hydro.json
{"data": []}
```

```json
// tests/fixtures/topology_subarea/solar.json
{"data": []}
```

```json
// tests/fixtures/topology_subarea/wind.json
{"data": []}
```

```text
// tests/fixtures/topology_subarea/ddem.txt
SubArea Valle,100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0
SubArea Bogota,300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0
```

- [ ] **Step 2: Write the golden + live tests**

```python
# tests/test_topology_golden_subarea.py
import json
from pathlib import Path

import pytest

from app.data.topology import parse
from app.data.topology.builders.subarea import build_subarea_network

FIX = Path(__file__).parent / "fixtures" / "topology_subarea"


def _load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def test_golden_fixtures_build_valid_subarea_network():
    raw = {
        name: _load(name)
        for name in ("substations", "lines", "lines_map", "capacity", "thermal_fuel", "hydro", "solar", "wind")
    }
    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    gens = parse.parse_generators(
        raw["capacity"], raw["thermal_fuel"], raw["hydro"], raw["solar"], raw["wind"]
    )
    demand = parse.parse_demand((FIX / "ddem.txt").read_text(), "ddem")
    network, intra_summary = build_subarea_network(subs, lines, gens, demand, map_lines=map_lines)

    assert {z.name for z in network.zones} == {"SubArea Valle", "SubArea Bogota"}
    assert len(network.branches) == 1
    branch = network.branches[0]
    assert {branch.from_zone, branch.to_zone} == {"SubArea Valle", "SubArea Bogota"}
    assert intra_summary["SubArea Valle"]["n_lines"] == 3
    assert abs(sum(network.demand_shares.values()) - 1.0) < 1e-9


@pytest.mark.live
def test_live_map_lines_are_covered_by_line_getall(tmp_path):
    """Regression guard for this plan's core empirical finding: every line
    name in TransmissionMap/getLines has an exact match in Line/getAll's
    name. If PARATEC breaks this, build_subarea_network silently drops the
    unmatched map lines instead of erroring — this test is what would catch
    that drift."""
    from app.data.topology import fetch
    from app.storage import LocalStorage

    storage = LocalStorage(str(tmp_path))
    raw = fetch.fetch_all(storage)
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    line_names = {line["name"] for line in lines}
    unmatched = [ml["name"] for ml in map_lines if ml["name"] not in line_names]
    assert unmatched == []
```

- [ ] **Step 3: Run tests to verify they pass (offline)**

Run: `uv run pytest tests/test_topology_golden_subarea.py -q -m "not live"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/topology_subarea/ tests/test_topology_golden_subarea.py
git commit -m "test(topology): golden fixture + live regression guard for subarea scope"
```

---

### Task 7: README note

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: documentation of `--scope`.

- [ ] **Step 1: Update the existing scrape-topology paragraph**

```markdown
<!-- README.md — replace the existing "### Topología PARATEC → red nodal" paragraph -->
### Topología PARATEC → red nodal

`uv run python -m app scrape-topology --date 2024-04-18` descarga los parámetros
técnicos del sistema (subestaciones, líneas, catálogo de generación) desde PARATEC
y la demanda por subárea desde XM, y escribe un `NodalNetwork` JSON consumible por
`run -t lmp --nodal-network <archivo>`.

`--scope` controla la granularidad de zona (default `subarea`):

- `subarea` (default): una zona por subárea operativa (21 zonas domésticas). Las
  ramas inter-subárea salen de `TransmissionMap/getLines`; las líneas dentro de
  una misma subárea se fusionan y quedan resumidas (no como zonas del grafo) en
  `topology/network_summary.json`.
- `node`: una zona por subestación PARATEC (500+ zonas) — el comportamiento
  original, útil para pruebas de carga/desempeño del motor con la topología
  completa.
- `area`: no implementado aún — PARATEC no tiene datos de línea a nivel de las
  8 áreas operativas.
```

- [ ] **Step 2: Verify**

Run: `uv run pytest -q -m "not live"`
Expected: full suite green, no network calls.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document scrape-topology --scope option"
```

---

## Self-Review

**Spec coverage:**
- ✅ `TransmissionMap/getLines` as primary inter-subarea branch source, `Line/getAll` gap-fill classification (Task 2 `parse_map_lines`, Task 4 `_classify_and_collect`)
- ✅ Electrical parallel combination for both inter-zone parallel lines and intra-zone fusion (Task 4 `_combine_parallel`, used identically in both `inter` and `intra` paths)
- ✅ Intra-zone summary as a sidecar, not a schema field (Task 4 returns it as `extra`; Task 5 `cli.py` writes it to `topology/network_summary.json` only when non-empty; `schemas.py` untouched)
- ✅ Generators/demand at subarea granularity are trivial (direct `zone = subarea`, direct `demand[subarea]` normalization) — Task 4, no geo-nearest/split logic ported from `build.py`
- ✅ `TopologyBuilder` shared interface with `subarea`/`node`/`area` behind one registry, `node` unchanged and `area` a stub (Task 3-4)
- ✅ `node`/`area` scope and `build.py`'s spec-deviation bug explicitly untouched (Global Constraints + Task 3 equivalence test `test_node_builder_registered_and_matches_build_network_directly` proves `node` is byte-for-byte unchanged)
- ✅ SIMEM cross-check and the 3-missing-subareas/2-real-cross-subarea findings are cited as the evidence base in the spec; not re-verified by code in this plan (they were live, one-off empirical checks, not something the pipeline needs to re-assert at runtime)

**Placeholder scan:** no TBD/TODO; every code step is complete, runnable code. The one spec-flagged risk (reactance not present in the map payload) was already resolved during design — Task 4 cross-references `Line/getAll` by name, confirmed live to have 100% coverage.

**Type consistency:** `parse_substations` → `dict` with `name/base_kv/subarea/latitude/longitude` (unchanged); `parse_lines` → adds `subarea` alongside the existing `name/from_zone/to_zone/reactance_ohm/kv/rating`; `parse_map_lines` → `name/sub1/sub2`. `TopologyBuilder.__call__` signature (`subs, lines, gens, demand, *, map_lines, demand_split, reference_zone`) is identical across `base.py`'s Protocol, `node.build_node_network`, `subarea.build_subarea_network`, and `builders.build_area_network`, and every one of them returns `tuple[NodalNetwork, dict[str, Any]]`. `cli.py` consumes exactly that tuple shape (`network, extra = builder(...)`).
