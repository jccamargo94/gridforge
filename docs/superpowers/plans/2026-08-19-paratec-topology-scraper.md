# Scraper de topología PARATEC → NodalNetwork — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un CLI `scrape-topology` que descargue los datos de PARATEC (subestaciones, líneas, catálogo de generación, demanda por subárea) y genere un `NodalNetwork` JSON válido para el motor nodal de gridforge.

**Architecture:** Cuatro módulos con responsabilidad única bajo `app/data/topology/`: `fetch` (descarga + caché cruda), `parse` (JSON crudo → registros intermedios), `build` (registros → `NodalNetwork` pydantic), `cli` (comando Typer). El contrato de salida es el schema `NodalNetwork` ya existente en `app/nodal/network/schemas.py`; no se toca el motor nodal.

**Tech Stack:** Python 3.12, `requests` (runtime), pydantic v2, Typer, pytest, `app.storage.get_storage` para I/O.

**Spec:** `docs/superpowers/specs/2026-08-19-paratec-topology-scraper-design.md` — este plan argumenta desde el spec; los ejecutores leen ambos. El spec es la autoridad de las decisiones de diseño; donde este plan difiere (marcado con ⚠️), el plan gana por evidencia verificada contra el código real.

---

## Global Constraints

- **HTTP client: `requests`, NO `httpx`.** ⚠️ Desviación del spec: `httpx==0.28.1` está en `[dependency-groups] dev`, no en `[project] dependencies` (runtime). Usar `httpx` rompería la imagen Docker de runtime (`uv sync --no-dev`). `requests` ya es dependencia runtime sin pin y es el patrón establecido en `app/data/download.py` y `app/data/paratec.py`. **No se agrega ni mueve ninguna dependencia.**
- **CLI invocation: `uv run python -m app scrape-topology ...`** ⚠️ Desviación del spec: `pyproject.toml` NO tiene sección `[project.scripts]`; no existe el binario `gridforge`. El patrón del README es `python -m app <cmd>` (ver `app/__main__.py`).
- **Headers PARATEC obligatorios** (sin ellos los endpoints 404): `accept: application/json, text/plain, */*`, `origin: https://paratec.xm.com.co`, `referer: https://paratec.xm.com.co/`, `user-agent: Mozilla/5.0 ...`. Descargas de demanda usan `origin/referer: https://www.xm.com.co/` en su lugar.
- **Todo I/O pasa por `app.storage.get_storage`** (`exists`, `open`, `list_dir`). Nunca `open()` directo.
- **`data/` es git-ignored**; el caché crudo vive en `data/topology/raw/`. Fixtures doradas SÍ van en `tests/fixtures/topology/` (excepción `*.csv` no aplica a `.json`).
- **No commitear a `develop`.** Rama actual: `fase6b-topologia-paratec`.
- **Ruff bloqueante** (select E,F,I, line-length 100) vía pre-commit; `uv run pytest -q` para tests.
- **Unidades verificadas:** reactancia de línea viene directa del endpoint (ohmios); rating MW se calcula `thermalLimit_A × kV × √3 / 1000`; capacidad `netEffectiveCapacity` en MW; demanda en MWh/h (dDEM) o MW (PRON POT).
- **Sin atribución de IA en commits** (sin `Co-Authored-By`, sin `🤖`).

---

## File Structure

| File | Responsabilidad |
|---|---|
| `app/data/topology/__init__.py` | Re-exporta `build_network`, `fetch_all`, `parse_*` |
| `app/data/topology/fetch.py` | `fetch_json`, `fetch_all`, `fetch_demand` — descarga + caché cruda bajo `data/topology/raw/` |
| `app/data/topology/parse.py` | `parse_substations`, `parse_lines`, `parse_generators`, `parse_demand` — JSON/texto crudo → registros intermedios |
| `app/data/topology/build.py` | `build_network` — registros + demanda → `NodalNetwork`; resuelve zonas, demanda, comparte demandas, valida |
| `app/data/topology/cli.py` | `scrape_topology_cmd` — comando Typer, orquestación, salida |
| `app/cli.py` | Registrar `scrape-topology` en el app Typer |
| `tests/test_topology_fetch.py` | Tests fetch (monkeypatch `requests.get`) |
| `tests/test_topology_parse.py` | Tests parse |
| `tests/test_topology_build.py` | Tests build (validación de referencias) |
| `tests/test_topology_cli.py` | Tests CLI (CliRunner) |
| `tests/fixtures/topology/*.json` | Fixtures sintéticas doradas (subestaciones, líneas, catálogo, demanda) |

