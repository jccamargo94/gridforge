# Spec — Resultados de corrida: métricas correctas + visualización completa

Fecha: 2026-08-12. Sigue a la prueba e2e (issue #50) y a la observación de
que el MPO real del predespacho ideal vive en el archivo `iMAR{MMDD}.txt`
(ya descargado por fecha).

## Objetivo

En el detalle de una corrida (`frontend/app/(app)/runs/[id]/page.tsx`), poder
**ver y descargar** la mayor cantidad de información útil de la corrida:

1. Métricas con unidades correctas.
2. Métricas de despacho (además de las de precio).
3. Las dos series de tiempo del precio del día (modelo vs XM).
4. Las plantas que marginan en cada hora.
5. Descarga de todos los artefactos nuevos.

## Decisiones de unidades (verificadas contra el código)

- Métricas de **precio** (modelo MPO vs XM MPO, ambos COP/MWh — `metrics.price_metrics`):
  - `RMSE` / `MAE` / `bias` → **COP/MWh**.
  - `WAPE` / `sMAPE` → fracción; mostrar **×100 con `%`**.
  - `R²` → adimensional.
- Métricas de **despacho** (generación modelo vs PrId, ambos MW):
  - `dispatch_mae_mw` / `dispatch_rmse_mw` → **MW**.

No se agrega MAPE (el repo lo evita deliberadamente; WAPE/sMAPE son los
reemplazos robustos).

## Cambios backend

### Migración `0004`

- `metric_sets`: agregar `dispatch_mae_mw` Float nullable y
  `dispatch_rmse_mw` Float nullable.
- `runs`: agregar `marginal_plants_path` String nullable.

### `app/pipeline/results.py`

- Nueva `extract_marginal_plants(model) -> pd.DataFrame` con columnas
  `datetime, generador, dispatch, pmax, is_marginal`. Una planta **margina** en
  `(g,t)` si `0 < pout[g,t] < Pmax[g,t]` (con tolerancia ~1e-6). Se calcula
  después del solve completo (MILP + pricing LP).
- `save_results` guarda `marginal_plants-{date}-{type}.csv` y devuelve su path
  en `RunResult.marginal_plants_path`.

### `app/pipeline/runner.py` (bloque `evaluate`)

- Además de las métricas de precio, calcular métricas de despacho:
  - `load_actual_dispatch` (ver abajo) → PrId por recurso (MW).
  - `extract_dispatch(model)` → despacho modelo (MW).
  - Mapear nombres PrId → generadores modelo con el matcher fuzzy ya existente
    (`app/data/heuristic/biddings.py::_match_resource_name`, exportarlo si hace
    falta). Calcular MAE/RMSE sobre los pares `(generador, hora)` con match.
  - Guardar en `result.metrics` bajo `dispatch_mae_mw` / `dispatch_rmse_mw`.
  - Si no hay PrId o no hay matches, dejar las claves ausentes (métricas None).
- `RunResult.metrics` sigue siendo `dict[str, float] | None`, así que las claves
  nuevas se persisten igual que las de precio.

### `app/data/actuals.py`

- Cambiar `load_actual_dispatch` para leer el **PrId** (predespacho ideal por
  recurso, MW) usando `resolve_input("PrId", ...)` + `parse_predespacho` de
  `app/data/heuristic/biddings.py` (devuelve `{nombre: [24 MW]}`). El path
  actual `preideal_dispatch/{date}.txt` no existe en el repo (mismo problema que
  el precio).

### `app/db/models.py` + `app/db/queries.py`

- `MetricSet`: agregar las 2 columnas de despacho.
- `Run`: agregar `marginal_plants_path`.
- `finish_run_ok`: persistir `dispatch_mae_mw`/`dispatch_rmse_mw` (leer de
  `result.metrics`) y `marginal_plants_path`.

### `services/api/main.py`

- `get_run_detail`: incluir en `metrics` las claves nuevas
  `dispatch_mae_mw`, `dispatch_rmse_mw`; incluir `marginal_plants` en
  `artifacts` (booleano); e incluir `price_series`:
  ```json
  [{"datetime": "...", "model_mpo": 91354.0, "xm_mpo": 91354.12}, ...]
  ```
  compuesto leyendo `run.price_path` (modelo) y `load_actual_price` (iMAR). Si
  falta alguna fuente, `price_series = null`.
- Nuevos endpoints (siguen el patrón de `_artifact_path`/`get_run_artifact`):
  - `GET /runs/{id}/marginal-plants` → records del CSV.
  - `GET /runs/{id}/download/marginal_plants` → CSV.
  - `GET /runs/{id}/download/price_comparison` → CSV `datetime,model_mpo,xm_mpo`
    (generado on-the-fly desde `price_path` + `load_actual_price`).

## Cambios frontend

### `lib/types.ts`

- `RunMetrics`: agregar `dispatch_mae_mw: number | null` y
  `dispatch_rmse_mw: number | null`.
- `RunDetail`: agregar `price_series: PricePoint[] | null` con
  `PricePoint = { datetime: string; model_mpo: number; xm_mpo: number }`.
- `RunArtifacts`: agregar `marginal_plants: boolean`.
- Nuevo `MarginalPlant = { datetime: string; generador: string; dispatch: number; pmax: number; is_marginal: boolean }`.

### `lib/api-client.ts`

- `getRunPrices`/`getRunPriceSeries` no hace falta: `price_series` va en el
  detalle. Agregar `getRunMarginalPlants(id): Promise<MarginalPlant[]>`.
- Ampliar el tipo de `downloadRunArtifact` a
  `"dispatch" | "prices" | "bess" | "marginal_plants" | "price_comparison"`.

### `app/(app)/runs/[id]/page.tsx`

- Tarjetas de métricas con unidades correctas:
  - RMSE/MAE/Sesgo → `COP/MWh`.
  - WAPE/sMAPE → `×100`, `%`.
  - R² → sin unidad.
  - Nuevas: MAE despacho y RMSE despacho → `MW`.
- Nueva sección **Precios** (`LineChart` recharts): dos líneas
  `model_mpo` y `xm_mpo` vs hora.
- Nueva sección **Plantas que marginan por hora**: tabla agrupada por hora
  (filtrar `is_marginal`), con descarga.
- `ArtifactDownloads`: agregar botones "Marginal plants CSV" y
  "Price comparison CSV".

### `lib/i18n.ts`

- Agregar claves es/en para las etiquetas nuevas (unidades, secciones, descargas).

## Testing

- `tests/test_results.py`: `extract_marginal_plants` (planta a media carga es
  marginal; a tope o a 0 no).
- `tests/test_actuals.py`: `load_actual_dispatch` lee PrId.
- `tests/test_metrics.py` o similar: métricas de despacho (MAE/RMSE MW) con
  mapeo de nombres.
- `tests/test_db_migrations.py` / `test_db_models.py`: columnas nuevas.
- `tests/test_api_results.py`: `price_series`, `marginal_plants`, descargas.
- Frontend: tests de los componentes nuevos (siguen patrón `*.test.tsx`).
- Gates: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`,
  y en `frontend/` `pnpm lint` / `pnpm test` si están configurados.

## Fuera de alcance

- Métricas de despacho por tecnología (existe `generation_by_tech` pero no se
  cablea aquí).
- Comparación de compromiso on/off (existe `commitment_metrics`).
- Descarga del despacho real de PrId crudo (no pedido explícito).
