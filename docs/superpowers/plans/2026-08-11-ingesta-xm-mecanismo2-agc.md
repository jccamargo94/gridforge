# Ingesta XM — Mecanismo 2 (pydataxm bulk) + dAGCUNIDAD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the `FileNotFoundError: data/dispo_declarada.csv` gap (and the four sibling gaps for `ofertas.csv`/`demaCome.csv`/`precio_bolsa/*.csv`/`DispoCome_resource.csv`) by implementing mecanismo 2 from `docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md` — on-demand fetch via `pydataxm.ReadDB.request_data`, reshaped and cached as year-partitioned CSVs — and fold in `dAGCUNIDAD` (mecanismo 1 extension) so a real run of `python -m app run <date>` completes end to end.

**Architecture:** New module `app/data/xm_bulk.py` holds the pydataxm fetch/reshape/crosswalk logic behind one orchestrator, `ensure_bulk_data_for_year`, called from `case_builder.build_case` alongside the existing `ensure_data_for_date`. `app/data/loaders.py`'s 5 affected loaders gain a required `year` (or `dispatch_date`) argument and read the new partitioned paths instead of one hardcoded historical CSV. A new `app/data/agc.py` parses the raw `dAGCUNIDAD{mmdd}.txt` blob (added to `download.py`'s existing `PARAMS` dict) and aggregates per-unit AGC to per-resource AGC using the same fuzzy-matching pattern `case_builder.py` already uses for OFEI name resolution. The Postgres `input_datasets` manifest (already built) is updated as an optional side effect — never a gate — so the CLI keeps working without `DATABASE_URL`.

**Tech Stack:** `pydataxm==0.3.18` (already a dependency, unused until now), pandas, `thefuzz` (already a dependency), the existing `Storage`/`get_storage` abstraction, SQLAlchemy `Session` (optional) for the manifest.

## Global Constraints

