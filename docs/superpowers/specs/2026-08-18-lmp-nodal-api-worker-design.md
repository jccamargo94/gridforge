# Spec — Fase 2: API/worker de persistencia para corridas LMP nodales

**Fecha:** 2026-08-18
**Fase:** 2 de 4 del módulo LMP nodal
**Módulo:** `app/nodal/`
**Estado:** aprobado (revisión de decisiones delegada a subagente de decisión)

## 1. Objetivo

Persistir las corridas LMP nodales de la Fase 1 en la base de datos y exponerlas
a través de la API y del worker existentes:

- Reusar las tablas `runs` y `input_datasets` ya construidas.
- Agregar una tabla `nodal_results` (una fila por corrida nodal) que capture las
  métricas de comparación Escenario A vs B y las rutas de los artefactos.
- Permitir lanzar una corrida nodal desde la API (con una red zonal elegida),
  consultarla y descargar sus artefactos.
- Dejar que el worker ejecute las corridas largas (ya fluyen por `run_case`
  cuando `level == "lmp"`).

No se toca el ancla mononodo (`app/model/`, `app/pipeline/case_builder.py`).

## 2. Contexto (qué ya existe)

Fase 1 (mergeada, PR #64) construyó el motor nodal:

- `app/nodal/runner.py::run_nodal(case, *, out, data_dir) -> RunResult` — carga
  la red (de `case.nodal_network` path o del ejemplo empaquetado), resuelve con
  `EgretNodalEngine`, liquida A+B, compara, escribe artefactos en
  `out_dir = f"{out}/{dispatch_date}-lmp"` y devuelve
  `RunResult(ok=True, dispatch_path=paths["dispatch"], metrics=comparison.metrics)`.
- `app/nodal/reporting.py::save_nodal_artifacts(...) -> dict[str,str]` — escribe
  `lmp.csv`, `dispatch.csv`, `branch_flows.csv`, `settlement_status_quo.csv`,
  `settlement_lmp.csv`, `comparison.csv`, `summary.json` y devuelve nombres
  **relativos**.
- `app/pipeline/runner.py::run_case` — cuando `level == DispatchLevel.lmp`
  importa y devuelve `run_nodal(...)`. Por lo tanto, las corridas nodales **ya
  fluyen por el worker** y crean filas en `runs`/`cases`.

La API/worker/DB de persistencia clásica ya existe:

- `app/db/models.py`: `Case`, `Run`, `MetricSet`, `InputDataset`, `Scenario`.
  `Case` **no** tiene columna `nodal_network`.
- `app/db/queries.py`: `create_case_and_run`, `finish_run_ok`,
  `finish_run_failed`, `get_metric_set`, `get_run`, `get_case`, etc.
- `services/worker/main.py::process_once` — reclama run pendiente, reconstruye
  `DispatchCase` vía `_build_case`, ejecuta `run_case`, escribe log, luego
  `finish_run_ok`/`finish_run_failed`.
- `services/api/main.py` — FastAPI con endpoints inline: `POST /runs`,
  `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/log`,
  `GET /runs/{id}/{artifact}`, `GET /runs/{id}/download/{artifact}`.

## 3. Brechas que esta fase cierra

1. `Case` en DB no tiene `nodal_network` → la API no puede lanzar una corrida
   nodal con una red elegida, y el worker no puede reconstruirla (usa el ejemplo
   empaquetado por defecto).
2. Los artefactos nodales se escriben a disco pero no se persisten ni son
   descubribles por la API; los endpoints de artefactos no los conocen.
3. Las métricas nodales de comparación (`total_cost`, `load_payment_delta`,
   `gen_revenue_delta`, `congestion_rent_total`, `price_avg_<z>`,
   `price_vol_<z>`) no caben en las columnas clásicas de `MetricSet` →
   `finish_run_ok` las descarta en silencio.

Además, un bug latente: `run_nodal` devuelve `dispatch_path` **relativo**
(`"dispatch.csv"`), que rompe para cualquier llamador que no sea el worker
(no lo une a `out_dir`).

## 4. Arquitectura y cambios

### 4.1 Persistencia de la red (`cases.nodal_network`)

Se agrega una columna JSON nullable `nodal_network` a `cases` con la red
serializada (`NodalNetwork` dict). Decisión: guardar el dict JSON en la fila, no
un `networks` + FK — `input_datasets` rastrea datasets XM descargados, no redes
de usuario; un dict JSON es el alcance correcto. Si más adelante las redes se
reutilizan/crecen, la vía de upgrade es una tabla `networks` + `network_id`.

**Dualidad de nombre (glosario):** hay tres cosas distintas con el mismo nombre
`nodal_network`:
- `Case.nodal_network` (DB) → dict serializado de la red enviada por el usuario.
- `DispatchCase.nodal_network` (schema) → **path** a un JSON en disco.
- `NodalResult.network` (DB) → snapshot de la red **post-inyección de cargas**
  (con `loads` de 24h cuando `demand_shares` está seteado), distinto del dict
  enviado.

### 4.2 Tabla `nodal_results` (migración 0005)

Una fila por corrida nodal, `run_id` único FK → `runs.id`:

| columna | tipo | nota |
|---|---|---|
| `id` | String PK | `_new_id()` |
| `run_id` | String FK unique | → `runs.id` |
| `metrics` | JSON | `comparison.metrics` (dict[str,float]) |
| `redistribution` | JSON | lista de registros `{zone,load_payment_a,load_payment_b,delta}` |
| `gen_revenue_by_zone` | JSON | lista `{zone,fuel,revenue_a,revenue_b,delta}` (NO se escribe como artefacto en reporting → por eso va en DB) |
| `network` | JSON | snapshot post-inyección de cargas |
| `lmp_path` | String nullable | ruta completa a `lmp.csv` |
| `dispatch_path` | String nullable | ruta completa a `dispatch.csv` |
| `branch_flows_path` | String nullable | |
| `settlement_status_quo_path` | String nullable | |
| `settlement_lmp_path` | String nullable | |
| `comparison_path` | String nullable | |
| `summary_path` | String nullable | |

Las 7 columnas de path siguen la convención de paths explícitos de `runs` y el
patrón del mapa `_ARTIFACT_PATHS` de la API.

### 4.3 Schema `NodalRunResult` en `RunResult`

Nuevo modelo pydantic `NodalRunResult` con: las 7 rutas de artefactos
(`str | None`), `metrics: dict[str,float]`, `redistribution: list[dict]`,
`gen_revenue_by_zone: list[dict]`, `network: dict`. Se agrega
`nodal: NodalRunResult | None = None` a `RunResult`.

`run_nodal` puebla `NodalRunResult` con **rutas completas**:
`f"{out_dir}/{rel}"`. Además se corrige el bug latente: `dispatch_path` pasa a
ser la ruta completa `f"{out_dir}/dispatch.csv"` (para llamadores no-worker).

### 4.4 Consultas

- `create_case_and_run(..., nodal_network: dict | None = None)` → guarda el dict
  en `Case.nodal_network`.
- `get_nodal_result(session, run_id) -> NodalResult | None`.
- `finish_nodal_run_ok(session, run, result: RunResult, out_dir)`:
  - Marca `run.status="done"`, `finished_at`, `out_dir`.
  - Inserta una `NodalResult` (no un `MetricSet`).
  - **NO** hace `session.rollback()` (a diferencia de `finish_run_failed`): el
    `run.log_path` seteado en memoria por `process_once` debe sobrevivir al
    commit. Mismo patrón add+commit que `finish_run_ok`.
  - Deja las columnas clásicas de `Run` (`dispatch_path`, `price_path`, …) como
    `None`: no hay ambigüedad sobre qué set de artefactos es el autoritativo.

**Decisión MetricSet:** para corridas nodales **solo** `NodalResult`, nunca un
`MetricSet` clásico — las métricas nodales no comparten columnas con el
`MetricSet` clásico, y escribir una fila all-None produciría un "metrics exist"
engañoso vía `get_metric_set`. `GET /runs/{id}` maneja la uniformidad devolviendo
`metrics: null` + un objeto `nodal` completo.

### 4.5 Worker

- `process_once`: después de construir el `case` y antes del solve, si
  `case_row.nodal_network` está seteado, escribir
  `{out_dir}/network.json` (vía `get_storage`), setear `case.nodal_network` a esa
  ruta (el flujo path-based de `load_network` queda intacto).
- Branch de finalización por **fuente de verdad** `result.ok and result.nodal is
  not None` → `finish_nodal_run_ok`; caso contrario el flujo clásico
  (`finish_run_ok`/`finish_run_failed`). No ramificar por `case.level`.

### 4.6 API

- `POST /runs` gana `nodal_network: NodalNetwork | None = None` (validación
  pydantic). Si se envía para `level != "lmp"` → **400** (fail fast, no ignorar
  en silencio). Se pasa a `create_case_and_run`.
- `GET /runs/{id}`: cuando existe `NodalResult`, devuelve `nodal` con
  `{metrics, redistribution, gen_revenue_by_zone, network, artifacts:{...}}`
  (flags booleanos por artefacto) y `metrics: null`.
- Nuevo `GET /runs/{run_id}/nodal/{artifact}` → filas JSON para
  `{lmp, dispatch, branch_flows, settlement_status_quo, settlement_lmp,
  comparison, summary}`. `summary` devuelve el JSON parseado (es el único
  artefacto JSON; la UI no debería necesitar un download para leer los totales).
- Nuevo `GET /runs/{run_id}/download/nodal/{artifact}` → descarga del archivo
  (incluye `summary.json`).
- Todas las rutas nuevas pasan por `_get_owned_run` (ownership check).

### 4.7 Convención de paths (`-lmp`)

`run.out_dir` sigue siendo la raíz del run (`{results_root}/{run.id}`) y los
artefactos viven un nivel más abajo en `{run.id}/{dispatch_date}-lmp/`. Las
columnas de path del `NodalResult` guardan la ruta completa
`{out}/{dispatch_date}-lmp/<file>`, que la API ubica con
`get_storage(".").exists(path)`. Documentar esta convención en el plan.

## 5. Alcance / fuera de alcance

**Dentro:** persistencia de corridas nodales, endpoints de lanzar/consultar/
descargar, worker ejecutando corridas largas, migración 0005, tests.

**Fuera (diferido):**
- Frontend (Fase 3) que consuma el objeto `nodal`. Hasta entonces, una corrida
  nodal mostrará flags clásicos en false en la UI actual (asimetría aceptada).
- Redes reutilizables en `networks` con FK (vía de upgrade futura).
- Prescient (Fase 4).
- Validación de la red entregada como algo más que el `model_validator` de
  `NodalNetwork` (422 en input malformado es correcto).

## 6. Testing

- Migración 0005 (`upgrade head` crea `nodal_results` + columna `cases.nodal_network`; `downgrade` los elimina) con el patrón inspect de `tests/test_db_migrations.py`.
- `test_db_models`: round-trip de `NodalResult`.
- `test_db_queries`: `create_case_and_run` con `nodal_network`; `get_nodal_result`; `finish_nodal_run_ok` (sin rollback, deja clásicas en None, no crea MetricSet).
- `test_worker_main`: corrida nodal end-to-end (`level="lmp"`, `nodal_network` = red de ejemplo) → `run.status=="done"`, existe `NodalResult`, 7 paths existen, sin MetricSet. Usa `tests/fixtures/xm_smoke` (fecha 2024-04-18; `tests/fixtures/xm_smoke/demaCome/demaCome_2024.csv` tiene las 24 filas de ese día).
- `test_api_runs` / `test_api_results`: `POST /runs` nodal (200 con run_id; 400 si `nodal_network` con `level != lmp`); `GET /runs/{id}` devuelve `nodal`; `GET /runs/{id}/nodal/lmp` → 72 registros (24h × 3 zonas); `GET /runs/{id}/download/nodal/summary.json` → 200; ownership 404.
- `test_nodal_runner`: `run_nodal` devuelve `NodalRunResult` con paths completos; `dispatch_path` ya no es relativo.

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Tiempo de solve en tests (cbc UC MILP 24h×3 + DCOPF) | Mantener red a escala de ejemplo; usar `mipgap` default; timeout más holgado en ese test, no red más chica. |
| Asimetría de UI (frontend ve flags clásicos en false) | Aceptada y documentada; Fase 3 consume `nodal`. |
| Confusión por la dualidad de `nodal_network` (dict/path/snapshot) | Glosario en este spec y en el plan. |
| Input malformado de red → 422 crudo | Aceptado; `NodalNetwork._validate_references` valida referencias y `demand_shares`. |
| `finish_nodal_run_ok` sin rollback | Espec intencional; documentado para no regresar al patrón de `finish_run_failed`. |

## 8. Referencias

- Spec Fase 1: `docs/superpowers/specs/2026-08-18-lmp-nodal-market-design.md`
- Plan Fase 1: `docs/superpowers/plans/2026-08-18-lmp-nodal-market.md`
- README del módulo: `docs/superpowers/plans/README-nodal.md`
