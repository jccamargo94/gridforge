# Design: Home chart-first (home-chart)

## Technical Approach

Frontend-only (issue #90). Home renders at `/` from a new `frontend/app/(app)/page.tsx`
inside the existing `RequireAuth` + `AppSidebar` shell; the root `frontend/app/page.tsx`
redirect is deleted (two `page.tsx` files resolving to `/` is a Next.js route conflict).
A composite recharts `LineChart` (X = `date`, 5 nullable lines, `connectNulls={false}`)
is fed by one TanStack query per 7/30/90 selection through `request()` + Supabase
bearer token. `PriceSeriesChart` patterns are copied, never the component. Covers every
spec requirement; answers the proposal approach verbatim.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Home in root `app/page.tsx` vs `app/(app)/page.tsx` + delete root | Root lacks `RequireAuth`/sidebar shell (chart API needs bearer auth); duplicating the shell wastes code. `(app)` group maps to `/` with shell free, but coexisting root page conflicts | Create `(app)/page.tsx`, **delete** `app/page.tsx` |
| Reuse `PriceSeriesChart` vs new `home-chart.tsx` | **Reuse forbidden:** its domain is intraday hour (0–23, 2 non-nullable series, `hourOfDay()` coercion). Forcing nullable date rows through it corrupts axis, tooltip, and zoom math | New component; copy only `useChartZoom`, `ChartLegend`, `ChartTooltip` styling, `formatNumber`, empty-state |
| Manual-only predicate on `visibility` vs `input_grade` | `input_grade=null` coincides with manual runs today, but grades are lane metadata; `visibility` is the authoritative gate matching `list_visible_runs` (`user_id==me OR public`) and `_get_authorized_run` | `isManualRun(r) = r.visibility !== "public"` in `lib/run-status.ts`; type `input_grade`, exclude from predicate (tolerant of `undefined` in stale fixtures) |
| Required vs optional `visibility`/`input_grade` on `RunSummary` | Optional hides contract drift; backend `_run_summary` always sends both | Required; update the `runs-table.test.tsx` fixture |
| Poll vs fetch-once for series | `useRunDetail` polls because runs transition; daily chart rows are static intraday | No `refetchInterval`; `queryKey ["chart-series", days]` refetches per selection |

## Data Flow

```text
(app)/page.tsx --days--> useChartSeries(days) --> getChartSeries(days)
                       TanStack ["chart-series", days]      |
                       request() + Supabase bearer          v
                                            GET /chart/series?days=N
                       ChartSeriesRow[] <-- response
(app)/page.tsx <--rows--> home-chart.tsx --click--> router.push(/runs/[bestId])
/runs page: listRuns() --> isManualRun filter --> RunsTable + counters
```

## File Changes

| File | Action | Description |
|---|---|---|
| `frontend/app/(app)/page.tsx` | Create | Home route: title/subtitle, 7/30/90 selector (default 30), hook wiring, loading/empty/error, TX1 caption |
| `frontend/app/page.tsx` | Delete | `/runs` redirect; route-conflicts with `(app)/page.tsx` |
| `frontend/components/home-chart.tsx` | Create | Date-domain chart: 5 lines `connectNulls={false}`, legend toggles, `useChartZoom`, date tooltip, click drill-down |
| `frontend/hooks/use-chart-series.ts` | Create | `useQuery(["chart-series", days], () => getChartSeries(days))` |
| `frontend/lib/api-client.ts` | Modify | `getChartSeries(days)` via `request()` |
| `frontend/lib/types.ts` | Modify | `ChartSeriesRow`, `RunVisibility`, `InputGrade`; extend `RunSummary`/`RunDetail` |
| `frontend/lib/run-status.ts` | Modify | `isManualRun` predicate next to `isTerminalStatus` |
| `frontend/lib/i18n.ts` | Modify | `home.*` + `sidebar.home` keys es/en |
| `frontend/app/(app)/runs/page.tsx` | Modify | `isManualRun` filter on table, all counters, empty-state |
| `frontend/components/app-sidebar.tsx` | Modify | Home entry (`href "/"`, active on exact `/`) |
| `home-chart.test.tsx`, `use-chart-series.test.tsx`, `run-status` filter test | Create | Vitest co-located, existing patterns |
| `frontend/components/runs-table.test.tsx` | Modify | Add `visibility`/`input_grade` to fixture |

## Interfaces / Contracts

```ts
// types.ts — mirrors GET /chart/series 9-key shape (test_api_chart.py)
export interface ChartSeriesRow {
  date: string; bolsa_tx1: number | null; mpo_xm: number | null;
  ideal_settled: number | null; ideal_settled_run_id: string | null;
  ideal_provisional: number | null; ideal_provisional_run_id: string | null;
  preideal: number | null; preideal_run_id: string | null;
}
export type RunVisibility = "private" | "public";
export type InputGrade = "settled" | "provisional" | null;
// api-client.ts
export function getChartSeries(days: number): Promise<ChartSeriesRow[]> {
  return request<ChartSeriesRow[]>(`/chart/series?days=${days}`);
}
// drill-down priority ideal_settled > ideal_provisional > preideal; null = no nav
export function bestRunId(r: ChartSeriesRow): string | null {
  return r.ideal_settled_run_id ?? r.ideal_provisional_run_id ?? r.preideal_run_id ?? null;
}
```

Gap/tooltip: `null` values pass through untouched (never `?? 0`); tooltip lists only
non-null series + date, notes trailing-null lag; empty state only when all 5 series are
null across the whole window. Preideal asymmetry documented in code comment: single
merged lane server-side (`chart.py _SERIES_KEYS`: settled hit wins, provisional id
unreachable once settled exists).

## i18n Keys (`home.*`, es ASCII-folded, no tildes)

| Key | es | en |
|---|---|---|
| `home.title` | Precios del mercado | Market prices |
| `home.subtitle` | Bolsa real, MPO de XM y simulaciones del modelo por dia | Real bolsa, XM MPO and model simulations per day |
| `home.tx1` / `home.mpo` / `home.idealSettled` / `home.idealProv` / `home.preideal` | Bolsa real (TX1) / MPO XM (iMAR) / Ideal liquidado / Ideal provisional / Preideal | Real bolsa (TX1) / XM MPO (iMAR) / Settled ideal / Provisional ideal / Preideal |
| `home.loading` / `home.empty` / `home.error` / `home.tx1Lag` | Cargando serie... / Sin datos de serie todavia. / No se pudo cargar la serie. / TX1 publica con 2-4 dias de retraso. | Loading series... / No series data yet. / Could not load the series. / TX1 publishes with a 2-4 day lag. |
| `sidebar.home` | Inicio | Home |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (vitest) | `bestRunId` priority + null; `isManualRun` (public/settled filtered, private kept, `undefined` kept); gap rendering (null → gap, never zero); trailing-null caption; priority click → `router.push`; locale switch es/en | Co-located `home-chart.test.tsx` (render + `userEvent` + `I18nProvider`, per `price-series-chart.test.tsx`); hook test mocks `@/lib/api-client` + asserts `?days=` query (per `use-run-log.test.tsx`) |
| Integration | Selector 7→30→90 refetches once each; `/runs` excludes public daily rows from table AND counters | `QueryClientProvider retry:false`; mixed-visibility list render |
| Gates | `pnpm lint` (eslint), `pnpm build` (tsc + Next), `pnpm test` | Strict TDD; no coverage tooling → no coverage gate; backend untouched (pytest optional sanity) |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary (`router.push` to an internal route is
standard Next.js navigation).

## Migration / Rollout

No migration required (frontend-only, no backend/contract change). Rollback: restore
`app/page.tsx` redirect, delete `(app)/page.tsx` and new files.

## Open Questions

None blocking. Minor: `staleTime` default acceptable (daily static data); sidebar Home
icon follows existing lucide set at implementation time.
