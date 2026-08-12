# Heuristica de precios de oferta (issue #30) — plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el `raise ValueError` en `case_builder.py` cuando `ofertas.csv`
(`PrecOferDesp`) no tiene datos publicados para la fecha, por una heuristica que
estima el precio de oferta usando generacion despachada (`PrId`) + disponibilidad
(`DispoDeclarada`) + costo marginal nacional por hora (`iMAR`), todos frescos hasta
hoy, a diferencia de `PrecOferDesp`.

**Architecture:** Paquete nuevo `app/data/heuristic/biddings.py`: parsers puros para
`PrId`/`iMAR`, un algoritmo de eliminacion (hora con un unico candidato "a media
maquina" resuelve ese recurso y lo saca de competencia en las demas horas), ensamblado
de la fila `ofertas` estimada (con fallback a ultimo precio publicado), y una funcion
de orquestacion que hace fuzzy-matching de nombres + cachea el resultado via
`app.storage`. Un unico call site nuevo en `case_builder.py`.

**Tech Stack:** Python 3.12, pandas, `thefuzz` (ya dependencia), `app.storage`
(`Storage`/`LocalStorage`), pytest, `uv run`.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-11-ofertas-heuristica-precios-design.md`
  — cualquier duda de comportamiento remitase ahi primero.
- `iMAR` NO lleva sufijo `_NAL` en el nombre de archivo real de XM; `PrId` SI. No
  cambiar esto ultimo (`tests/test_paths.py::test_prid_nal_suffix` ya lo cubre).
- `iMAR` trae MPO en **COP/MWh**; `ofertas.csv`'s columna `Value` sigue la convencion
  COP/kWh cruda (igual que `PrecOferDesp`). Toda escritura a `Value` debe dividir el
  MPO por `1e3`. No te saltes esta conversion — es el mismo tipo de bug de escala que
  ya paso una vez en este repo (revenue BESS inflado 1000x, Fase 1).
- No usar `open()` plano para el archivo de cache `ofertas_estimado_{year}.csv` —
  pasa por `app.storage.get_storage`. Los archivos de entrada por-fecha (`PrId`,
  `iMAR`, via `resolve_input`) SI usan `open()` plano, igual que `parse_ofei` y los
  dos bloques de `case_builder.py` para `dCondIniP`/`dCondIniU` (patron ya existente
  en el repo, no se cambia aqui).
- Pydantic v2 no aplica en este plan (no se tocan schemas).
- `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` deben
  pasar antes de cada commit relevante. `uv run ty check app/ || true` es informativo,
  nunca bloqueante.
- Fuera de alcance de este plan (ver spec): caso especial de precio-por-configuracion
  en plantas CC ([#36](https://github.com/jccamargo94/gridforge/issues/36)), ciclo de
  calibracion contra dispatch real (bloqueado por
  [#34](https://github.com/jccamargo94/gridforge/issues/34)), heuristica
  estacional/historica para recursos sin resolver.

---

### Task 1: Fix del bug `_NAL` en `iMAR` (bloqueante para todo lo demas)

**Files:**
- Modify: `app/data/download.py:35-37` (`_blob_filename`)
- Modify: `app/data/paths.py:29-31` (`_filename`)
- Modify: `tests/test_download.py:42`
- Test: `tests/test_paths.py` (agregar caso nuevo)
- Modify: `tests/fixtures/xm_smoke/generate_fixture.py:117-120`
- Rename + rewrite content: `tests/fixtures/xm_smoke/2024-04-18/iMAR0418_NAL.txt` ->
  `tests/fixtures/xm_smoke/2024-04-18/iMAR0418.txt`

**Interfaces:**
- Produces: `_filename("iMAR", date) -> "iMAR{MMDD}.txt"` (sin sufijo),
  `_filename("PrId", date) -> "PrId{MMDD}_NAL.txt"` (sin cambios) — usado por
  Task 4/5 via `resolve_input`.

- [ ] **Step 1: Escribir el test que falla — `iMAR` no debe llevar `_NAL`**

En `tests/test_paths.py`, agregar al final:

```python
def test_imar_has_no_nal_suffix(tmp_path):
    d = date(2024, 4, 18)
    live = tmp_path / "2024-04-18"
    live.mkdir()
    (live / "iMAR0418.txt").write_text("x")
    assert resolve_input("iMAR", d, str(tmp_path)).endswith("iMAR0418.txt")
    assert not resolve_input("iMAR", d, str(tmp_path)).endswith("_NAL.txt")
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_paths.py::test_imar_has_no_nal_suffix -v`
Expected: FAIL — `resolve_input` busca `iMAR0418_NAL.txt`, no encuentra `iMAR0418.txt`,
lanza `FileNotFoundError`.

- [ ] **Step 3: Arreglar `app/data/paths.py`**

En `_filename` (linea ~30):

```python
def _filename(kind: str, dispatch_date: date) -> str:
    mmdd = f"{dispatch_date.month:0>2}{dispatch_date.day:0>2}"
    complement = "_NAL" if kind == "PrId" else ""
    return f"{kind}{mmdd}{complement}.txt"
```

- [ ] **Step 4: Arreglar `app/data/download.py`**

En `_blob_filename` (linea ~35):

```python
def _blob_filename(file_type: str, file_date: date) -> str:
    """Compute the blob filename without extension (e.g., 'OFEI0418' or 'PrId0418_NAL')."""
    complement = "_NAL" if file_type == "PrId" else ""
    return f"{file_type}{file_date.month:0>2}{file_date.day:0>2}{complement}"
```

- [ ] **Step 5: Correr el test de paths y verificar que pasa**

Run: `uv run pytest tests/test_paths.py -v`
Expected: PASS (todos, incluyendo `test_prid_nal_suffix` que sigue verificando que
`PrId` SI lleva `_NAL`).

- [ ] **Step 6: Actualizar `tests/test_download.py`**

Linea 42, cambiar:

```python
    (tmp_path / "2024-04-18" / "iMAR0418_NAL.txt").write_text("existing")
```

por:

```python
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text("existing")
```

- [ ] **Step 7: Renombrar y corregir el contenido del fixture `iMAR` de xm_smoke**

El contenido actual del fixture (`f"{g['name']},0,0,...`) nunca fue el formato real
de XM — era un placeholder nunca validado (iMAR jamas se parseaba con exito). El
formato real (verificado en vivo 2026-08-11) es 3 filas: `"Costo Marginal"`,
`"Delta"`, `"MPO"`, 24 valores cada una.

```bash
git mv tests/fixtures/xm_smoke/2024-04-18/iMAR0418_NAL.txt \
       tests/fixtures/xm_smoke/2024-04-18/iMAR0418.txt
```

Reemplazar el contenido de `tests/fixtures/xm_smoke/2024-04-18/iMAR0418.txt` por:

```
"Costo Marginal",150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00
"Delta",0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00
"MPO",150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00, 150000.00
```

- [ ] **Step 8: Actualizar `generate_fixture.py` para que siga siendo reproducible**

En `tests/fixtures/xm_smoke/generate_fixture.py`, reemplazar lineas 117-120:

```python
imar_lines = []
for g in GENERATORS:
    imar_lines.append(f"{g['name']},0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
(flat_dir / f"iMAR{MMDD}_NAL.txt").write_text("\n".join(imar_lines) + "\n")
```

por:

```python
mpo_row = ",".join(["150000.00"] * 24)
delta_row = ",".join(["0.00"] * 24)
imar_lines = [f'"Costo Marginal",{mpo_row}', f'"Delta",{delta_row}', f'"MPO",{mpo_row}']
(flat_dir / f"iMAR{MMDD}.txt").write_text("\n".join(imar_lines) + "\n")
```

- [ ] **Step 9: Correr toda la suite y verificar que nada mas se rompio**

Run: `uv run pytest -q`
Expected: PASS (todos los tests, incluyendo `tests/test_xm_smoke_*.py` que dependen
del fixture renombrado — `ensure_data_for_date`/`resolve_input` ya no buscan
`_NAL` para iMAR, asi que el archivo renombrado se sigue encontrando).

- [ ] **Step 10: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add app/data/download.py app/data/paths.py tests/test_download.py \
        tests/test_paths.py tests/fixtures/xm_smoke/generate_fixture.py
git add -A tests/fixtures/xm_smoke/2024-04-18/iMAR0418.txt \
           tests/fixtures/xm_smoke/2024-04-18/iMAR0418_NAL.txt
git commit -m "fix: iMAR blob filename has no _NAL suffix, only PrId does

Verified live against XM's real blob storage: iMAR{MMDD}.txt has no
suffix. The _NAL suffix on both made iMAR always 404, so it was never
successfully downloaded for any 2026 date."
```

---

### Task 2: Parsers puros + algoritmo de deteccion de marginal

**Files:**
- Create: `app/data/heuristic/__init__.py`
- Create: `app/data/heuristic/biddings.py`
- Test: `tests/test_ofertas_heuristic.py`

**Interfaces:**
- Produces:
  - `parse_predespacho(raw_text: str) -> dict[str, list[float]]` — nombre crudo del
    recurso -> 24 floats (generacion despachada, MW).
  - `parse_mpo(raw_text: str) -> list[float]` — 24 floats (MPO nacional, COP/MWh).
  - `detect_marginal_resources(predespacho: dict[str, list[float]], dispo_declarada: dict[str, list[float]]) -> dict[str, int]`
    — recurso (ya en el namespace de `dispo_declarada`) -> indice de hora (0-23)
    resuelta como marginal.

- [ ] **Step 1: Crear el paquete vacio**

```bash
mkdir -p app/data/heuristic
touch app/data/heuristic/__init__.py
```

- [ ] **Step 2: Escribir los tests que fallan**

Crear `tests/test_ofertas_heuristic.py`:

```python
from app.data.heuristic.biddings import (
    detect_marginal_resources,
    parse_mpo,
    parse_predespacho,
)


def test_parse_predespacho_reads_resource_and_24_hours():
    raw = "TERMO1,10,20,30," + ",".join(["40"] * 21) + "\nTERMO2,5,5,5," + ",".join(["5"] * 21)
    result = parse_predespacho(raw)
    assert result["TERMO1"] == [10.0, 20.0, 30.0] + [40.0] * 21
    assert result["TERMO2"] == [5.0] * 24


def test_parse_predespacho_skips_short_lines():
    raw = "TERMO1,10,20\nTERMO2," + ",".join(["5"] * 24)
    result = parse_predespacho(raw)
    assert "TERMO1" not in result
    assert result["TERMO2"] == [5.0] * 24


def test_parse_mpo_reads_mpo_row():
    raw = (
        '"Costo Marginal",' + ",".join(["990.0"] * 24) + "\n"
        '"Delta",' + ",".join(["0.0"] * 24) + "\n"
        '"MPO",' + ",".join([str(991000.0 + h) for h in range(24)])
    )
    result = parse_mpo(raw)
    assert result[0] == 991000.0
    assert result[23] == 991023.0


def test_parse_mpo_raises_when_no_mpo_row():
    raw = '"Costo Marginal",' + ",".join(["990.0"] * 24)
    try:
        parse_mpo(raw)
        assert False, "esperaba ValueError"
    except ValueError as e:
        assert "MPO" in str(e)


def test_detect_marginal_resolves_unique_candidate_hour():
    # TERMO1 a media maquina solo en la hora 5; nadie mas es candidato ahi.
    predespacho = {
        "TERMO1": [0.0] * 5 + [150.0] + [300.0] * 18,  # 150 < 300 (dispo) solo hora 5
        "TERMO2": [200.0] * 24,  # siempre al tope de su dispo (200) -> nunca candidato
    }
    dispo_declarada = {
        "TERMO1": [300.0] * 24,
        "TERMO2": [200.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {"TERMO1": 5}


def test_detect_marginal_ambiguous_hour_resolves_nothing_for_that_hour():
    # TERMO1 y TERMO2 candidatos ambos en la hora 3, ninguno en otra hora.
    predespacho = {
        "TERMO1": [300.0] * 3 + [150.0] + [300.0] * 20,
        "TERMO2": [200.0] * 3 + [100.0] + [200.0] * 20,
    }
    dispo_declarada = {
        "TERMO1": [300.0] * 24,
        "TERMO2": [200.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {}


def test_detect_marginal_elimination_unlocks_second_hour():
    # TERMO1 es candidato unico en hora 1 (se resuelve ahi). TERMO1 y TERMO2
    # tambien son candidatos ambos en hora 2 -- pero una vez TERMO1 se
    # resuelve por hora 1, se elimina de hora 2, dejando a TERMO2 como unico
    # candidato de hora 2, que tambien se resuelve.
    predespacho = {
        "TERMO1": [300.0, 150.0, 150.0] + [300.0] * 21,
        "TERMO2": [200.0, 200.0, 100.0] + [200.0] * 21,
    }
    dispo_declarada = {
        "TERMO1": [300.0] * 24,
        "TERMO2": [200.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {"TERMO1": 1, "TERMO2": 2}
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_ofertas_heuristic.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.data.heuristic.biddings'`

- [ ] **Step 4: Implementar `app/data/heuristic/biddings.py`**

```python
"""Estima ofertas.csv para fechas donde PrecOferDesp aun no publica.

PrId (generacion despachada por recurso/hora) y iMAR (costo marginal/MPO
nacional por hora) estan frescos hasta hoy, a diferencia de PrecOferDesp
(un mes de rezago). Este modulo cruza ambos para detectar que recurso
esta "a media maquina" (candidato a marginar) cada hora, y le asigna el
MPO de la hora en que se resuelve como su precio de oferta -- ver
docs/superpowers/specs/2026-08-11-ofertas-heuristica-precios-design.md.
"""

import csv
import io
from datetime import date

_HOURS = range(24)


def parse_predespacho(raw_text: str) -> dict[str, list[float]]:
    """PrId: una fila por recurso, sin encabezado, `nombre,v0,v1,...,v23`."""
    out: dict[str, list[float]] = {}
    for line in csv.reader(io.StringIO(raw_text)):
        if len(line) < 25:
            continue
        out[line[0].strip()] = [float(v) for v in line[1:25]]
    return out


def parse_mpo(raw_text: str) -> list[float]:
    """iMAR: filas 'Costo Marginal'/'Delta'/'MPO', 24 valores cada una (COP/MWh)."""
    for line in csv.reader(io.StringIO(raw_text)):
        if line and line[0].strip().strip('"') == "MPO":
            return [float(v) for v in line[1:25]]
    raise ValueError("no se encontro la fila 'MPO' en el archivo iMAR")


def detect_marginal_resources(
    predespacho: dict[str, list[float]],
    dispo_declarada: dict[str, list[float]],
) -> dict[str, int]:
    """Devuelve {recurso: hora} para los recursos resueltos por eliminacion.

    Candidato a marginar en la hora h: 0 < despachado[h] < disponible[h]
    ("a media maquina"). Una hora con un unico candidato restante resuelve
    ese recurso -- su precio real es el MPO de esa hora -- y lo elimina
    como candidato de todas las demas horas (solo puede tener un precio,
    porque su oferta es plana durante el dia). Recursos que nunca quedan
    como unico candidato de ninguna hora no se resuelven aqui.

    `despachado`/`disponible` deben venir en la misma unidad (MW) -- ver nota
    de unidades en `ensure_ofertas_estimado`. Si un recurso es candidato unico
    en mas de una hora simultaneamente, se resuelve con la primera en orden de
    hora (0->23); es una eleccion arbitraria pero determinista, no un bug.
    """
    candidates: dict[int, set[str]] = {h: set() for h in _HOURS}
    for resource, despacho in predespacho.items():
        disponible = dispo_declarada.get(resource)
        if disponible is None:
            continue
        for h in _HOURS:
            if 0 < despacho[h] < disponible[h]:
                candidates[h].add(resource)

    resolved: dict[str, int] = {}
    changed = True
    while changed:
        changed = False
        for h, resources in candidates.items():
            if len(resources) == 1:
                (resource,) = resources
                if resource not in resolved:
                    resolved[resource] = h
                    changed = True
                for other_resources in candidates.values():
                    other_resources.discard(resource)
    return resolved
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_ofertas_heuristic.py -v`
Expected: PASS (7/7)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add app/data/heuristic/__init__.py app/data/heuristic/biddings.py \
        tests/test_ofertas_heuristic.py
git commit -m "feat: parse PrId/iMAR and detect marginal resource per hour

Elimination algorithm: an hour with exactly one 'partially loaded'
candidate resolves that resource's price (=MPO of that hour) and removes
it from every other hour's candidate set, since a flat daily offer can
only have one true price."
```

---

### Task 3: `estimate_ofertas` — ensamblado, unidades, fallback

**Files:**
- Modify: `app/data/heuristic/biddings.py`
- Test: `tests/test_ofertas_heuristic.py`

**Interfaces:**
- Consumes: `detect_marginal_resources` de Task 2 (misma firma).
- Produces: `estimate_ofertas(dispatch_date: date, predespacho: dict[str, list[float]], dispo_declarada: dict[str, list[float]], mpo_by_hour: list[float], ultimo_precio: dict[str, float]) -> pd.DataFrame`
  con columnas `["Date", "resource_name", "Value", "is_estimated"]` — usado por
  Task 4.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_ofertas_heuristic.py`:

```python
from datetime import date as _date

import pandas as pd

from app.data.heuristic.biddings import estimate_ofertas


def test_estimate_ofertas_resolved_resource_uses_mpo_over_1e3():
    predespacho = {"TERMO1": [0.0] * 5 + [150.0] + [300.0] * 18, "TERMO2": [200.0] * 24}
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    mpo_by_hour = [1000.0] * 5 + [990000.0] + [1000.0] * 18
    ultimo_precio = {"TERMO1": 100.0, "TERMO2": 180.0}

    result = estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, ultimo_precio
    )

    row = result[result["resource_name"] == "TERMO1"].iloc[0]
    assert row["Value"] == 990.0  # 990000 / 1e3
    assert bool(row["is_estimated"]) is True
    assert row["Date"] == pd.Timestamp(_date(2026, 8, 11))


def test_estimate_ofertas_unresolved_resource_falls_back_to_ultimo_precio():
    predespacho = {"TERMO1": [200.0] * 24}  # nunca a media maquina (== dispo todo el dia)
    dispo_declarada = {"TERMO1": [200.0] * 24}
    mpo_by_hour = [990000.0] * 24
    ultimo_precio = {"TERMO1": 150.0, "TERMO2": 180.0}  # TERMO2 ni siquiera esta en predespacho

    result = estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, ultimo_precio
    )

    values = result.set_index("resource_name")["Value"].to_dict()
    assert values == {"TERMO1": 150.0, "TERMO2": 180.0}
    assert result["is_estimated"].all()


def test_estimate_ofertas_empty_ultimo_precio_returns_empty_frame():
    result = estimate_ofertas(_date(2026, 8, 11), {}, {}, [0.0] * 24, {})
    assert result.empty
    assert list(result.columns) == ["Date", "resource_name", "Value", "is_estimated"]
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_ofertas_heuristic.py -v`
Expected: FAIL con `ImportError: cannot import name 'estimate_ofertas'`

- [ ] **Step 3: Implementar `estimate_ofertas`**

Agregar a `app/data/heuristic/biddings.py` (despues de `detect_marginal_resources`):

```python
import pandas as pd


def estimate_ofertas(
    dispatch_date: date,
    predespacho: dict[str, list[float]],
    dispo_declarada: dict[str, list[float]],
    mpo_by_hour: list[float],
    ultimo_precio: dict[str, float],
) -> pd.DataFrame:
    """Fila `ofertas` estimada para `dispatch_date`, un renglon por cada recurso
    resuelto como marginal (ver `detect_marginal_resources`) o presente en
    `ultimo_precio` (la union de ambos conjuntos -- un recurso resuelto sin
    precio historico previo igual recibe fila, usando su MPO inferido; uno sin
    resolver usa el ultimo precio publicado sin cambio)."""
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    rows = []
    for resource in set(ultimo_precio) | set(resolved):
        if resource in resolved:
            value = mpo_by_hour[resolved[resource]] / 1e3
        else:
            value = ultimo_precio[resource]
        rows.append(
            {
                "Date": pd.Timestamp(dispatch_date),
                "resource_name": resource,
                "Value": value,
                "is_estimated": True,
            }
        )
    return pd.DataFrame(rows, columns=["Date", "resource_name", "Value", "is_estimated"])
```

Mover el `import pandas as pd` al tope del archivo junto a `import csv`/`import io`
en vez de dejarlo inline (era solo para mostrar donde entra en este paso).

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_ofertas_heuristic.py -v`
Expected: PASS (10/10)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add app/data/heuristic/biddings.py tests/test_ofertas_heuristic.py
git commit -m "feat: assemble estimated ofertas rows from marginal detection

iMAR's MPO is COP/MWh; ofertas.csv's Value column is raw COP/kWh (same
convention as PrecOferDesp, case_builder.py scales *1e3 downstream) --
divide by 1e3 here so the existing scaling stays correct."
```

---

### Task 4: `ensure_ofertas_estimado` — fuzzy matching, cache, storage

**Files:**
- Modify: `app/data/heuristic/biddings.py`
- Test: `tests/test_ofertas_heuristic.py`

**Interfaces:**
- Consumes: `estimate_ofertas` de Task 3 (misma firma); `app.data.paths.resolve_input`;
  `app.storage.get_storage`.
- Produces: `ensure_ofertas_estimado(dispatch_date: date, data_dir: str, dispo: pd.DataFrame, oferta_full: pd.DataFrame) -> pd.DataFrame`
  — usado por Task 5. `dispo` debe venir ya filtrado a `dispatch_date` (mismas
  columnas que `app.data.loaders.load_dispo`: `resource_name`, `datetime`, `dispo`,
  `gen_type`). Puede propagar `FileNotFoundError` (si `PrId`/`iMAR` no existen para
  la fecha) o `ValueError` (si `iMAR` existe pero no tiene fila `MPO` parseable).

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_ofertas_heuristic.py`:

```python
from app.data.heuristic.biddings import ensure_ofertas_estimado


def _write_prid_imar(tmp_path, fecha_str="2026-08-11", mmdd="0811"):
    day_dir = tmp_path / fecha_str
    day_dir.mkdir(parents=True, exist_ok=True)
    # Nombres identicos a los del universo dispo (no ambiguos para el fuzzy
    # match) -- la robustez del match en si con nombres XM reales/ruidosos
    # queda para iterar despues (issue #35), esto prueba la orquestacion.
    (day_dir / f"PrId{mmdd}_NAL.txt").write_text(
        "TERMO1," + ",".join(["0"] * 5 + ["150"] + ["300"] * 18) + "\n"
        "TERMO2," + ",".join(["200"] * 24) + "\n",
        encoding="latin1",
    )
    mpo_row = ",".join(["1000"] * 5 + ["990000"] + ["1000"] * 18)
    (day_dir / f"iMAR{mmdd}.txt").write_text(
        f'"Costo Marginal",{mpo_row}\n"Delta",' + ",".join(["0"] * 24) + f'\n"MPO",{mpo_row}\n',
        encoding="latin1",
    )
    return day_dir


def test_ensure_ofertas_estimado_matches_names_and_caches(tmp_path):
    fecha = _date(2026, 8, 11)
    _write_prid_imar(tmp_path)

    hours = [pd.Timestamp(fecha) + pd.Timedelta(hours=h) for h in range(24)]
    dispo = pd.DataFrame(
        [
            {"resource_name": "TERMO1", "datetime": h, "dispo": 300_000.0, "gen_type": "TERMICA"}
            for h in hours
        ]
        + [
            {"resource_name": "TERMO2", "datetime": h, "dispo": 200_000.0, "gen_type": "TERMICA"}
            for h in hours
        ]
    )
    oferta_full = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-30"), pd.Timestamp("2026-07-30")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [100.0, 180.0],
        }
    )

    result = ensure_ofertas_estimado(fecha, str(tmp_path), dispo, oferta_full)

    values = result.set_index("resource_name")["Value"].to_dict()
    assert values["TERMO1"] == 990.0  # resuelto hora 5 (990000 MPO / 1e3)
    assert values["TERMO2"] == 180.0  # nunca a media maquina -> fallback ultimo precio

    # Cachea: una segunda llamada no vuelve a leer PrId/iMAR (los borramos y
    # confirmamos que igual funciona, porque debe venir del cache).
    (tmp_path / "2026-08-11" / "PrId0811_NAL.txt").unlink()
    (tmp_path / "2026-08-11" / "iMAR0811.txt").unlink()
    cached_result = ensure_ofertas_estimado(fecha, str(tmp_path), dispo, oferta_full)
    assert cached_result.set_index("resource_name")["Value"].to_dict() == values
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_ofertas_heuristic.py::test_ensure_ofertas_estimado_matches_names_and_caches -v`
Expected: FAIL con `ImportError: cannot import name 'ensure_ofertas_estimado'`

- [ ] **Step 3: Implementar `ensure_ofertas_estimado`**

Agregar a `app/data/heuristic/biddings.py`. Imports nuevos al tope del archivo:

```python
from thefuzz import fuzz, process

from app.data.paths import resolve_input
from app.storage import get_storage
```

Funcion:

```python
def _match_resource_name(raw_name: str, resource_names: list[str]) -> str | None:
    match = process.extractOne(
        query=raw_name.lower(),
        choices=resource_names,
        scorer=fuzz.partial_ratio,
        processor=lambda x: x.lower().replace(" ", ""),
        score_cutoff=70,
    )
    return match[0] if match else None


def ensure_ofertas_estimado(
    dispatch_date: date,
    data_dir: str,
    dispo: "pd.DataFrame",
    oferta_full: "pd.DataFrame",
) -> "pd.DataFrame":
    """Estima (y cachea) las filas `ofertas` para `dispatch_date`. `dispo` debe
    venir ya filtrado a esa fecha. Propaga FileNotFoundError/ValueError si
    PrId/iMAR no estan disponibles o no se pueden parsear -- el llamador decide
    que hacer (ver case_builder.py)."""
    storage = get_storage(data_dir)
    year = dispatch_date.year
    cache_path = f"ofertas_estimado/ofertas_estimado_{year}.csv"

    if storage.exists(cache_path):
        with storage.open(cache_path, "rb") as f:
            cached = pd.read_csv(f, parse_dates=["Date"])
        existing = cached[cached["Date"].dt.date == dispatch_date]
        if not existing.empty:
            return existing.reset_index(drop=True)
    else:
        cached = pd.DataFrame(columns=["Date", "resource_name", "Value", "is_estimated"])

    prid_path = resolve_input("PrId", dispatch_date, data_dir)
    with open(prid_path, encoding="latin1") as f:
        predespacho_raw = parse_predespacho(f.read())

    imar_path = resolve_input("iMAR", dispatch_date, data_dir)
    with open(imar_path, encoding="latin1") as f:
        mpo_by_hour = parse_mpo(f.read())

    resource_names = list(dispo["resource_name"].unique())
    predespacho = {}
    for raw_name, values in predespacho_raw.items():
        matched = _match_resource_name(raw_name, resource_names)
        if matched is not None:
            predespacho[matched] = values

    # dispo_declarada.csv esta en kW (case_builder.py hace *1e-3 -> MW bajo
    # "# Valores en MWh"); PrId (predespacho, generacion despachada) esta en MW
    # crudo, sin escalar (mismo convenio documentado en agc.py). Sin este *1e-3
    # aqui, "disponible" queda ~1000x mas grande que "despachado" siempre, la
    # regla "a media maquina" nunca filtra nada, y todo cae al fallback en
    # silencio -- no lo detectes por un test fallando, detectalo por unidades.
    dispo_declarada = {
        resource: (group.sort_values("datetime")["dispo"] * 1e-3).tolist()
        for resource, group in dispo.groupby("resource_name")
    }

    ultimo_precio = (
        oferta_full.sort_values("Date").groupby("resource_name")["Value"].last().to_dict()
    )

    estimated = estimate_ofertas(
        dispatch_date, predespacho, dispo_declarada, mpo_by_hour, ultimo_precio
    )

    cached = pd.concat([cached, estimated], ignore_index=True)
    with storage.open(cache_path, "w") as f:
        cached.to_csv(f, index=False)

    return estimated
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_ofertas_heuristic.py -v`
Expected: PASS (11/11)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add app/data/heuristic/biddings.py tests/test_ofertas_heuristic.py
git commit -m "feat: orchestrate ofertas estimation with name matching + cache

Fuzzy-matches PrId's raw resource names against the run's known resource
universe (same pattern as case_builder.py's other XM name mappings), and
caches the result in ofertas_estimado/ofertas_estimado_{year}.csv so a
repeat run for the same date doesn't need PrId/iMAR again."
```

---

### Task 5: Integrar en `case_builder.py`

**Files:**
- Modify: `app/pipeline/case_builder.py:20-29` (imports), `:107-117` (el `raise`)
- Test: `tests/test_xm_smoke_build_case.py`

**Interfaces:**
- Consumes: `ensure_ofertas_estimado` de Task 4 (misma firma).

- [ ] **Step 1: Escribir los tests (uno ajustado, uno nuevo) que fallan**

En `tests/test_xm_smoke_build_case.py`, el test existente
`test_build_case_raises_clear_error_when_ofertas_empty_for_date` asume que
`ofertas.csv` vacio para la fecha SIEMPRE lanza — con la heuristica de por medio,
solo debe lanzar si TAMPOCO hay `ultimo_precio` (oferta historica) para ningun
recurso. Cambiar su `ofertas_2024.csv` para que no tenga ninguna fila (antes tenia
una fila de TERMO1):

```python
def test_build_case_raises_clear_error_when_ofertas_empty_for_date(tmp_path, monkeypatch):
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # Sin ninguna fila historica -> la heuristica tampoco tiene de donde
    # sacar un "ultimo precio publicado", asi que sigue sin poder estimar.
    (tmp_path / "ofertas" / "ofertas_2024.csv").write_text("Date,resource_name,Value\n")
    # Create the missing dispo_come partition so ensure_bulk_data_for_year doesn't try to fetch it
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text("datetime,resource_name,dispo\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    fecha = date(2024, 4, 18)
    case = DispatchCase(dispatch_date=fecha, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=fecha, source=InputSource.historical, data_dir=str(tmp_path))

    with pytest.raises(ValueError, match="ofertas"):
        build_case(case, inputs)
```

Agregar, despues de ese test, uno nuevo verificando el camino feliz de la heuristica:

```python
def test_build_case_uses_heuristic_when_ofertas_missing_but_historical_data_exists(
    tmp_path, monkeypatch
):
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # Sin fila para la fecha del dispatch, pero SI hay precio historico para
    # ambos generadores -> la heuristica puede al menos usar el fallback.
    (tmp_path / "ofertas" / "ofertas_2024.csv").write_text(
        "Date,resource_name,Value\n2024-04-15,TERMO1,150\n2024-04-15,TERMO2,180\n"
    )
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text("datetime,resource_name,dispo\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    fecha = date(2024, 4, 18)
    case = DispatchCase(dispatch_date=fecha, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=fecha, source=InputSource.historical, data_dir=str(tmp_path))

    # No debe lanzar -- la heuristica cubre el hueco.
    _, param_data, _ = build_case(case, inputs)
    beta = dict(param_data["beta"])
    # PrId del fixture usa el nombre "TOTAL" (no matchea TERMO1/TERMO2), asi
    # que ningun recurso se resuelve como marginal -- ambos caen al fallback
    # de ultimo precio publicado, escalado x1e3 (COP/kWh -> COP/MWh).
    assert beta == {"TERMO1": 150000.0, "TERMO2": 180000.0}
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_xm_smoke_build_case.py -v`
Expected: el primero (`raises_clear_error`) FAIL porque hoy revienta apenas
`ofertas.empty` es `True`, sin intentar la heuristica todavia (mensaje sigue siendo
el viejo, deberia seguir pasando en realidad -- revisar en el siguiente paso).
Expected: el segundo (`uses_heuristic`) FAIL con `ValueError` (el `raise` viejo
sigue ahi, no hay heuristica todavia).

- [ ] **Step 3: Integrar en `case_builder.py`**

Agregar el import (junto a los demas `from app.data...` en la cabecera, linea ~25):

```python
from app.data.heuristic.biddings import ensure_ofertas_estimado
```

Reemplazar el bloque (lineas ~107-117):

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

por:

```python
    oferta_full = ofertas.copy()
    ofertas = ofertas[ofertas.Date.dt.date == DISPATCH_DATE]
    if ofertas.empty:
        try:
            ofertas = ensure_ofertas_estimado(DISPATCH_DATE, dd, dispo, oferta_full)
        except (FileNotFoundError, ValueError):
            ofertas = pd.DataFrame(columns=["Date", "resource_name", "Value", "is_estimated"])
    if ofertas.empty:
        raise ValueError(
            f"no hay ofertas (PrecOferDesp) publicadas por XM para {DISPATCH_DATE}, y "
            "tampoco se pudo estimar con la heuristica (PrId/iMAR no disponibles, o sin "
            "precio historico de ningun recurso). XM publica PrecOferDesp por mes "
            "calendario completo, un mes despues (agosto completo solo esta disponible "
            "desde el 1 de septiembre) -- intente con una fecha de un mes ya cerrado."
        )
```

Nota: `dispo` en este punto ya esta filtrado y deduplicado para `DISPATCH_DATE`
(lineas 103-104, sin cambios) -- es exactamente lo que `ensure_ofertas_estimado`
espera.

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_xm_smoke_build_case.py -v`
Expected: PASS (ambos, mas los 3 tests preexistentes del archivo).

- [ ] **Step 5: Correr toda la suite**

Run: `uv run pytest -q`
Expected: PASS, todos los tests (incluyendo Fases previas, sin regresiones).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add app/pipeline/case_builder.py tests/test_xm_smoke_build_case.py
git commit -m "feat: fall back to ofertas heuristic instead of hard-failing (#30)

case_builder.py no longer raises immediately when PrecOferDesp has no
data for the dispatch date -- it now tries the marginal-detection
heuristic first (app.data.heuristic.biddings), only raising if that
also can't produce a price for any resource."
```

---

## Self-Review

**Cobertura del spec:** seccion 1.1 (bug _NAL) -> Task 1. Seccion 3.1/3.2 (candidatos
+ eliminacion) -> Task 2. Seccion 1.2/3.3 (unidades + fallback) -> Task 3. Seccion 2
(arquitectura, fuzzy matching) + seccion 4 (trazabilidad/cache) -> Task 4. Seccion 2
(call site) -> Task 5. Seccion 5 (testing) cubierta por los tests de cada task —
`estimate_ofertas`/`ensure_ofertas_estimado` tienen su e2e propio (Task 3/4); el
e2e completo via `build_case` (Task 5) queda acotado a la integracion (no repite
la logica del algoritmo, ya probada). Seccion 6 (riesgos conocidos) queda
documentada en el spec, no requiere tarea — son fuera de alcance explicito.

**Placeholders:** ninguno — todo paso tiene codigo real, ningun "TODO"/"similar a".

**Consistencia de tipos:** `estimate_ofertas` devuelve siempre
`["Date", "resource_name", "Value", "is_estimated"]`, usado igual en Task 3 y Task 4.
`detect_marginal_resources` devuelve `dict[str, int]`, consumido igual en Task 3.
`ensure_ofertas_estimado` devuelve `pd.DataFrame` con las mismas columnas, consumido
igual en Task 5 (`ofertas = ensure_ofertas_estimado(...)`).