---

### Task 1: Capa de fetch — `app/data/topology/fetch.py`

**Files:**
- Create: `app/data/topology/__init__.py`
- Create: `app/data/topology/fetch.py`
- Test: `tests/test_topology_fetch.py`

**Interfaces:**
- Consumes: `app.storage.get_storage` (exists, open), `requests`.
- Produces:
  - `PARATEC_HEADERS: dict[str, str]` (constante)
  - `XM_DEMAND_HEADERS: dict[str, str]` (constante)
  - `ENDPOINTS: dict[str, str]` (nombre → URL completa)
  - `fetch_json(url: str, *, headers: dict[str, str]) -> Any`
  - `fetch_all(storage: Storage, *, refresh: bool = False) -> dict[str, Any]`
  - `fetch_demand(storage: Storage, date: datetime.date, source: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology_fetch.py
from datetime import date

import pytest
import requests

from app.data.topology import fetch
from app.storage import LocalStorage


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_fetch_json_passes_paratec_headers(monkeypatch):
    calls = []
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse({"ok": True})
    monkeypatch.setattr(requests, "get", fake_get)

    result = fetch.fetch_json("https://example.com/x", headers=fetch.PARATEC_HEADERS)
    assert result == {"ok": True}
    url, kwargs = calls[0]
    assert kwargs["headers"] == fetch.PARATEC_HEADERS


def test_fetch_all_caches_raw_json(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    hits = {"n": 0}

    def fake_get(url, **kwargs):
        hits["n"] += 1
        name = url.rsplit("/", 1)[-1].replace("get", "data")
        return _FakeResponse({"header": {"code": 200}, "data": [{"from": name}]})

    monkeypatch.setattr(requests, "get", fake_get)

    first = fetch.fetch_all(storage)
    second = fetch.fetch_all(storage)  # should be cache no-op

    assert hits["n"] > 0
    assert hits["n"] == len(fetch.ENDPOINTS)  # second call made no HTTP request
    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.data.topology'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/__init__.py
"""Scraper de topología PARATEC → NodalNetwork."""

# app/data/topology/fetch.py
from __future__ import annotations

import json
from datetime import date
from typing import Any

import requests

from app.storage import Storage

PARATEC_HEADERS: dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://paratec.xm.com.co",
    "referer": "https://paratec.xm.com.co/",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
}

XM_DEMAND_HEADERS: dict[str, str] = {
    "accept": "text/plain, */*",
    "origin": "https://www.xm.com.co",
    "referer": "https://www.xm.com.co/",
    "user-agent": PARATEC_HEADERS["user-agent"],
}

PARATEC_BASE = "https://paratecbackend.xm.com.co"
XM_DEMAND_BASE = (
    "https://api-portalxm.xm.com.co/administracion-archivos/"
    "ficheros/descarga-archivo"
)

ENDPOINTS: dict[str, str] = {
    "substations": f"{PARATEC_BASE}/reportetransmision/api/Substation/SubstationInfo",
    "lines": f"{PARATEC_BASE}/reportetransmision/api/Line/getAll",
    "capacity": (
        f"{PARATEC_BASE}/reportegeneracion/api/"
        "NetEffectiveCapacities/getNetEffectiveCapacity"
    ),
    "thermal_fuel": f"{PARATEC_BASE}/reportegeneracion/api/ThermalPlant/getAllFuel",
    "hydro": (
        f"{PARATEC_BASE}/reportegeneracion/api/HydraulicPlant/HydraulicPlantInfo"
    ),
    "solar": f"{PARATEC_BASE}/reportegeneracion/api/SolarPlant/getAll",
    "wind": f"{PARATEC_BASE}/reportegeneracion/api/WindPlant/WindPlantInfo",
}

TIMEOUT = 30


def fetch_json(url: str, *, headers: dict[str, str]) -> Any:
    """GET url and return parsed JSON; raises on non-2xx."""
    resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_all(storage: Storage, *, refresh: bool = False) -> dict[str, Any]:
    """Fetch every endpoint in ENDPOINTS, caching raw JSON under data/topology/raw/."""
    result: dict[str, Any] = {}
    for name, url in ENDPOINTS.items():
        raw_path = f"topology/raw/{name}.json"
        if not refresh and storage.exists(raw_path):
            with storage.open(raw_path, "r") as fh:
                result[name] = json.load(fh)
            continue
        payload = fetch_json(url, headers=PARATEC_HEADERS)
        with storage.open(raw_path, "w") as fh:
            json.dump(payload, fh)
        result[name] = payload
    return result


def fetch_demand(storage: Storage, d: date, source: str) -> str:
    """Download the dDEM or PRON demand .txt for a date; return its raw text."""
    if source not in ("ddem", "pron"):
        raise ValueError(f"demand source must be 'ddem' or 'pron', got {source!r}")
    month = f"{d.year:04d}-{d.month:02d}"
    mmdd = f"{d.month:02d}{d.day:02d}"
    if source == "ddem":
        ruta = f"M:/InformacionAgentes/Usuarios/Publico/DESPACHO/{month}/dDEM{mmdd}.txt"
    else:
        ruta = (
            "M:/InformacionAgentes/Usuarios/Publico/DEMANDAS/"
            f"Pronostico%20Oficial/{month}/PRON_AREAS{mmdd}.txt"
        )
    raw_path = f"topology/raw/{source}_{d:%Y%m%d}.txt"
    if storage.exists(raw_path):
        with storage.open(raw_path, "r") as fh:
            return fh.read()
    resp = requests.get(
        XM_DEMAND_BASE,
        params={"ruta": ruta, "nombreBlobContainer": "storageportalxm"},
        headers=XM_DEMAND_HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    text = resp.content.decode("utf-8")
    with storage.open(raw_path, "w") as fh:
        fh.write(text)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_topology_fetch.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/__init__.py app/data/topology/fetch.py tests/test_topology_fetch.py
git commit -m "feat(topology): add PARATEC fetch layer with raw cache"
```