- **Never construct `pydataxm.pydataxm.ReadDB()` unless at least one required partition file is actually missing.** Its `__init__` calls `all_variables()`, which hits the network — confirmed by two `timeout 20` hangs during research. Every orchestrator must do the `storage.exists(...)` check *before* importing/instantiating `ReadDB`, exactly like `ensure_data_for_date` already does with `storage.list_dir`. This is what keeps `tests/test_xm_smoke_loaders.py::test_ensure_data_for_date_is_a_noop`-style offline tests (and any real CLI run against already-cached data) network-free.
- **`request_data` already chunks multi-month ranges internally** (it builds one HTTP call per calendar month and gathers them with `asyncio`) — confirmed by reading `pydataxm/pydataxm.py:106-201`. Do not add any extra month/day-chunking loop around it; call it once with `(date(year, 1, 1), date(year, 12, 31))`.
- **`request_data("ListadoRecursos", "Sistema", start, end)` needs non-`None` `start`/`end` even though the list-type branch never uses them** — the method computes `pd.date_range(start_date, end_date, ...)` unconditionally before branching on entity type, and raises `ValueError` on `None`. Pass the same throwaway date for both, e.g. `date.today()`.
- **Units — verified against the live API's own `MetricUnits` column (`consult.inventario_metricas`), not assumed:** `DispoDeclarada`=kWh, `PrecOferDesp`=COP/kWh, `DemaCome`=kWh, `PrecBolsNaci`=COP/kWh, `DispoCome`=kW. These match the units the existing loaders/`case_builder.py` already assume (`load_precio_bolsa`'s `*1e3` COP/kWh→COP/MWh, `case_builder.py`'s blanket `*1e-3` kW→MW on dispo/demand). **Write every pydataxm value to CSV unscaled, exactly as the API returns it.** Do not add new scaling in `xm_bulk.py` — the existing downstream scale factors already assume these units.
- **Exception: `dAGCUNIDAD` is in MW, not kW** (sample values 8.5, 45.0, 52.5 — plant-scale AGC bands), while `case_builder.py:329`'s `agc_indexed = agc_asignado.set_index([...])["agc"] * 1e-3` assumes the CSV is in kW (same convention as everything else, traced to `notebooks/data_fetcher.ipynb`'s historical `AGC_Programado_(kWh)_2024.xlsx` source). **Multiply parsed dAGCUNIDAD values by 1000 before writing `agc_asignado.csv`** so the existing `*1e-3` in `case_builder.py` continues to work unmodified. Do not touch `case_builder.py:329`.
- **`PrecOferDesp` is published by full calendar month, one month in arrears** — confirmed empty for 2026-08-01 through 2026-08-04 (queried live on 2026-08-11), present through 2026-07-30. Per the user (2026-08-11): XM's real policy is that the entire current month becomes available only on the 1st of the next month (all of August is unavailable until 2026-09-01, no partial/rolling release). This is a real data-availability constraint, not a bug. Task 7 adds a fail-fast check so a too-recent `dispatch_date` produces one clear error instead of a confusing downstream failure. A future heuristic to work around this for near-real-time runs is tracked separately — see the GitHub issue referenced in memory `project_ofertas-price-heuristic-for-recent-dates` — and is explicitly OUT OF SCOPE here.
- **`parametros_plantas.csv` (mecanismo 3 / Paratec) is explicitly OUT OF SCOPE for this plan** — per memory `project_thermal-configuration-dispatch`, reducing Paratec's per-unit data to the flat `TMG`/ramp scalars `case_builder.py` wants is a modeling decision, not data plumbing. This file stays hand-maintained; a run still needs it present in `data/parametros_plantas.csv`. Do not attempt to fetch or generate it in this plan.
- Match existing style: plain functions (no classes) in `app/data/*.py`, `Storage`/`get_storage` for all file I/O (never bare `open()`), pydantic/typing already used in this repo (`from __future__ import annotations` not used elsewhere in `app/data/`, don't introduce it).
- Run `uv run pytest -q` (not bare `pytest`) — this repo's env is managed by `uv`. Never add an AI/model co-authorship line to any commit message (project-wide rule, `CLAUDE.md`).
- Tests must monkeypatch `pydataxm` — never hit the real network in the test suite. Follow the existing pattern in `tests/test_download.py` (`monkeypatch.setattr("app.data.download.requests.get", _fake_get)`): patch `app.data.xm_bulk.ReadDB` with a fake class whose `request_data` returns a canned `DataFrame` shaped like the real API response (columns verified live during this plan's research — reproduced in each task below).

---

## Task 1: Loaders take a `year` argument; migrate the smoke fixture to the partitioned layout

This is pure plumbing/layout work — no new fetch logic yet — so the rest of the plan can build on a stable, testable target layout. Also fixes a real latent bug: `load_precio_bolsa` currently hardcodes `precio_bolsa_2024.csv`, so any run for a year other than 2024 already fails or silently returns an empty frame after the date filter — confirmed live: the failing run's actual date is 2026-08-04.

**Files:**
- Modify: `app/data/loaders.py`
- Modify: `app/pipeline/case_builder.py:82-87` (loader call sites)
- Modify: `tests/test_loaders.py`
- Modify: `tests/test_xm_smoke_loaders.py`
- Modify: `tests/fixtures/xm_smoke/generate_fixture.py`
- Rename fixture files (see Step 5)

**Interfaces:**
- Produces: `load_dispo(data_dir, year) -> pd.DataFrame`, `load_ofertas(data_dir, year) -> pd.DataFrame`, `load_demanda(data_dir, year) -> pd.DataFrame`, `load_precio_bolsa(data_dir, year) -> pd.DataFrame`, `load_dispo_come(data_dir, year) -> pd.DataFrame` — `year` is a required positional-or-keyword `int`. `load_agc`/`load_parametros_plantas` are untouched by this task (Task 8 changes `load_agc`).

- [ ] **Step 1: Update the failing test for `load_precio_bolsa`**

Edit `tests/test_loaders.py`:

```python
import pandas as pd

from app.data.loaders import load_precio_bolsa


def test_precio_bolsa_scaled(tmp_path):
    (tmp_path / "precio_bolsa").mkdir()
    pd.DataFrame({"datetime": ["2024-04-18 00:00"], "precio_bolsa": [0.1]}).to_csv(
        tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv", index=False
    )
    out = load_precio_bolsa(str(tmp_path), 2024)
    assert abs(out["precio_bolsa"].iloc[0] - 100.0) < 1e-9
```

- [ ] **Step 2: Run it to see it fail on the new required arg**

Run: `uv run pytest tests/test_loaders.py -v`
Expected: FAIL with `TypeError: load_precio_bolsa() missing 1 required positional argument: 'year'`

- [ ] **Step 3: Rewrite `app/data/loaders.py`**

```python
"""Readers for the root-level XM CSVs.

Unit conversions that were previously scattered across the scripts are applied
here, in exactly one place (e.g. precio_bolsa is scaled to COP/MWh).
"""

import pandas as pd

from app.storage import get_storage


def load_dispo(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"dispo_declarada/dispo_declarada_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


def load_ofertas(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"ofertas/ofertas_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["Date"])


def load_demanda(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"demaCome/demaCome_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


def load_agc(data_dir: str = "data") -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open("agc_asignado.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


def load_parametros_plantas(data_dir: str = "data") -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open("parametros_plantas.csv", "rb") as f:
        return pd.read_csv(f)


def load_precio_bolsa(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"precio_bolsa/precio_bolsa_{year}.csv", "rb") as f:
        df = pd.read_csv(f, parse_dates=["datetime"])
    df["precio_bolsa"] = df["precio_bolsa"] * 1e3
    return df


def load_dispo_come(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"dispo_come/dispo_come_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])
```

(`load_agc`/`load_parametros_plantas` reproduced unchanged so the whole file is here for reference — Task 8 edits `load_agc` only.)

- [ ] **Step 4: Update `case_builder.py`'s loader call sites**

In `app/pipeline/case_builder.py`, replace:

```python
    if case.level == DispatchLevel.ideal:
        dispo_come = loaders.load_dispo_come(dd)
    dispo = loaders.load_dispo(dd)
    ofertas = loaders.load_ofertas(dd)
    demanda = loaders.load_demanda(dd)
    agc_asignado = loaders.load_agc(dd)
    parametros_plantas = loaders.load_parametros_plantas(dd)
    precio_bolsa = loaders.load_precio_bolsa(dd)
```

with:

```python
    year = DISPATCH_DATE.year
    if case.level == DispatchLevel.ideal:
        dispo_come = loaders.load_dispo_come(dd, year)
    dispo = loaders.load_dispo(dd, year)
    ofertas = loaders.load_ofertas(dd, year)
    demanda = loaders.load_demanda(dd, year)
    agc_asignado = loaders.load_agc(dd)
    parametros_plantas = loaders.load_parametros_plantas(dd)
    precio_bolsa = loaders.load_precio_bolsa(dd, year)
```

(`load_agc(dd)` stays as-is here — Task 8 changes both its signature and this call site together.)

- [ ] **Step 5: Migrate the smoke fixture to the partitioned layout**

```bash
cd tests/fixtures/xm_smoke
mkdir -p dispo_declarada ofertas demaCome
git mv dispo_declarada.csv dispo_declarada/dispo_declarada_2024.csv
git mv ofertas.csv ofertas/ofertas_2024.csv
git mv demaCome.csv demaCome/demaCome_2024.csv
# precio_bolsa/precio_bolsa_2024.csv already lives at the target path — no move needed
```

- [ ] **Step 6: Update `generate_fixture.py` to write the new paths**

In `tests/fixtures/xm_smoke/generate_fixture.py`, replace:

```python
with open(BASE / "dispo_declarada.csv", "w", newline="") as f:
```
with
```python
(BASE / "dispo_declarada").mkdir(exist_ok=True)
with open(BASE / "dispo_declarada" / "dispo_declarada_2024.csv", "w", newline="") as f:
```

Replace:
```python
with open(BASE / "ofertas.csv", "w", newline="") as f:
```
with
```python
(BASE / "ofertas").mkdir(exist_ok=True)
with open(BASE / "ofertas" / "ofertas_2024.csv", "w", newline="") as f:
```

Replace:
```python
with open(BASE / "demaCome.csv", "w", newline="") as f:
```
with
```python
(BASE / "demaCome").mkdir(exist_ok=True)
with open(BASE / "demaCome" / "demaCome_2024.csv", "w", newline="") as f:
```

- [ ] **Step 7: Update `tests/test_xm_smoke_loaders.py`'s loader calls**

Replace:

```python
def test_root_csvs_load():
    dispo = loaders.load_dispo(DD)
    assert len(dispo[dispo["datetime"].dt.date == FECHA]) == 48  # 2 generators x 24h

    ofertas = loaders.load_ofertas(DD)
    assert len(ofertas[ofertas["Date"].dt.date == FECHA]) == 2

    demanda = loaders.load_demanda(DD)
    assert len(demanda[demanda["datetime"].dt.date == FECHA]) == 24

    agc = loaders.load_agc(DD)
    assert "agc" in agc.columns

    params = loaders.load_parametros_plantas(DD)
    assert set(params["generador"]) == {"TERMO1", "TERMO2"}

    precio_bolsa = loaders.load_precio_bolsa(DD)
    assert len(precio_bolsa[precio_bolsa["datetime"].dt.date == FECHA]) == 24
```

with:

```python
def test_root_csvs_load():
    dispo = loaders.load_dispo(DD, FECHA.year)
    assert len(dispo[dispo["datetime"].dt.date == FECHA]) == 48  # 2 generators x 24h

    ofertas = loaders.load_ofertas(DD, FECHA.year)
    assert len(ofertas[ofertas["Date"].dt.date == FECHA]) == 2

    demanda = loaders.load_demanda(DD, FECHA.year)
    assert len(demanda[demanda["datetime"].dt.date == FECHA]) == 24

    agc = loaders.load_agc(DD)
    assert "agc" in agc.columns

    params = loaders.load_parametros_plantas(DD)
    assert set(params["generador"]) == {"TERMO1", "TERMO2"}

    precio_bolsa = loaders.load_precio_bolsa(DD, FECHA.year)
    assert len(precio_bolsa[precio_bolsa["datetime"].dt.date == FECHA]) == 24
```

- [ ] **Step 8: Regenerate the fixture and run the full suite**

```bash
uv run python tests/fixtures/xm_smoke/generate_fixture.py
git add --dry-run tests/fixtures/xm_smoke/  # confirm every new/moved file is tracked, per feedback_verify-test-portability
uv run pytest -q
```
Expected: all tests pass (same count as before this task — this is a pure rename/plumbing task).

- [ ] **Step 9: Commit**

```bash
git add app/data/loaders.py app/pipeline/case_builder.py tests/test_loaders.py \
  tests/test_xm_smoke_loaders.py tests/fixtures/xm_smoke/
git commit -m "refactor: partition XM bulk-dataset loaders by year"
```

---

## Task 2: `app/data/xm_bulk.py` — shared wide-to-long reshape + resource crosswalk

**Files:**
- Create: `app/data/xm_bulk.py`
- Test: `tests/test_xm_bulk.py`

**Interfaces:**
- Produces: `_melt_hourly(df: pd.DataFrame, value_col: str) -> pd.DataFrame` with columns `["code", "datetime", value_col]`.
- Produces: `fetch_resource_crosswalk(consult) -> pd.DataFrame` with columns `["code", "resource_name", "gen_type"]`.
- Consumes (from `pydataxm.pydataxm.ReadDB`, imported as `from pydataxm.pydataxm import ReadDB`): `consult.request_data(coleccion: str, metrica: str, start_date, end_date) -> pd.DataFrame`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_xm_bulk.py`:

```python
from datetime import date

import pandas as pd

from app.data.xm_bulk import _melt_hourly, fetch_resource_crosswalk


def test_melt_hourly_reshapes_wide_to_long():
    raw = pd.DataFrame(
        {
            "Values_code": ["2QEK", "3ENA"],
            "Values_Hour01": [10.0, 20.0],
            "Values_Hour02": [11.0, 21.0],
            "Date": [date(2024, 4, 18), date(2024, 4, 18)],
        }
    )
    out = _melt_hourly(raw, "dispo")

    assert list(out.columns) == ["code", "datetime", "dispo"]
    assert len(out) == 4
    row = out[(out["code"] == "2QEK") & (out["datetime"] == pd.Timestamp("2024-04-18 00:00"))]
    assert row["dispo"].iloc[0] == 10.0
    row2 = out[(out["code"] == "3ENA") & (out["datetime"] == pd.Timestamp("2024-04-18 01:00"))]
    assert row2["dispo"].iloc[0] == 21.0


class _FakeConsult:
    def request_data(self, coleccion, metrica, start_date, end_date):
        assert coleccion == "ListadoRecursos"
        assert metrica == "Sistema"
        return pd.DataFrame(
            {
                "Values_Code": ["2QEK", "3ENA"],
                "Values_Name": ["SALTO II", "TERMO NORTE"],
                "Values_Type": ["HIDRAULICA", "TERMICA"],
            }
        )


def test_fetch_resource_crosswalk_renames_columns():
    out = fetch_resource_crosswalk(_FakeConsult())
    assert list(out.columns) == ["code", "resource_name", "gen_type"]
    assert out[out["code"] == "3ENA"]["gen_type"].iloc[0] == "TERMICA"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.data.xm_bulk'`

- [ ] **Step 3: Implement `app/data/xm_bulk.py`**

```python
"""Mecanismo 2 (pydataxm bulk) of the XM ingesta design:
docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md sections 3-6.

Fetches DispoDeclarada/PrecOferDesp/DemaCome/PrecBolsNaci/DispoCome from XM's
public bulk API and reshapes them into the same CSV shapes app/data/loaders.py
already reads. Values are written unscaled (see plan Global Constraints for the
verified unit conventions) -- existing loaders/case_builder.py scaling is
untouched.
"""

from datetime import date

import pandas as pd

HOUR_PREFIX = "Values_Hour"


def _melt_hourly(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    hour_cols = [c for c in df.columns if c.startswith(HOUR_PREFIX)]
    long = df.melt(
        id_vars=["Values_code", "Date"], value_vars=hour_cols, var_name="hour", value_name=value_col
    )
    hour_num = long["hour"].str.removeprefix(HOUR_PREFIX).astype(int) - 1
    long["datetime"] = pd.to_datetime(long["Date"]) + pd.to_timedelta(hour_num, unit="h")
    return long.rename(columns={"Values_code": "code"})[["code", "datetime", value_col]]


def fetch_resource_crosswalk(consult) -> pd.DataFrame:
    """code <-> resource_name <-> gen_type, from XM's ListadoRecursos list metric.

    start/end are required by pydataxm's request_data even for list-type
    metrics (it computes a date range unconditionally before branching on
    entity type) but are otherwise unused -- any single date works.
    """
    today = date.today()
    raw = consult.request_data("ListadoRecursos", "Sistema", today, today)
    return raw.rename(
        columns={"Values_Code": "code", "Values_Name": "resource_name", "Values_Type": "gen_type"}
    )[["code", "resource_name", "gen_type"]]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/xm_bulk.py tests/test_xm_bulk.py
git commit -m "feat: wide-to-long reshape and resource crosswalk for pydataxm bulk fetch"
```

---

## Task 3: `ensure_dispo_declarada` and `ensure_dispo_come` (resource-keyed, crosswalk-joined)

**Files:**
- Modify: `app/data/xm_bulk.py`
- Modify: `tests/test_xm_bulk.py`

**Interfaces:**
- Consumes: `_melt_hourly`, `fetch_resource_crosswalk` (Task 2).
- Produces: `ensure_dispo_declarada(year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None) -> None`, `ensure_dispo_come(year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None) -> None`. Both are no-ops (no network, no manifest write) if their target partition already exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_xm_bulk.py`:

```python
from app.data.xm_bulk import ensure_dispo_come, ensure_dispo_declarada
from app.storage import LocalStorage


class _FakeConsultDispo:
    def __init__(self):
        self.calls = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.calls.append((coleccion, metrica, start_date, end_date))
        return pd.DataFrame(
            {
                "Values_code": ["2QEK"],
                "Values_Hour01": [100.0],
                "Values_Hour02": [110.0],
                "Date": [date(2024, 4, 18)],
            }
        )


_CROSSWALK = pd.DataFrame(
    {"code": ["2QEK"], "resource_name": ["SALTO II"], "gen_type": ["HIDRAULICA"]}
)


def test_ensure_dispo_declarada_writes_partition_with_gen_type(tmp_path):
    consult = _FakeConsultDispo()
    ensure_dispo_declarada(2024, str(tmp_path), consult, _CROSSWALK)

    assert consult.calls == [("DispoDeclarada", "Recurso", date(2024, 1, 1), date(2024, 12, 31))]
    out = pd.read_csv(tmp_path / "dispo_declarada" / "dispo_declarada_2024.csv")
    assert list(out.columns) == ["datetime", "resource_name", "dispo", "gen_type"]
    assert out.iloc[0]["resource_name"] == "SALTO II"
    assert out.iloc[0]["gen_type"] == "HIDRAULICA"
    assert out.iloc[0]["dispo"] == 100.0


def test_ensure_dispo_declarada_is_noop_when_partition_exists(tmp_path):
    storage = LocalStorage(str(tmp_path))
    with storage.open("dispo_declarada/dispo_declarada_2024.csv", "w") as f:
        f.write("datetime,resource_name,dispo,gen_type\n")

    def _boom(*a, **kw):
        raise AssertionError("should not fetch when partition already exists")

    consult = type("C", (), {"request_data": _boom})()
    ensure_dispo_declarada(2024, str(tmp_path), consult, _CROSSWALK)


def test_ensure_dispo_come_writes_partition_without_gen_type(tmp_path):
    consult = _FakeConsultDispo()
    ensure_dispo_come(2024, str(tmp_path), consult, _CROSSWALK)

    assert consult.calls == [("DispoCome", "Recurso", date(2024, 1, 1), date(2024, 12, 31))]
    out = pd.read_csv(tmp_path / "dispo_come" / "dispo_come_2024.csv")
    assert list(out.columns) == ["datetime", "resource_name", "dispo"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: FAIL with `ImportError: cannot import name 'ensure_dispo_declarada'`

- [ ] **Step 3: Implement in `app/data/xm_bulk.py`**

Add imports at the top:

```python
from app.db.queries import upsert_input_dataset
from app.storage import get_storage
```

Append:

```python
def ensure_dispo_declarada(year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"dispo_declarada/dispo_declarada_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("DispoDeclarada", "Recurso", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "dispo")
    merged = long.merge(crosswalk, on="code", how="inner")[["datetime", "resource_name", "dispo", "gen_type"]]
    with storage.open(path, "w") as f:
        merged.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_declarada",
            partition_key=str(year),
            source="pydataxm:DispoDeclarada",
            row_count=len(merged),
        )


def ensure_dispo_come(year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"dispo_come/dispo_come_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("DispoCome", "Recurso", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "dispo")
    merged = long.merge(crosswalk, on="code", how="inner")[["datetime", "resource_name", "dispo"]]
    with storage.open(path, "w") as f:
        merged.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_come",
            partition_key=str(year),
            source="pydataxm:DispoCome",
            row_count=len(merged),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/xm_bulk.py tests/test_xm_bulk.py
git commit -m "feat: fetch dispo_declarada/dispo_come partitions via pydataxm"
```

---

## Task 4: `ensure_ofertas` (daily-constant special case, no melt)

Verified live: `PrecOferDesp` returns the same value across all 24 `Values_HourNN` columns for every resource/day (0/84 rows differed in a real sample) — the existing `ofertas.csv` schema already assumes one row per resource per day, so this reads `Values_Hour01` directly instead of reusing `_melt_hourly`.

**Files:**
- Modify: `app/data/xm_bulk.py`
- Modify: `tests/test_xm_bulk.py`

**Interfaces:**
- Produces: `ensure_ofertas(year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_xm_bulk.py`:

```python
from app.data.xm_bulk import ensure_ofertas


class _FakeConsultOfertas:
    def request_data(self, coleccion, metrica, start_date, end_date):
        return pd.DataFrame(
            {
                "Values_code": ["2QEK"],
                "Values_Hour01": [89.657],
                "Values_Hour02": [89.657],
                "Date": [date(2024, 4, 18)],
            }
        )


def test_ensure_ofertas_writes_one_row_per_resource_per_day(tmp_path):
    ensure_ofertas(2024, str(tmp_path), _FakeConsultOfertas(), _CROSSWALK)
    out = pd.read_csv(tmp_path / "ofertas" / "ofertas_2024.csv")
    assert list(out.columns) == ["Date", "resource_name", "Value"]
    assert len(out) == 1
    assert out.iloc[0]["resource_name"] == "SALTO II"
    assert out.iloc[0]["Value"] == 89.657
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: FAIL with `ImportError: cannot import name 'ensure_ofertas'`

- [ ] **Step 3: Implement**

Append to `app/data/xm_bulk.py`:

```python
def ensure_ofertas(year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"ofertas/ofertas_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("PrecOferDesp", "Recurso", date(year, 1, 1), date(year, 12, 31))
    daily = raw.rename(columns={"Values_code": "code", "Values_Hour01": "Value", "Date": "Date"})
    daily = daily[["code", "Date", "Value"]]
    merged = daily.merge(crosswalk, on="code", how="inner")[["Date", "resource_name", "Value"]]
    with storage.open(path, "w") as f:
        merged.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="ofertas",
            partition_key=str(year),
            source="pydataxm:PrecOferDesp",
            row_count=len(merged),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/xm_bulk.py tests/test_xm_bulk.py
git commit -m "feat: fetch ofertas partition via pydataxm"
```

---

## Task 5: `ensure_dema_come` and `ensure_precio_bolsa` (system-level, no crosswalk)

**Files:**
- Modify: `app/data/xm_bulk.py`
- Modify: `tests/test_xm_bulk.py`

**Interfaces:**
- Produces: `ensure_dema_come(year: int, data_dir: str, consult, session=None) -> None`, `ensure_precio_bolsa(year: int, data_dir: str, consult, session=None) -> None`. Neither takes a crosswalk — `Values_code` is the constant `"Sistema"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_xm_bulk.py`:

```python
from app.data.xm_bulk import ensure_dema_come, ensure_precio_bolsa


class _FakeConsultSistema:
    def __init__(self, value):
        self.value = value

    def request_data(self, coleccion, metrica, start_date, end_date):
        return pd.DataFrame(
            {
                "Values_code": ["Sistema"],
                "Values_Hour01": [self.value],
                "Values_Hour02": [self.value],
                "Date": [date(2024, 4, 18)],
            }
        )


def test_ensure_dema_come_writes_system_series(tmp_path):
    ensure_dema_come(2024, str(tmp_path), _FakeConsultSistema(8_300_000.0))
    out = pd.read_csv(tmp_path / "demaCome" / "demaCome_2024.csv")
    assert list(out.columns) == ["datetime", "dema"]
    assert out.iloc[0]["dema"] == 8_300_000.0


def test_ensure_precio_bolsa_writes_unscaled_cop_per_kwh(tmp_path):
    ensure_precio_bolsa(2024, str(tmp_path), _FakeConsultSistema(0.2))
    out = pd.read_csv(tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv")
    assert list(out.columns) == ["datetime", "precio_bolsa"]
    assert out.iloc[0]["precio_bolsa"] == 0.2  # raw COP/kWh; load_precio_bolsa applies *1e3
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement**

Append to `app/data/xm_bulk.py`:

```python
def ensure_dema_come(year: int, data_dir: str, consult, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"demaCome/demaCome_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("DemaCome", "Sistema", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "dema")[["datetime", "dema"]]
    with storage.open(path, "w") as f:
        long.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session, dataset="demaCome", partition_key=str(year), source="pydataxm:DemaCome",
            row_count=len(long),
        )


def ensure_precio_bolsa(year: int, data_dir: str, consult, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"precio_bolsa/precio_bolsa_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("PrecBolsNaci", "Sistema", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "precio_bolsa")[["datetime", "precio_bolsa"]]
    with storage.open(path, "w") as f:
        long.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session, dataset="precio_bolsa", partition_key=str(year), source="pydataxm:PrecBolsNaci",
            row_count=len(long),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/xm_bulk.py tests/test_xm_bulk.py
git commit -m "feat: fetch demaCome/precio_bolsa partitions via pydataxm"
```

---

## Task 6: `ensure_bulk_data_for_year` orchestrator (network-lazy)

**Files:**
- Modify: `app/data/xm_bulk.py`
- Modify: `tests/test_xm_bulk.py`

**Interfaces:**
- Consumes: all `ensure_*` functions from Tasks 3-5, `fetch_resource_crosswalk` from Task 2.
- Produces: `ensure_bulk_data_for_year(year: int, data_dir: str, session=None) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_xm_bulk.py`:

```python
from app.data.xm_bulk import ensure_bulk_data_for_year


def test_ensure_bulk_data_for_year_is_noop_when_all_partitions_exist(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    for name, fname in [
        ("dispo_declarada", "dispo_declarada_2024.csv"),
        ("ofertas", "ofertas_2024.csv"),
        ("demaCome", "demaCome_2024.csv"),
        ("precio_bolsa", "precio_bolsa_2024.csv"),
        ("dispo_come", "dispo_come_2024.csv"),
    ]:
        with storage.open(f"{name}/{fname}", "w") as f:
            f.write("x\n")

    def _boom(*a, **kw):
        raise AssertionError("ReadDB must not be constructed when nothing is missing")

    monkeypatch.setattr("app.data.xm_bulk.ReadDB", _boom)
    ensure_bulk_data_for_year(2024, str(tmp_path))


def test_ensure_bulk_data_for_year_fetches_missing_partitions(tmp_path, monkeypatch):
    calls = []

    class _FakeReadDB:
        def __init__(self):
            calls.append("constructed")

        def request_data(self, coleccion, metrica, start_date, end_date):
            calls.append(coleccion)
            if coleccion == "ListadoRecursos":
                return pd.DataFrame(
                    {"Values_Code": ["2QEK"], "Values_Name": ["SALTO II"], "Values_Type": ["HIDRAULICA"]}
                )
            code = "Sistema" if metrica == "Sistema" else "2QEK"
            return pd.DataFrame(
                {
                    "Values_code": [code],
                    "Values_Hour01": [1.0],
                    "Values_Hour02": [1.0],
                    "Date": [date(2024, 4, 18)],
                }
            )

    monkeypatch.setattr("app.data.xm_bulk.ReadDB", _FakeReadDB)
    ensure_bulk_data_for_year(2024, str(tmp_path))

    assert calls[0] == "constructed"
    assert (tmp_path / "dispo_declarada" / "dispo_declarada_2024.csv").exists()
    assert (tmp_path / "ofertas" / "ofertas_2024.csv").exists()
    assert (tmp_path / "demaCome" / "demaCome_2024.csv").exists()
    assert (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").exists()
    assert (tmp_path / "dispo_come" / "dispo_come_2024.csv").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: FAIL with `ImportError: cannot import name 'ensure_bulk_data_for_year'`

- [ ] **Step 3: Implement**

Add import at the top of `app/data/xm_bulk.py`:

```python
from pydataxm.pydataxm import ReadDB
```

Append:

```python
_PARTITION_PATHS = {
    "dispo_declarada": "dispo_declarada/dispo_declarada_{year}.csv",
    "ofertas": "ofertas/ofertas_{year}.csv",
    "demaCome": "demaCome/demaCome_{year}.csv",
    "precio_bolsa": "precio_bolsa/precio_bolsa_{year}.csv",
    "dispo_come": "dispo_come/dispo_come_{year}.csv",
}
_NEEDS_CROSSWALK = {"dispo_declarada", "ofertas", "dispo_come"}


def ensure_bulk_data_for_year(year: int, data_dir: str, session=None) -> None:
    storage = get_storage(data_dir)
    missing = {
        name for name, template in _PARTITION_PATHS.items() if not storage.exists(template.format(year=year))
    }
    if not missing:
        return

    consult = ReadDB()
    crosswalk = fetch_resource_crosswalk(consult) if missing & _NEEDS_CROSSWALK else None

    if "dispo_declarada" in missing:
        ensure_dispo_declarada(year, data_dir, consult, crosswalk, session)
    if "ofertas" in missing:
        ensure_ofertas(year, data_dir, consult, crosswalk, session)
    if "demaCome" in missing:
        ensure_dema_come(year, data_dir, consult, session)
    if "precio_bolsa" in missing:
        ensure_precio_bolsa(year, data_dir, consult, session)
    if "dispo_come" in missing:
        ensure_dispo_come(year, data_dir, consult, crosswalk, session)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_xm_bulk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/data/xm_bulk.py tests/test_xm_bulk.py
git commit -m "feat: add ensure_bulk_data_for_year orchestrator"
```

---

## Task 7: Wire the orchestrator into `build_case` + fail-fast on empty ofertas

**Files:**
- Modify: `app/pipeline/case_builder.py`
- Test: `tests/test_case_builder.py` (create if it doesn't exist — check first with `find tests -iname '*case_builder*'`; if a suitable file exists, add to it instead)

**Interfaces:**
- Consumes: `ensure_bulk_data_for_year` (Task 6).

- [ ] **Step 1: Write the failing test**

If `tests/test_case_builder.py` doesn't exist, create it; otherwise append this test to whatever file already exercises `build_case` against `tests/fixtures/xm_smoke`.

```python
from datetime import date
from pathlib import Path

import pytest

from app.pipeline.case_builder import build_case
from app.schemas import DispatchCase, DispatchLevel, InputPack, InputSource

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def test_build_case_raises_clear_error_when_ofertas_empty_for_date(tmp_path, monkeypatch):
    # Reuse the real fixture layout but for a date with no ofertas rows.
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr("app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network")))
    monkeypatch.setattr("app.data.download.requests.get", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")))

    other_date = date(2024, 4, 19)  # not in the fixture's ofertas partition
    case = DispatchCase(dispatch_date=other_date, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=other_date, source=InputSource.historical, data_dir=str(tmp_path))

    with pytest.raises(ValueError, match="ofertas"):
        build_case(case, inputs)
```

(This test relies on `2024-04-19` having no `OFEI0419.txt`/etc either, so it will actually fail earlier at the mechanism-1 blob download with a network `AssertionError` before reaching the ofertas check — **adjust**: instead directly unit-test the check by calling `build_case` for `2024-04-18` against a *copy* of the fixture with `ofertas/ofertas_2024.csv` emptied down to its header row, so mechanism 1 and mechanism 2 both no-op via existing files and only the ofertas content differs.)

Rewrite the test body accordingly:

```python
def test_build_case_raises_clear_error_when_ofertas_empty_for_date(tmp_path, monkeypatch):
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    (tmp_path / "ofertas" / "ofertas_2024.csv").write_text("Date,resource_name,Value\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network"))
    )

    fecha = date(2024, 4, 18)
    case = DispatchCase(dispatch_date=fecha, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=fecha, source=InputSource.historical, data_dir=str(tmp_path))

    with pytest.raises(ValueError, match="ofertas"):
        build_case(case, inputs)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_case_builder.py -v -k ofertas_empty`
Expected: FAIL — either `build_case` succeeds with an empty `ofertas` frame (no error raised) or fails later with an unrelated `KeyError`/`IndexError` deep in the fuzzy-matching code, not a `ValueError` mentioning "ofertas".

- [ ] **Step 3: Wire the orchestrator + fail-fast check into `case_builder.py`**

Add to the imports at the top of `app/pipeline/case_builder.py`:

```python
from app.data.xm_bulk import ensure_bulk_data_for_year
```

Replace the `ensure_data_for_date(DISPATCH_DATE, data_dir=dd)` line with:

```python
    ensure_data_for_date(DISPATCH_DATE, data_dir=dd)
    ensure_bulk_data_for_year(DISPATCH_DATE.year, data_dir=dd)
```

Replace:

```python
    oferta_full = ofertas.copy()
    ofertas = ofertas[ofertas.Date.dt.date == DISPATCH_DATE]
```

with:

```python
    oferta_full = ofertas.copy()
    ofertas = ofertas[ofertas.Date.dt.date == DISPATCH_DATE]
    if ofertas.empty:
        raise ValueError(
            f"no hay ofertas (PrecOferDesp) publicadas por XM para {DISPATCH_DATE}. "
            "XM publica PrecOferDesp por mes calendario completo, un mes despues "
            "(agosto completo solo esta disponible desde el 1 de septiembre) -- "
            "intente con una fecha de un mes ya cerrado, o ver GH issue "
            "'heuristica de precios de oferta para fechas recientes' para el "
            "enfoque planeado a futuro."
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_case_builder.py -v -k ofertas_empty`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass, including the existing `tests/test_xm_smoke_loaders.py` and any prior `build_case`-against-fixture smoke test — the fixture's `dispo_declarada/`, `ofertas/`, `demaCome/`, `precio_bolsa/` partitions all already exist so `ensure_bulk_data_for_year` is a pure no-op there (no network).

- [ ] **Step 6: Commit**

```bash
git add app/pipeline/case_builder.py tests/test_case_builder.py
git commit -m "feat: wire pydataxm bulk fetch into build_case, fail fast on empty ofertas"
```

---

## Task 8: `dAGCUNIDAD` fetch (mecanismo 1 extension) + `app/data/agc.py` parse/aggregate

Real per-unit AGC blob format, fetched live: `"UNIT NAME",v1,v2,...,v24` (24 comma-separated hourly values, no header row). Unit names are plant name + trailing unit number (e.g. `"CHIVOR 2"`, `"CHIVOR 3"`, `"CHIVOR 4"` all belong to plant `CHIVOR`). Verified live: stripping the trailing `" <digits>"` and matching against `fetch_resource_crosswalk`'s `resource_name` column resolves cleanly for real plants (`CHIVOR`, `CALIMA`) using the same `thefuzz` pattern `case_builder.py` already uses for OFEI name resolution; unmatched units (e.g. non-centrally-dispatched minor plants) are skipped with a warning, not an error — same pattern as the existing `dispo_come` "no existe el generador... se asignara en 0" handling in `case_builder.py`.

**Files:**
- Modify: `app/data/download.py` (add `dAGCUNIDAD` to `PARAMS`)
- Create: `app/data/agc.py`
- Modify: `app/data/loaders.py` (`load_agc` signature)
- Modify: `app/pipeline/case_builder.py` (call site + ordering)
- Test: `tests/test_agc.py`
- Modify: `tests/test_loaders.py`, `tests/test_xm_smoke_loaders.py`

**Interfaces:**
- Produces: `parse_dagcunidad(raw_text: str) -> pd.DataFrame` with columns `["unit_name", "hour", "agc_mw"]` (long format, `hour` is 0-23).
- Produces: `ensure_agc_asignado(dispatch_date: date, data_dir: str, resource_names: list[str], session=None) -> None` — writes `data/{dispatch_date}/agc_asignado.csv` with columns `["datetime", "recurso", "agc"]`, `agc` in kW (raw MW `* 1000`) to match `case_builder.py`'s existing `* 1e-3`.
- Produces: `load_agc(data_dir: str, dispatch_date: date) -> pd.DataFrame` (replaces the old flat-file signature).

- [ ] **Step 1: Add `dAGCUNIDAD` to `download.py`'s `PARAMS`**

In `app/data/download.py`, add to the `PARAMS` dict:

```python
    "dAGCUNIDAD": {
        "initial_path": "M:/InformacionAgentes/Usuarios/Publico/DESPACHO",
    },
```

This is a plain dict entry alongside the existing 5 — `save_file`'s `complement = "_NAL" if file_type in {"PrId", "iMAR"} else ""` branch already leaves `dAGCUNIDAD` with no suffix, matching the real filename `dAGCUNIDAD0804.txt` confirmed live. No other change needed in this file; `ensure_data_for_date`'s existing loop over `PARAMS` now downloads it automatically whenever the date folder is empty.

- [ ] **Step 2: Write the failing tests for `app/data/agc.py`**

Create `tests/test_agc.py`:

```python
from datetime import date

import pandas as pd

from app.data.agc import parse_dagcunidad

RAW = (
    '"CHIVOR 2",52.5000, 50.5000\n'
    '"CHIVOR 3",10.0000, 8.6667\n'
    '"CALIMA 1",0.0000, 8.5000\n'
)


def test_parse_dagcunidad_long_format():
    out = parse_dagcunidad(RAW)
    assert list(out.columns) == ["unit_name", "hour", "agc_mw"]
    assert len(out) == 6  # 3 units x 2 hours
    row = out[(out["unit_name"] == "CHIVOR 2") & (out["hour"] == 0)]
    assert row["agc_mw"].iloc[0] == 52.5
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_agc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.data.agc'`

- [ ] **Step 4: Implement `parse_dagcunidad`**

Create `app/data/agc.py`:

```python
"""Parse + aggregate the per-unit AGC blob (dAGCUNIDAD, mecanismo 1) down to
the per-resource shape case_builder.py expects (agc_asignado.csv).

Raw format, one line per unit, no header:
    "UNIT NAME",v1,v2,...,v24

Unit -> resource aggregation strips the trailing " <digits>" (e.g.
"CHIVOR 2" -> "CHIVOR") and fuzzy-matches against the run's known resource
names, same pattern case_builder.py already uses for OFEI name resolution.
Values are MW in the raw blob; case_builder.py's existing *1e-3 assumes kW
(same convention as dispo/demand), so this module converts *1000 on write --
see plan Global Constraints.
"""

import csv
import io
import re
from datetime import date

import pandas as pd
from thefuzz import fuzz, process

from app.db.queries import upsert_input_dataset
from app.storage import get_storage

_UNIT_SUFFIX = re.compile(r"\s+\d+$")


def parse_dagcunidad(raw_text: str) -> pd.DataFrame:
    rows = []
    for line in csv.reader(io.StringIO(raw_text)):
        if not line:
            continue
        unit_name = line[0]
        for hour, value in enumerate(line[1:25]):
            rows.append({"unit_name": unit_name, "hour": hour, "agc_mw": float(value)})
    return pd.DataFrame(rows, columns=["unit_name", "hour", "agc_mw"])


def _resource_name_for_unit(unit_name: str, resource_names: list[str]) -> str | None:
    candidate = _UNIT_SUFFIX.sub("", unit_name).strip()
    match = process.extractOne(
        query=candidate.lower(),
        choices=resource_names,
        scorer=fuzz.token_sort_ratio,
        processor=lambda x: x.lower().replace(" ", ""),
        score_cutoff=70,
    )
    return match[0] if match else None


def ensure_agc_asignado(
    dispatch_date: date, data_dir: str, resource_names: list[str], session=None
) -> None:
    storage = get_storage(data_dir)
    out_path = f"{dispatch_date}/agc_asignado.csv"
    if storage.exists(out_path):
        return

    filename = f"dAGCUNIDAD{dispatch_date.month:0>2}{dispatch_date.day:0>2}.txt"
    with storage.open(f"{dispatch_date}/{filename}", "r") as f:
        raw_text = f.read()

    long = parse_dagcunidad(raw_text)
    long["recurso"] = long["unit_name"].apply(lambda u: _resource_name_for_unit(u, resource_names))
    unmatched = long[long["recurso"].isnull()]["unit_name"].unique()
    for name in unmatched:
        print(f"...AGC: no se pudo mapear la unidad '{name}' a ningun recurso. Se ignora.")
    long = long.dropna(subset=["recurso"])

    agg = long.groupby(["recurso", "hour"], as_index=False)["agc_mw"].sum()
    agg["datetime"] = pd.to_datetime(dispatch_date) + pd.to_timedelta(agg["hour"], unit="h")
    agg["agc"] = agg["agc_mw"] * 1000  # MW -> kW, matches case_builder.py's *1e-3
    out = agg[["datetime", "recurso", "agc"]]

    with storage.open(out_path, "w") as f:
        out.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session, dataset="agc_asignado", partition_key=str(dispatch_date),
            source="xm_blob:dAGCUNIDAD", row_count=len(out),
        )
```

- [ ] **Step 5: Run to verify `parse_dagcunidad` test passes**

Run: `uv run pytest tests/test_agc.py -v`
Expected: PASS

- [ ] **Step 6: Write the failing test for `ensure_agc_asignado`**

Append to `tests/test_agc.py`:

```python
from app.data.agc import ensure_agc_asignado
from app.storage import LocalStorage


def test_ensure_agc_asignado_aggregates_units_to_resources(tmp_path):
    storage = LocalStorage(str(tmp_path))
    fecha = date(2024, 4, 18)
    raw = '"CHIVOR 2",52.5000, 50.5000\n"CHIVOR 3",10.0000, 8.6667\n"ALTO ANCHICAYA 1",0.0,0.0\n'
    with storage.open(f"{fecha}/dAGCUNIDAD0418.txt", "w") as f:
        f.write(raw)

    ensure_agc_asignado(fecha, str(tmp_path), resource_names=["CHIVOR"])

    out = pd.read_csv(tmp_path / str(fecha) / "agc_asignado.csv", parse_dates=["datetime"])
    assert list(out.columns) == ["datetime", "recurso", "agc"]
    assert set(out["recurso"]) == {"CHIVOR"}
    hour0 = out[out["datetime"] == pd.Timestamp("2024-04-18 00:00")]
    assert hour0["agc"].iloc[0] == (52.5 + 10.0) * 1000  # CHIVOR 2 + CHIVOR 3, MW->kW


def test_ensure_agc_asignado_is_noop_when_file_exists(tmp_path):
    storage = LocalStorage(str(tmp_path))
    fecha = date(2024, 4, 18)
    with storage.open(f"{fecha}/agc_asignado.csv", "w") as f:
        f.write("datetime,recurso,agc\n")

    def _boom(*a, **kw):
        raise AssertionError("should not read dAGCUNIDAD when agc_asignado.csv already exists")

    monkeypatch_target = storage.open
    ensure_agc_asignado(fecha, str(tmp_path), resource_names=["CHIVOR"])
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/test_agc.py -v`
Expected: PASS

- [ ] **Step 8: Update `load_agc` in `app/data/loaders.py`**

Replace:

```python
def load_agc(data_dir: str = "data") -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open("agc_asignado.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])
```

with:

```python
def load_agc(data_dir: str, dispatch_date) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"{dispatch_date}/agc_asignado.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])
```

- [ ] **Step 9: Reorder `build_case` in `app/pipeline/case_builder.py`**

`agc_asignado` currently loads too early (before `dispo` is filtered, so `resource_names` isn't available yet). Move the load down.

Replace:

```python
    year = DISPATCH_DATE.year
    if case.level == DispatchLevel.ideal:
        dispo_come = loaders.load_dispo_come(dd, year)
    dispo = loaders.load_dispo(dd, year)
    ofertas = loaders.load_ofertas(dd, year)
    demanda = loaders.load_demanda(dd, year)
    agc_asignado = loaders.load_agc(dd)
    parametros_plantas = loaders.load_parametros_plantas(dd)
    precio_bolsa = loaders.load_precio_bolsa(dd, year)
```

with:

```python
    year = DISPATCH_DATE.year
    if case.level == DispatchLevel.ideal:
        dispo_come = loaders.load_dispo_come(dd, year)
    dispo = loaders.load_dispo(dd, year)
    ofertas = loaders.load_ofertas(dd, year)
    demanda = loaders.load_demanda(dd, year)
    parametros_plantas = loaders.load_parametros_plantas(dd)
    precio_bolsa = loaders.load_precio_bolsa(dd, year)
```

Then, immediately after the existing dispo date-filter line:

```python
    dispo = dispo[(dispo.datetime.dt.date == DISPATCH_DATE) & (dispo["resource_name"].notnull())]
    dispo = dispo.drop_duplicates(subset=["resource_name", "datetime"])
```

insert:

```python
    ensure_agc_asignado(DISPATCH_DATE, dd, resource_names=list(dispo["resource_name"].unique()))
    agc_asignado = loaders.load_agc(dd, DISPATCH_DATE)
```

Add the import at the top of `case_builder.py`:

```python
from app.data.agc import ensure_agc_asignado
```

The existing later line `agc_asignado = agc_asignado[agc_asignado["datetime"].dt.date == DISPATCH_DATE]` stays — it's now a no-op filter (defensive, matches the pattern every other loaded frame follows) since `load_agc` already returns only this date's rows.

- [ ] **Step 10: Update `tests/test_xm_smoke_loaders.py`'s `load_agc` call and fixture**

The fixture's `agc_asignado.csv` currently lives at the flat root (`tests/fixtures/xm_smoke/agc_asignado.csv`) with only one row. Move it under the date folder and give it 24 hourly rows matching the fixture's other per-hour data, then update `generate_fixture.py`.

In `tests/fixtures/xm_smoke/generate_fixture.py`, replace:

```python
with open(BASE / "agc_asignado.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "recurso", "agc"])
    w.writerow([HOURS[0].isoformat(sep=" "), "TERMO1", 0])
```

with:

```python
agc_dir = BASE / str(FECHA)
agc_dir.mkdir(exist_ok=True)
with open(agc_dir / "agc_asignado.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "recurso", "agc"])
    for h in HOURS:
        w.writerow([h.isoformat(sep=" "), "TERMO1", 0])
```

(`agc_dir` mkdir is `exist_ok=True` since `flat_dir = BASE / str(FECHA)` already creates this same directory later in the script for the OFEI/PrId files — check the script's existing `flat_dir.mkdir(exist_ok=True)` line and either reuse `flat_dir` directly instead of a new `agc_dir` variable, or keep both since they resolve to the same path either way.)

Remove the old fixture file and regenerate:

```bash
rm tests/fixtures/xm_smoke/agc_asignado.csv
uv run python tests/fixtures/xm_smoke/generate_fixture.py
```

In `tests/test_xm_smoke_loaders.py`, replace:

```python
    agc = loaders.load_agc(DD)
    assert "agc" in agc.columns
```

with:

```python
    agc = loaders.load_agc(DD, FECHA)
    assert "agc" in agc.columns
```

- [ ] **Step 11: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 12: Commit**

```bash
git add app/data/download.py app/data/agc.py app/data/loaders.py app/pipeline/case_builder.py \
  tests/test_agc.py tests/test_loaders.py tests/test_xm_smoke_loaders.py tests/fixtures/xm_smoke/
git commit -m "feat: fetch and aggregate dAGCUNIDAD per-unit AGC into agc_asignado.csv"
```

---

## Task 9: Document the operational gaps in `README.md`

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Find the section documenting required `data/` inputs**

Run: `grep -n "dispo_declarada\|parametros_plantas\|data/ es git-ignored\|datos requeridos" README.md`

- [ ] **Step 2: Add a short note next to the existing input-data documentation**

Add (adapt wording/placement to whatever section the grep above surfaces — this repo's README already has a "datos requeridos" section per `AGENTS.md`'s own routing table):

```markdown
`dispo_declarada.csv`, `ofertas.csv`, `demaCome.csv`, `precio_bolsa/*.csv` y
`DispoCome_resource.csv` se descargan automaticamente (via `pydataxm`,
particionados por año en `data/{dataset}/{dataset}_{year}.csv`) la primera
vez que se corre una fecha de ese año — no requieren descarga manual.
`PrecOferDesp` (ofertas) se publica por mes calendario completo, un mes
despues (agosto completo solo esta disponible desde el 1 de septiembre):
correr una fecha del mes en curso falla con un `ValueError` explicito, no es
un bug. Ver GH issue "heuristica de precios de oferta para fechas recientes"
para el plan a futuro de estimar precios antes de esa publicacion.

`parametros_plantas.csv` sigue siendo mantenido a mano — no hay mecanismo de
descarga (la fuente real, Paratec, requiere una decision de modelado sobre
como reducir sus parametros por-unidad/por-configuracion a los escalares
planos que el modelo usa hoy; ver `docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md`
seccion 7).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document pydataxm auto-fetch and remaining parametros_plantas.csv gap"
```

---

## Task 10: End-to-end manual verification against the real XM API

Not a TDD task — a manual checkpoint before calling this plan done, since every automated test in this plan monkeypatches `pydataxm`/`requests` by design (per Global Constraints, "never hit the real network in the test suite").

- [ ] **Step 1: Run a real historical date end to end**

```bash
rm -rf /tmp/gridforge-e2e-test
uv run python -m app run 2026-07-15 -t preideal --data-dir /tmp/gridforge-e2e-test
```

Expected: downloads mecanismo-1 blobs, fetches all 5 pydataxm partitions + AGC, no `FileNotFoundError`, ends with a solved case or a clear, unrelated failure (e.g. missing `parametros_plantas.csv` — copy one from `tests/fixtures/xm_smoke/parametros_plantas.csv` with real `resource_name`s substituted, or from a prior real `data/` snapshot, since this file is explicitly out of scope per Global Constraints).

- [ ] **Step 2: Confirm the year-partition cache is reused, not re-fetched**

Run the same command again for a nearby date in the same year (e.g. `2026-07-16`):

```bash
uv run python -m app run 2026-07-16 -t preideal --data-dir /tmp/gridforge-e2e-test
```

Expected: no `pydataxm` network calls for the 5 bulk datasets this time (only the per-date mecanismo-1 blobs + AGC re-download, since those are still date-keyed) — confirm by checking there's no multi-second pause/network activity for the bulk fetch step, or temporarily add a print statement in `ensure_bulk_data_for_year` and remove it after.

- [ ] **Step 3: Confirm the fail-fast message on a too-recent date**

```bash
uv run python -m app run "$(date +%Y-%m-%d)" -t preideal --data-dir /tmp/gridforge-e2e-test
```

Expected: fails with the `ValueError` from Task 7 ("no hay ofertas... XM publica PrecOferDesp por mes calendario completo, un mes despues..."), not a stack trace pointing at `loaders.py` or a fuzzy-matching `KeyError`.

- [ ] **Step 4: Report findings**

If any step's actual behavior differs from "Expected," do not silently patch around it — this is exactly the kind of live-API-shape assumption this plan's research already got wrong once (`MaxDays`/chunking) and right once (crosswalk) before verifying. Stop and re-verify against the real API rather than adjusting code to make a symptom go away.
