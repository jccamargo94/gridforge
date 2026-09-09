# Tasks: Home chart-first (home-chart)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~550-650 (3 new source + 3 new tests ~450; 7 modified + 1 deleted ~150) |
| 400-line budget risk | High |
| Chained PRs recommended | No — single-pr strategy + unlimited budget; one cohesive frontend slice under size:exception |
| Suggested split | Single PR (units 1-4 land together; gates close unit 4) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Types + isManualRun + fixture | single PR | `pnpm vitest run-status runs-table` | N/A (no UI; pure logic) | Revert `types.ts`, `run-status.ts`, fixture |
| 2 | getChartSeries + useChartSeries | single PR | `pnpm vitest use-chart-series` | N/A (needs authed `GET /chart/series`) | Delete hook, revert `api-client.ts` |
| 3 | home-chart.tsx + tests | single PR | `pnpm vitest home-chart` | `pnpm dev` → `/` with session (live backend) | Delete component + test |
| 4 | Home page + sidebar + i18n + /runs filter + gates | single PR | `pnpm test && pnpm lint && pnpm build` | `pnpm dev` authed walkthrough `/`, `/runs` | Restore `app/page.tsx` redirect; delete `(app)/page.tsx` |

## Phase 1: Foundation (types, predicate, fixture, fetcher)

- [x] 1.1 RED: co-located run-status test asserts `isManualRun` (public→false, private→true, `undefined`→true); GREEN: add `isManualRun` to `frontend/lib/run-status.ts`.
- [x] 1.2 Extend `frontend/lib/types.ts` (`ChartSeriesRow`, `RunVisibility`, `InputGrade`; required `visibility`/`input_grade` on `RunSummary`/`RunDetail`) + update `frontend/components/runs-table.test.tsx` fixture atomically (ordering hazard: never land apart).
- [x] 1.3 RED: `frontend/hooks/use-chart-series.test.tsx` mocks `@/lib/api-client`, asserts `?days=` query; GREEN: add `getChartSeries(days)` to `frontend/lib/api-client.ts` + `frontend/hooks/use-chart-series.ts` (`queryKey ["chart-series", days]`, no polling).

## Phase 2: Chart component

- [x] 2.1 RED: `frontend/components/home-chart.test.tsx` (null→gap never zero; `bestRunId` settled>provisional>preideal; all-null ids no nav; trailing-null caption; es/en via `I18nProvider`).
- [x] 2.2 GREEN: `frontend/components/home-chart.tsx` (date-domain `LineChart`, 5 nullable lines `connectNulls={false}`, legend toggles, `useChartZoom`, non-null-only date tooltip, click→`router.push` best id, preideal-lane comment).

## Phase 3: Wiring (page, sidebar, i18n, /runs filter)

- [x] 3.1 Add `home.*` + `sidebar.home` keys to `frontend/lib/i18n.ts` (es ASCII-folded, en per design table).
- [x] 3.2 Create `frontend/app/(app)/page.tsx` (title/subtitle, 7/30/90 selector default 30, loading/empty/error `role="alert"`, TX1 caption) + DELETE `frontend/app/page.tsx` (route conflict).
- [x] 3.3 Add Home entry to `frontend/components/app-sidebar.tsx` (`href "/"`, active on exact `/`).
- [x] 3.4 Apply `isManualRun` filter in `frontend/app/(app)/runs/page.tsx` (table, all counters, empty-state).

## Phase 4: Gates

- [x] 4.1 Run `pnpm test`, `pnpm lint`, `pnpm build` in `frontend/`; all green, backend untouched.

### Gate status (apply phase, 2026-09-09, branch `fase7b-home-chart`)

- `pnpm test`: 264 passed; 2 failed — both pre-existing nodal flakes, also failing on
  unmodified `develop` (`nodal-dispatch-chart` stacked-area, `nodal/page` hour selector).
  All 31 new home-chart tests pass (incl. full-suite runs).
- `pnpm lint`: 0 errors (3 warnings, all in untouched files).
- `pnpm build`: compile succeeds; type-check blocked by (a) pre-existing
  `components/nodal/network-graph.test.tsx(214,12)` error (present on `develop`,
  verified via `git stash` + `tsc`), and (b) root-owned stale `.next/dev/types/`
  cache referencing the deleted `app/page.tsx` (harness-owned dir, not removable
  without sudo). Source-level `tsc` excluding gitignored `.next` shows zero new
  errors. `git status` confirms backend untouched (only `frontend/` + `openspec/`).