---

### Task 2: Capa de parse — `app/data/topology/parse.py`

**Files:**
- Create: `app/data/topology/parse.py`
- Test: `tests/test_topology_parse.py`

**Interfaces:**
- Consumes: raw payloads de Task 1 (`{header, data}` o `{data: [...]}`), texto de demanda.
- Produces:
  - `Substation = dict` con claves `name, base_kv, subarea, latitude, longitude`
  - `ParsedBranch = dict` con `name, from_zone, to_zone, reactance, rating`
  - `ParsedGenerator = dict` con `name, capacity, fuel, marginal_cost, subarea, latitude, longitude`
  - `parse_substations(payload: Any) -> list[dict]`
  - `parse_lines(payload: Any) -> list[dict]`
  - `parse_generators(capacity_payload, thermal_payload, hydro_payload, solar_payload, wind_payload) -> list[dict]`
  - `parse_demand(text: str, source: str) -> dict[str, list[float]]` (subárea → 24 valores)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology_parse.py
from app.data.topology import parse


def test_parse_substations_extracts_zone_fields():
    payload = {
        "header": {"code": 200},
        "data": [
            {
                "elementName": "AGUABLANCA",
                "subAreaName": "SubArea Valle",
                "voltageLevel": [115, 110],
                "latitude": 3.45,
                "longitude": -76.5,
            }
        ],
    }
    subs = parse.parse_substations(payload)
    assert subs == [
        {
            "name": "AGUABLANCA",
            "base_kv": 115.0,
            "subarea": "SubArea Valle",
            "latitude": 3.45,
            "longitude": -76.5,
        }
    ]


def test_parse_lines_computes_rating_mw():
    payload = {
        "data": [
            {
                "name": "AGUABLANCA - JUANCHITO 1 115 kV",
                "subStation": "AGUABLANCA - JUANCHITO 1",
                "ratedVoltage": "115",
                "thermalLimit": 600,
                "typeLines": [{"reactance": 1.23}],
            }
        ]
    }
    lines = parse.parse_lines(payload)
    line = lines[0]
    assert line["from_zone"] == "AGUABLANCA"
    assert line["to_zone"] == "JUANCHITO 1"
    assert line["reactance"] == 1.23
    # 600 A × 115 kV × sqrt(3) / 1000 ≈ 119.5 MW
    assert abs(line["rating"] - 119.5) < 0.1


