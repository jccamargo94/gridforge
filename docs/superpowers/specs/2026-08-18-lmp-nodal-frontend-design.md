# Spec — Fase 3: Dashboard de comparación nodal (frontend)

**Fecha:** 2026-08-18
**Fase:** 3 de 4 del módulo LMP nodal
**Módulos:** `frontend/` (+ enriquecimiento mínimo de `services/api/main.py`)
**Estado:** aprobado en brainstorming

## 1. Objetivo

Construir el dashboard de comparación nodal en el frontend existente de
GridForge: una página por corrida nodal (`/runs/[id]/nodal`) que visualiza el
despacho LMP y la comparación Escenario A (precio único + congestión
socializada) vs Escenario B (LMP ex-ante vinculante), más una página de
descubrimiento de corridas nodales (`/nodal`) con su red asociada.

Consume la API de la Fase 2 (ya mergeada): el objeto `nodal` de
`GET /runs/{id}` y los endpoints `GET /runs/{id}/nodal/{artifact}` /
`GET /runs/{id}/download/nodal/{artifact}`.

## 2. Contexto (qué ya existe)

- **Fase 1** (mergeada, PR #64): módulo `app/nodal/` — motor EGRET
  (`EgretNodalEngine`), settlements A/B sobre el mismo despacho, comparación y
  reporting. Artefactos: `lmp.csv`, `dispatch.csv`, `branch_flows.csv`,
  `settlement_status_quo.csv`, `settlement_lmp.csv`, `comparison.csv`,
  `summary.json`.
- **Fase 2** (mergeada, PR #65): tabla `nodal_results`, columna
  `cases.nodal_network`, worker ejecutando corridas LMP, y API:
  - `GET /runs/{id}` → `nodal: {metrics, redistribution, gen_revenue_by_zone,
    network, artifacts:{...}} | null` (y `metrics: null` cuando hay nodal).
    `network` es el snapshot **post-inyección de cargas** del `NodalNetwork`
    (dict completo).
  - `GET /runs/{id}/nodal/{artifact}` → filas JSON (`lmp`, `dispatch`,
    `branch_flows`, `settlement_status_quo`, `settlement_lmp`, `comparison`) o
    JSON parseado (`summary`).
  - `GET /runs/{id}/download/nodal/{artifact}` → archivo crudo.
  - `GET /runs` → lista de runs con `level` por corrida (sin info nodal).
- **Frontend** (`frontend/`): Next.js 16.3 App Router, React 19, Tailwind v4,
  shadcn/ui sobre Base UI (no Radix), `@tanstack/react-query` v5, recharts
  3.10, vitest + Testing Library, i18n es/en (default es). **No hay ninguna UI
  nodal** — hoy una corrida LMP muestra los flags clásicos en false (asimetría
  aceptada en Fase 2).
- **Datos verificados** (`app/nodal/reporting.py`):
  - `lmp.csv`: `timestamp, bus, lmp` (24h × N zonas).
  - `dispatch.csv`: `generator, zone, fuel, hour, dispatch_mw`.
  - `branch_flows.csv`: `timestamp, branch, flow_mw`.
  - `settlement_status_quo.csv`: `zone, hour, load_payment, gen_revenue, uplift`.
  - `settlement_lmp.csv`: `zone, hour, load_payment, gen_revenue`.
  - `comparison.csv`: `zone, load_payment_a, load_payment_b, delta`.
  - `summary.json`: `{metrics, totals, generator_count, branch_count}`.

## 3. Decisiones de diseño (acordadas en brainstorming)

1. **Mapa zonal = diagrama esquemático por topología.** El schema `NodalNetwork`
   no tiene coordenadas (Zone = `name` + `base_kv`). El layout de nodos se
   calcula de la topología (spring-embedder determinista) y cada nodo se colorea
   según el LMP de la hora seleccionada. Funciona con cualquier red JSON, sin
   datos geográficos. Mapas geográficos reales quedan fuera de alcance.
2. **Ruta dedicada `/runs/[id]/nodal`**, enlazada desde el detalle del run
   (visible solo cuando `data.nodal` existe). El detalle clásico no crece y
   cada mentalidad tiene su página.
3. **Descubrimiento global: ítem "Nodal" en el sidebar** → `/nodal`, lista de
   corridas nodales. Para mostrar la red de cada corrida en la lista, se
   **enriquece `GET /runs`** con `nodal: {network_name, zones, generators,
   branches} | null` por fila (decisión explícita del usuario — acepta el costo
   de 1 query extra por fila).
4. **Alcance de vistas:** spec (métricas, mapa, curvas, tabla de diferencial,
   matriz de redistribución) **+ despacho nodal y flujos de rama** (decisión
   explícita del usuario).
5. **La topología completa se muestra en el dashboard** vía la tarjeta "Red
   utilizada" (nombre, baseMVA, referencia, zonas, generadores, ramas) usando el
   `network` snapshot que ya viaja en `data.nodal.network` — sin fetch extra.
6. **Un solo fetch por artefacto** con react-query (`queryKey` por
   `[nodal-<artifact>, id]`), `enabled` según `data.nodal`. El `lmp` (72 filas
   en la red de ejemplo) y los demás artefactos son pequeños.

## 4. Arquitectura

### 4.1 Rutas

- `app/(app)/nodal/page.tsx` — lista de corridas nodales (hereda el shell
  autenticado). Filtra client-side por `level === "lmp"` sobre `GET /runs`.
- `app/(app)/runs/[id]/nodal/page.tsx` — dashboard de comparación nodal.
- Enlace desde `app/(app)/runs/[id]/page.tsx`: cuando `data.nodal` existe, un
  `Link` "Análisis nodal" en la cabecera del run.
- Sidebar (`components/app-sidebar.tsx`): nuevo `NAV_ITEM` `{ href: "/nodal",
  labelKey: "sidebar.nodal", icon: Network }`. El check de activo pasa de
  `pathname.startsWith(href)` a también activar con `pathname.includes("/nodal")`
  para el item nodal (para que `/runs/[id]/nodal` lo marque activo).

### 4.2 Enriquecimiento mínimo de la API (`services/api/main.py`)

`list_runs_endpoint` agrega a cada resumen un campo `nodal`:

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

- Se agrega al loop de `list_runs` (cada resumen gana el campo `nodal`).
  `GET /runs/{id}` **no cambia**: su objeto `nodal` ya incluye el `network`
  completo, del que estos cuatro campos son derivables. Nota: `RunSummary` del
  frontend gana el campo `nodal` — la tabla de runs existente no lo muestra
  (no rompe).
- **Sin cambios de migración**: solo respuesta JSON.

### 4.3 Tipos frontend (`frontend/lib/types.ts`)

- `DispatchLevel` → `"preideal" | "ideal" | "lmp"`.
- `RunSummary.nodal` → `{ network_name: string | null; zones: number;
  generators: number; branches: number } | null`.
- `NodalMetrics = Record<string, number>` (keys: `total_cost`,
  `load_payment_delta`, `gen_revenue_delta`, `congestion_rent_total`,
  `price_avg_<z>`, `price_vol_<z>`).
- `NodalRedistributionRow = { zone: string; load_payment_a: number;
  load_payment_b: number; delta: number }`.
- `NodalGenRevenueRow = { zone: string; fuel: string; revenue_a: number;
  revenue_b: number; delta: number }`.
- `NodalArtifactName = "lmp" | "dispatch" | "branch_flows" |
  "settlement_status_quo" | "settlement_lmp" | "comparison" | "summary"`.
- `NodalResult = { metrics: NodalMetrics; redistribution:
  NodalRedistributionRow[]; gen_revenue_by_zone: NodalGenRevenueRow[]; network:
  NodalNetwork; artifacts: Record<NodalArtifactName, boolean> }`.
- `RunDetail.nodal: NodalResult | null`.
- Mirror TS del schema pydantic: `NodalNetwork {name, baseMVA, reference_zone,
  zones: Zone[], generators: Generator[], branches: Branch[], loads: BusLoad[],
  demand_shares}`; `Zone {name, base_kv}`; `Generator {name, zone, p_min, p_max,
  marginal_cost, no_load_cost, fuel, min_up_time, min_down_time, initial_status,
  ramp_rate}`; `Branch {name, from_zone, to_zone, reactance, rating}`;
  `BusLoad {zone, p_load: number[]}`.
- Filas de artefactos: `LmpRow {timestamp, bus, lmp}`; `NodalDispatchRow
  {generator, zone, fuel, hour, dispatch_mw}`; `BranchFlowRow {timestamp, branch,
  flow_mw}`; `SettlementRow {zone, hour, load_payment, gen_revenue, uplift?}`;
  `NodalSummaryJson {metrics, totals, generator_count, branch_count}`.

### 4.4 API client (`frontend/lib/api-client.ts`)

- `getRunNodalArtifact<T>(id, artifact: NodalArtifactName)` → para `summary`
  devuelve el JSON parseado; para el resto, las filas como `T[]`.
- `downloadNodalArtifact(id, artifact)` → `GET /runs/{id}/download/nodal/{artifact}`
  como Blob (patrón `downloadRunArtifact` actual).

## 5. Vistas del dashboard (`/runs/[id]/nodal`)

Orden de la página:

1. **Cabecera**: reusa el patrón del run detail (run_id mono, fecha + badge
   `lmp`, timestamp, status pill, `Link` "Volver al detalle").
2. **Selector de hora (0–23)** + **tarjetas de métricas**: `MetricCard` (patrón
   local de run detail) para `total_cost`, `load_payment_delta`,
   `gen_revenue_delta`, `congestion_rent_total`, y `price_avg_<z>` /
   `price_vol_<z>` (render dinámico por zona). Fuente: `data.nodal.metrics`.
   El selector de hora gobierna mapa y curvas.
3. **Mapa zonal + Red utilizada** (grid de 2 columnas):
   - `components/nodal/zonal-map.tsx` — `<svg>` con nodos (círculos, etiqueta
     del nombre de zona) coloreados según LMP de la hora seleccionada (escala
     continua min→max, azul→ámbar) y aristas (ramas). Tooltip: zona, LMP,
     carga, generación de la zona.
   - `components/nodal/network-card.tsx` — "Red utilizada": nombre, baseMVA,
     zona de referencia, zonas, generadores (zona/fuel/costo marginal), ramas
     (from→to/reactancia/rating).
4. **Curvas de precio**: `components/nodal/price-curves-chart.tsx` — línea por
   zona (24h) + línea "precio único" (LMP del `reference_zone`). Reusa patrón
   `PriceSeriesChart` + `ChartLegend`/`ChartTooltip`/`useChartZoom`; marcador
   vertical de la hora seleccionada.
5. **Despacho nodal + flujos de rama**:
   - `components/nodal/nodal-dispatch-chart.tsx` — stacked area por generador
     por hora (reusa `lib/dispatch-chart-data.ts`).
   - `components/nodal/branch-flows-chart.tsx` — líneas de `flow_mw` por rama
     por hora.
6. **Tabla de diferencial**: `components/nodal/differential-table.tsx` —
   shadcn `Table`: pago de demanda A vs B con delta por zona (de
   `redistribution`), y tabla de ingresos de generación por zona+fuel (de
   `gen_revenue_by_zone`). Delta resaltado emerald/red.
7. **Matriz de redistribución**: `components/nodal/redistribution-matrix.tsx` —
   heatmap divergente (emerald→red, centrado en 0) sobre el `delta` por zona.
8. **Descargas**: reusa el patrón de `ArtifactDownloads` para los 7 artefactos
   nodales (name + descarga vía `downloadNodalArtifact`).

## 6. Layout esquemático determinista

- `lib/nodal-layout.ts`:
  - `computeZoneLayout(zones, branches) -> Record<zone, {x, y}>` — spring-
    embedder determinista (posiciones iniciales en círculo, ~200 iteraciones de
    repulsión/atracción con `alpha` decreciente; sin aleatoriedad → mismo input,
    mismo output). Nodos aislados quedan en la periferia del círculo.
  - `lmpColor(lmp, min, max) -> string` — interpolación lineal de color
    (azul→ámbar) entre min y max de la hora; casos degenerados (min==max)
    devuelven el color neutro.
- Ambas funciones puras y unit-testables (sin DOM).

## 7. i18n, estados y errores

- Strings nuevos vía `t()` en `lib/i18n.ts` (es/en, default es) bajo clave
  `nodal.*` y `sidebar.nodal`. Nombres de zonas/generadores/ramas son datos, no
  se traducen.
- `useQuery` por artefacto con `queryKey: ["nodal-<artifact>", id]` y
  `enabled: Boolean(data?.nodal?.artifacts.<name>)` (mismo patrón del run
  detail). Spinner `Loader2` durante carga; estado vacío con icono si no hay
  datos nodales; errores con `role="alert"` (patrón `/compare`).
- El enlace del run detail a `/runs/[id]/nodal` solo se renderiza cuando
  `data.nodal` existe (corrida `done` nodal).

## 8. Testing

Colocado junto al código (convención vitest existente):

- `lib/nodal-layout.test.ts` — determinismo (mismo input → mismo output),
  grafo de 3 zonas produce 3 nodos conectados; `lmpColor` en rango, mínimo,
  máximo y degenerado.
- `lib/api-client.test.ts` — nuevos `getRunNodalArtifact`/`downloadNodalArtifact`
  con `fetch` stub + mock de `supabase.auth.getSession` (patrón existente).
- `components/nodal/*.test.tsx` — render con `I18nProvider`, assert en español;
  mapa renderiza N nodos y M aristas; charts con el stub de `ResizeObserver`
  existente.
- `app/(app)/nodal/page.test.tsx` — filtra `level === "lmp"`, muestra chips de
  topología, link al dashboard.
- `app/(app)/runs/[id]/nodal/page.test.tsx` — smoke render con datos nodales
  mockeados.

Backend: `tests/test_api_runs.py` — `GET /runs` devuelve `nodal` con
`network_name/zones/generators/branches` para un run nodal y `null` para un run
clásico.

## 9. Fuera de alcance

- Prescient (Fase 4).
- Mapas geográficos reales (requiere lat/lon por zona — no disponible).
- Comparar varias corridas nodales entre sí (`/compare` sigue siendo clásico).
- Editar/enviar redes desde la UI (solo consumo).
- Nueva lógica de negocio en `app/nodal/` (cero cambios salvo el enriquecimiento
  de `GET /runs`).

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| Next.js 16 con breaking changes vs training data | Leer `node_modules/next/dist/docs/` antes de escribir código (regla de `frontend/AGENTS.md`); seguir los patrones de páginas existentes. |
| N+1 en `GET /runs` (1 `get_nodal_result` por fila) | Aceptado por decisión del usuario; escala actual es decenas de runs. |
| SVG del mapa sin layout con muchos nodos | Layout determinista + ancho de la página acotado (`max-w-6xl`); redes grandes se ven a escala, sin pretender ser un visor geo. |
| Artefacto `summary` es JSON, el resto CSV | `getRunNodalArtifact` tipa la rama `summary` aparte (JSON parseado). |
| Corrida nodal sin terminar (pending/running/failed) | Dashboard solo accesible cuando `data.nodal` existe (runs `done`); `/nodal` muestra status pill y enlaza solo a corridas con dashboard. |

## 11. Referencias

- Spec Fase 1: `docs/superpowers/specs/2026-08-18-lmp-nodal-market-design.md`
- Spec Fase 2: `docs/superpowers/specs/2026-08-18-lmp-nodal-api-worker-design.md`
- Plan Fase 1: `docs/superpowers/plans/2026-08-18-lmp-nodal-market.md`
- README del módulo: `docs/superpowers/plans/README-nodal.md`