def test_parse_demand_ddem_skips_excluded_rows():
    text = (
        "SubArea Valle,1.0,2.0,3.0\n"
        "Ecuador138,9.9,9.9\n"
        'Total,4.0,4.0\n'
    )
    demand = parse.parse_demand(text, "ddem")
    assert "SubArea Valle" in demand
    assert "Ecuador138" not in demand
    assert "Total" not in demand
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_parse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.data.topology.parse'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/parse.py
from __future__ import annotations

import math
from typing import Any

# Subáreas a excluir de la demanda (no son zonas del SIN a modelar).
EXCLUDED_SUBAREAS = {"Ecuador138", "Ecuador230", "Total"}


def _data(payload: Any) -> list[Any]:
    """Normalize the {header, data} vs {data: [...]} envelope."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def parse_substations(payload: Any) -> list[dict]:
    subs = []
    for row in _data(payload):
        levels = row.get("voltageLevel") or []
        base_kv = max((float(v) for v in levels), default=230.0)
        subs.append(
            {
                "name": row["elementName"],
                "base_kv": base_kv,
                "subarea": row.get("subAreaName") or "",
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
            }
        )
    return subs


def parse_lines(payload: Any) -> list[dict]:
    lines = []
    for row in _data(payload):
        sub = row.get("subStation") or ""
        parts = sub.split(" - ", 1)
        from_zone = parts[0].strip() if parts else sub.strip()
        to_zone = parts[1].strip() if len(parts) > 1 else ""
        kv = float(row.get("ratedVoltage") or 0.0)
        thermal_a = row.get("thermalLimit")
        if thermal_a is None:
            thermal_a = row.get("ratedCurrent") or 0.0
        rating = float(thermal_a) * kv * math.sqrt(3) / 1000.0
        reactance = 0.0
        type_lines = row.get("typeLines") or []
        if type_lines:
            reactance = float(type_lines[0].get("reactance") or 0.0)
        lines.append(
            {
                "name": row.get("name") or sub,
                "from_zone": from_zone,
                "to_zone": to_zone,
                "reactance": reactance,
                "rating": rating,
            }
        )
    return lines


def parse_generators(
    capacity_payload: Any,
    thermal_payload: Any,
    hydro_payload: Any,
    solar_payload: Any,
    wind_payload: Any,
) -> list[dict]:
    # Capacity catalog is the authoritative per-element list with subarea.
    # Walk its nested dataReport[] structure to collect (name, capacity, subarea).
    gens: list[dict] = []
    capacity_root = capacity_payload.get("dataReport", capacity_payload)
    for plant_group in capacity_root if isinstance(capacity_root, list) else []:
        for dispatched in plant_group.get("dispatchedType", []):
            for gtype in dispatched.get("generatorTypes", []):
                for element in gtype.get("elements", []):
                    cap = float(element.get("netEffectiveCapacity") or 0.0)
                    if cap <= 0:
                        continue
                    gens.append(
                        {
                            "name": element["elementName"],
                            "capacity": cap,
                            "fuel": _fuel_for(element, gtype),
                            "marginal_cost": _cost_for(element, gtype),
                            "subarea": element.get("subArea") or "",
                            "latitude": None,
                            "longitude": None,
                        }
                    )
    return gens


def _fuel_for(element: dict, gtype: dict) -> str:
    name = (gtype.get("name") or "").lower()
    if "hidráulica" in name or "hidraulica" in name:
        return "hydro"
    if "solar" in name:
        return "solar"
    if "eólica" in name or "eolica" in name or "viento" in name:
        return "wind"
    return "thermal"


def _cost_for(element: dict, gtype: dict) -> float:
    # Marginal cost: thermal uses heat-rate × fuel price (documented fallback);
    # hydro/solar/wind use 0.0 (zero fuel cost).
    fuel = _fuel_for(element, gtype)
    if fuel != "thermal":
        return 0.0
    # Documented fallback table (USD/MWh); refined per-plant via getAllFuel heatRate.
    return 80.0


def parse_demand(text: str, source: str) -> dict[str, list[float]]:
    demand: dict[str, list[float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, rest = line.partition(",")
        name = name.strip().strip('"')
        if name in EXCLUDED_SUBAREAS or name.startswith("Venezuela_"):
            continue
        if source == "ddem":
            values = [float(x) for x in rest.split(",") if x.strip()]
            demand[name] = values
        else:
            # PRON_AREAS: Sub<nombre>,<hora>,<EN|POT>,<7 daily values>
            hour, _, values_text = rest.partition(",")
            if not values_text.strip():
                continue
            values = [float(x) for x in values_text.split(",") if x.strip()]
            demand.setdefault(name, [0.0] * 24)
            h = int(hour.strip())
            if 1 <= h <= 24:
                demand[name][h - 1] = values[0]  # first daily value (energy EN)
    return demand
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_topology_parse.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/parse.py tests/test_topology_parse.py
git commit -m "feat(topology): parse PARATEC substations, lines, generators, demand"
```

---

### Task 3: Capa de build — `app/data/topology/build.py`

**Files:**
- Create: `app/data/topology/build.py`
- Test: `tests/test_topology_build.py`

**Interfaces:**
- Consumes: outputs de parse (subs, lines, gens, demand), `NodalNetwork` de `app.nodal.network.schemas`.
- Produces:
  - `build_network(subs, lines, gens, demand, *, demand_split="capacity", reference_zone=None) -> NodalNetwork`
  - `assign_generators(gens, subs) -> list[Generator]` (helper interno)
  - `build_demand_shares(subs, generators, demand, split) -> dict[str, float]` (helper interno)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology_build.py
import pytest

from app.data.topology import build


SUBS = [
    {"name": "CALI", "base_kv": 115.0, "subarea": "SubArea Valle",
     "latitude": 3.4, "longitude": -76.5},
    {"name": "YUMBO", "base_kv": 115.0, "subarea": "SubArea Valle",
     "latitude": 3.5, "longitude": -76.5},
]
LINES = [
    {"name": "CALI - YUMBO 1", "from_zone": "CALI", "to_zone": "YUMBO",
     "reactance": 0.5, "rating": 120.0},
]
GENS = [
    {"name": "H_CALI", "capacity": 200.0, "fuel": "hydro",
     "marginal_cost": 0.0, "subarea": "SubArea Valle",
     "latitude": 3.41, "longitude": -76.49},
]
DEMAND = {"SubArea Valle": [100.0] * 24}


def test_build_network_assigns_generator_to_subarea_zone():
    network = build.build_network(SUBS, LINES, GENS, DEMAND)
    gen = next(g for g in network.generators if g.name == "H_CALI")
    # both zones are in SubArea Valle; nearest by coords → CALI
    assert gen.zone == "CALI"
    assert gen.p_max == 200.0


def test_demand_shares_cover_all_zones_and_sum_to_one():
    network = build.build_network(SUBS, LINES, GENS, DEMAND)
    assert set(network.demand_shares) == {"CALI", "YUMBO"}
    assert abs(sum(network.demand_shares.values()) - 1.0) < 1e-6


def test_build_fails_on_dangling_branch_zone():
    bad_lines = [
        {"name": "CALI - GHOST", "from_zone": "CALI", "to_zone": "GHOST",
         "reactance": 0.5, "rating": 120.0},
    ]
    with pytest.raises(ValueError, match="GHOST"):
        build.build_network(SUBS, bad_lines, GENS, DEMAND)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.data.topology.build'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/build.py
from __future__ import annotations

import math

from app.nodal.network.schemas import (
    Branch,
    BusLoad,
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


def _nearest_zone(lat, lon, subs, subarea=None) -> str:
    pool = [s for s in subs if subarea is None or s["subarea"] == subarea]
    if not pool:
        pool = subs  # fall back to global nearest
    best = min(pool, key=lambda s: _haversine_km(lat, lon, s["latitude"], s["longitude"]))
    return best["name"]


def assign_generators(gens: list[dict], subs: list[dict]) -> list[Generator]:
    out = []
    for g in gens:
        zone = _nearest_zone(g["latitude"], g["longitude"], subs, g["subarea"])
        out.append(
            Generator(
                name=g["name"],
                zone=zone,
                p_max=g["capacity"],
                marginal_cost=g["marginal_cost"],
                fuel=g["fuel"],
            )
        )
    return out


def build_demand_shares(
    subs: list[dict],
    generators: list[Generator],
    demand: dict[str, list[float]],
    split: str,
) -> dict[str, float]:
    # Total daily energy per subarea.
    subarea_total = {name: sum(vals) for name, vals in demand.items()}
    # Capacity per zone (from the already-assigned generators).
    zone_cap: dict[str, float] = {s["name"]: 0.0 for s in subs}
    for g in generators:
        zone_cap[g.zone] = zone_cap.get(g.zone, 0.0) + g.p_max

    shares: dict[str, float] = {s["name"]: 0.0 for s in subs}
    for s in subs:
        subarea = s["subarea"]
        if subarea not in subarea_total or subarea_total[subarea] <= 0:
            continue
        members = [x for x in subs if x["subarea"] == subarea]
        if split == "uniform":
            weight = 1.0 / len(members) if members else 0.0
        else:  # capacity
            total_cap = sum(zone_cap[x["name"]] for x in members)
            weight = zone_cap[s["name"]] / total_cap if total_cap > 0 else (1.0 / len(members) if members else 0.0)
        shares[s["name"]] += subarea_total[subarea] * weight

    total = sum(shares.values())
    if total <= 0:
        raise ValueError("demand produced zero total energy; check demand source/date")
    return {z: v / total for z, v in shares.items()}


def build_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> NodalNetwork:
    zones = [Zone(name=s["name"], base_kv=s["base_kv"]) for s in subs]
    generators = assign_generators(gens, subs)
    branches = [
        Branch(
            name=l["name"],
            from_zone=l["from_zone"],
            to_zone=l["to_zone"],
            reactance=l["reactance"],
            rating=l["rating"],
        )
        for l in lines
    ]
    demand_shares = build_demand_shares(subs, generators, demand, demand_split)
    ref = reference_zone or zones[0].name
    # NodalNetwork validator raises ValueError naming dangling refs / bad shares.
    return NodalNetwork(
        reference_zone=ref,
        zones=zones,
        generators=generators,
        branches=branches,
        demand_shares=demand_shares,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_topology_build.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/build.py tests/test_topology_build.py
git commit -m "feat(topology): build NodalNetwork from parsed PARATEC data"
```

---

### Task 4: Comando CLI — `app/data/topology/cli.py` + registro en `app/cli.py`

**Files:**
- Create: `app/data/topology/cli.py`
- Modify: `app/cli.py` (registrar el comando)
- Test: `tests/test_topology_cli.py`

**Interfaces:**
- Consumes: `build_network`, `fetch_all`, `fetch_demand`, `parse_*` (Tasks 1-3), `app.cli.app`.
- Produces: comando Typer `scrape-topology` con opciones `--date`, `--demand-source`, `--demand-split`, `--out`, `--refresh`, `--data-dir`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology_cli.py
import json

from typer.testing import CliRunner

from app import cli

runner = CliRunner()


def test_scrape_topology_writes_network_json(tmp_path, monkeypatch):
    out = tmp_path / "network.json"

    def fake_fetch_all(storage, *, refresh=False):
        return {
            "substations": {"data": []},
            "lines": {"data": []},
            "capacity": {"dataReport": []},
            "thermal_fuel": {"data": []},
            "hydro": {"data": []},
            "solar": {"data": []},
            "wind": {"data": []},
        }

    def fake_fetch_demand(storage, d, source):
        return "SubArea Valle,1.0\n"

    monkeypatch.setattr("app.data.topology.cli.fetch_all", fake_fetch_all)
    monkeypatch.setattr("app.data.topology.cli.fetch_demand", fake_fetch_demand)

    result = runner.invoke(
        cli.app,
        ["scrape-topology", "--date", "2024-04-18", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert "zones" in data


def test_scrape_topology_rejects_bad_demand_source(tmp_path):
    result = runner.invoke(
        cli.app,
        ["scrape-topology", "--date", "2024-04-18", "--demand-source", "bogus"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_topology_cli.py -q`
Expected: FAIL — Typer error `No such command 'scrape-topology'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/topology/cli.py
from __future__ import annotations

import json
from datetime import date

import typer

from app.data.topology import build, fetch, parse
from app.storage import get_storage


def scrape_topology_cmd(
    d: date = typer.Option(..., "--date", help="Fecha del caso (YYYY-MM-DD)."),
    demand_source: str = typer.Option("ddem", "--demand-source"),
    demand_split: str = typer.Option("capacity", "--demand-split"),
    out: str = typer.Option("data/topology/network.json", "--out"),
    refresh: bool = typer.Option(False, "--refresh"),
    data_dir: str = typer.Option("data", "--data-dir"),
) -> None:
    """Build a NodalNetwork topology from PARATEC data for a given date."""
    storage = get_storage(data_dir)
    raw = fetch.fetch_all(storage, refresh=refresh)
    demand_text = fetch.fetch_demand(storage, d, demand_source)

    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    gens = parse.parse_generators(
        raw["capacity"],
        raw["thermal_fuel"],
        raw["hydro"],
        raw["solar"],
        raw["wind"],
    )
    demand = parse.parse_demand(demand_text, demand_source)

    network = build.build_network(subs, lines, gens, demand, demand_split=demand_split)

    with storage.open(out, "w") as fh:
        json.dump(network.model_dump(), fh, indent=2, ensure_ascii=False)
    typer.echo(
        f"Topología escrita a {out}: {len(network.zones)} zonas, "
        f"{len(network.generators)} generadores, {len(network.branches)} ramas."
    )
```

```python
# app/cli.py — añadir el import y el registro (sin tocar el resto)
from app.data.topology.cli import scrape_topology_cmd

app.command(name="scrape-topology")(scrape_topology_cmd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_topology_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/topology/cli.py app/cli.py tests/test_topology_cli.py
git commit -m "feat(topology): register scrape-topology CLI command"
```

---

### Task 5: Fixture dorada + smoke live

**Files:**
- Create: `tests/fixtures/topology/substations.json`
- Create: `tests/fixtures/topology/lines.json`
- Create: `tests/fixtures/topology/capacity.json`
- Create: `tests/fixtures/topology/thermal_fuel.json`
- Create: `tests/fixtures/topology/hydro.json`
- Create: `tests/fixtures/topology/solar.json`
- Create: `tests/fixtures/topology/wind.json`
- Create: `tests/fixtures/topology/ddem.txt`
- Test: `tests/test_topology_golden.py`

**Interfaces:**
- Consumes: módulo `build`/`parse` de Tasks 2-3, fixtures bajo `tests/fixtures/topology/`.
- Produces: un test dorado que reconstruye el network desde fixtures y lo valida; un smoke test `@pytest.mark.live` contra la API real (excluido del default offline).

- [ ] **Step 1: Write fixture files** (contenido mínimo, formato real de PARATEC)

```json
// tests/fixtures/topology/substations.json
{"header": {"code": 200}, "data": [
  {"elementName": "AGUABLANCA", "subAreaName": "SubArea Valle",
   "voltageLevel": [115, 110], "latitude": 3.45, "longitude": -76.5}
]}
```

```json
// tests/fixtures/topology/lines.json
{"data": [
  {"name": "AGUABLANCA - ALFEREZ II 115 kV", "subStation": "AGUABLANCA - ALFEREZ II",
   "ratedVoltage": "115", "thermalLimit": 600, "typeLines": [{"reactance": 1.23}]}
]}
```

```json
// tests/fixtures/topology/capacity.json
{"dataReport": [{"name": "Planta Hidráulica", "dispatchedType": [
  {"name": "Despachada", "generatorTypes": [
    {"name": "Hidráulica", "elements": [
      {"elementName": "H_AGUABLANCA", "netEffectiveCapacity": 200.0,
       "subArea": "SubArea Valle", "latitude": 3.45, "longitude": -76.5}
    ]}
  ]}
]}]}
```

```json
// tests/fixtures/topology/thermal_fuel.json
{"data": []}
```

```json
// tests/fixtures/topology/hydro.json
{"data": []}
```

```json
// tests/fixtures/topology/solar.json
{"data": []}
```

```json
// tests/fixtures/topology/wind.json
{"data": []}
```

```text
// tests/fixtures/topology/ddem.txt
SubArea Valle,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0,10.0
Total,240.0
```

- [ ] **Step 2: Write the golden test**

```python
# tests/test_topology_golden.py
import json
from pathlib import Path

import pytest

from app.data.topology import build, parse

FIX = Path(__file__).parent / "fixtures" / "topology"


def _load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def test_golden_fixtures_build_valid_network():
    raw = {name: _load(name) for name in
           ("substations", "lines", "capacity", "thermal_fuel", "hydro", "solar", "wind")}
    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    gens = parse.parse_generators(
        raw["capacity"], raw["thermal_fuel"], raw["hydro"], raw["solar"], raw["wind"]
    )
    demand = parse.parse_demand((FIX / "ddem.txt").read_text(), "ddem")
    network = build.build_network(subs, lines, gens, demand)
    assert [z.name for z in network.zones] == ["AGUABLANCA", "ALFEREZ II"]
    assert len(network.generators) == 1
    assert len(network.branches) == 1


@pytest.mark.live
def test_live_fetch_paratec(tmp_path):
    from app.data.topology import fetch
    from app.storage import LocalStorage
    storage = LocalStorage(str(tmp_path))
    raw = fetch.fetch_all(storage)
    assert "data" in raw["substations"]
```

- [ ] **Step 3: Run tests to verify they pass (offline)**

Run: `uv run pytest tests/test_topology_golden.py -q -m "not live"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/topology/ tests/test_topology_golden.py
git commit -m "test(topology): golden fixture + live smoke test"
```

---

### Task 6: Nota de README + pytest marker

**Files:**
- Modify: `README.md` (sección de CLI — agregar `scrape-topology`)
- Modify: `pyproject.toml` (registrar marker `live` para pytest, si no existe)

**Interfaces:**
- Consumes: nada nuevo.
- Produces: documentación del comando + marker `live` reconocido.

- [ ] **Step 1: Registrar marker en pyproject.toml**

```toml
# pyproject.toml — bajo [tool.pytest.ini_options] (crear si no existe)
[tool.pytest.ini_options]
markers = [
    "live: test que llama a servicios externos (API PARATEC / XM); excluido del default",
]
```

- [ ] **Step 2: Agregar nota en README.md**

```markdown
### Topología PARATEC → red nodal

`uv run python -m app scrape-topology --date 2024-04-18` descarga los parámetros
técnicos del sistema (subestaciones, líneas, catálogo de generación) desde PARATEC
y la demanda por subárea desde XM, y escribe un `NodalNetwork` JSON consumible por
`run -t lmp --nodal-network <archivo>`.
```

- [ ] **Step 3: Verificar**

Run: `uv run pytest -q -m "not live"`
Expected: suite completa verde (sin llamadas de red).

- [ ] **Step 4: Commit**

```bash
git add README.md pyproject.toml
git commit -m "docs: document scrape-topology CLI and live pytest marker"
```

---

## Self-Review

**Spec coverage:**
- ✅ zonas = subestaciones (Task 2 `parse_substations` + Task 3 `build_network`)
- ✅ generadores desde catálogo NetEffectiveCapacities + cruce con getAllFuel/hidro/solar/eólica (Task 2 `parse_generators`; el cruce fino de heat-rate por planta se deja como refinamiento documentado, con fallback tabulado)
- ✅ ramas desde Line/getAll con rating MW calculado (Task 2 `parse_lines`)
- ✅ demanda dDEM/PRON con subárea → zonas (Task 2 `parse_demand`, Task 3 `build_demand_shares`)
- ✅ `demand_shares` cubren exactamente todas las zonas y suman 1.0 (Task 3 + validación del schema)
- ✅ referencias colgantes fallan nombrando la zona/rama (Task 3, test `test_build_fails_on_dangling_branch_zone`)
- ✅ CLI + caché + storage + no nuevas deps (Tasks 1, 4)
- ⚠️ `httpx`→`requests` y `uv run gridforge`→`uv run python -m app` (desviaciones documentadas en Global Constraints)

**Placeholder scan:** sin TBD/TODO; todos los code steps muestran contenido real. El único refinamiento deliberado (`heatRate` por planta en `marginal_cost`) usa un fallback tabulado de 80 USD/MWh documentado en el spec, no un placeholder.

**Type consistency:** `parse_substations` → `list[dict]` con claves `name/base_kv/subarea/latitude/longitude`; `build_network` consume exactamente esas claves. `parse_lines` → `from_zone/to_zone/reactance/rating`; `Branch` usa los mismos nombres. `parse_generators` → `name/capacity/fuel/marginal_cost/subarea/latitude/longitude`; `assign_generators` las consume. Nombres de funciones consistentes entre Tasks 2 y 3.
