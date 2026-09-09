# Apply progress: Home chart-first (home-chart)

Branch: `fase7b-home-chart` (off `develop` @ `03b63fbc3`). Mode: Strict TDD.
Delivery: maintainer-approved `size:exception`, single PR (units 1-4 together).
Backend: untouched (`git status` shows only `frontend/` + `openspec/`).

## Commits (work units)

| Unit | SHA | Message | Tasks |
|------|-----|---------|-------|
| 1 | `7cd14b072` | feat(home-chart): add ChartSeriesRow types and isManualRun predicate | 1.1, 1.2 |
| 2 | `a39ce5003` | feat(home-chart): add getChartSeries fetcher and useChartSeries hook | 1.3 |
| 3 | `16b349933` | feat(home-chart): add HomeChart with drill-down and home i18n keys | 2.1, 2.2, 3.1 (pulled forward) |
| 4 | `32d16b0df` | feat(home-chart): wire Home page, sidebar entry, and manual-only runs filter | 3.2, 3.3, 3.4 (+ test hardening) |
| 4b | `37c4270b1` | feat(home-chart): delete root redirect conflicting with Home route | 3.2 (deletion staged separately — explicit `git add` paths missed it) |

## Task status

- [x] 1.1 `isManualRun` in `frontend/lib/run-status.ts` (+ `run-status.test.ts`)
- [x] 1.2 `ChartSeriesRow`/`RunVisibility`/`InputGrade` in `frontend/lib/types.ts`
  (required `visibility`/`input_grade` on `RunSummary`/`RunDetail`); fixtures updated
  atomically in `runs-table.test.tsx` (+ 5 sibling fixtures required for `tsc`:
  `run-selector`, `run-comparison-table`, `types.test`, `runs/[id]/page.test`,
  `runs/[id]/nodal/page.test`, `(app)/nodal/page.test`)
- [x] 1.3 `getChartSeries(days)` in `api-client.ts` + `use-chart-series.ts`
  (`queryKey ["chart-series", days]`, no polling) + both test files
- [x] 2.1 `home-chart.test.tsx`: 15 tests (bestRunId x3, handleChartClick x3,
  5 lines, gap, continuous-path companion, empty, trailing-null caption,
  legend toggle, en locale, tooltip x2)
- [x] 2.2 `home-chart.tsx`: date-domain `LineChart`, 5 nullable lines
  `connectNulls={false}`, legend toggles, `useChartZoom`, non-null-only date
  tooltip, click drill-down, preideal-lane comment
- [x] 3.1 `home.*` + `sidebar.home` keys es/en (ASCII-folded es) + `home.retry`
  (addition: spec requires error retry affordance, no key existed)
- [x] 3.2 `frontend/app/(app)/page.tsx` (title/subtitle, 7/30/90 default 30,
  loading/empty/error `role="alert"` + retry) + `page.test.tsx` (4 tests);
  DELETED `frontend/app/page.tsx` (route conflict)
- [x] 3.3 Home entry in `app-sidebar.tsx` (`House` icon, active on exact `/`)
  + 2 tests (link, active/inactive triangulation)
- [x] 3.4 `isManualRun` filter in `(app)/runs/page.tsx` (table, all counters,
  empty-state) + `page.test.tsx` (3 tests)
- [x] 4.1 gates — see Gate status in `tasks.md`

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `lib/run-status.test.ts` | Unit | 49/49 pass | 3 fail, import missing | 8/8 pass | 3 cases (public/private/undefined) | none needed (pure 1-liner) |
| 1.2 | fixtures + `tsc` | Structural | 49/49 pass | N/A structural | tsc: no new errors | skipped (single shape; verified by tsc + 23 fixture tests) | none |
| 1.3 | `hooks/use-chart-series.test.tsx`, `lib/api-client.test.ts` | Unit | 49/49 pass | module missing + not-a-function | 18/18 pass | 2+2 cases (days 30/7, refetch on change) | none needed |
| 2.1/2.2 | `components/home-chart.test.tsx` | Unit | 49/49 pass | import fails | 15/15 pass | bestRunId x3, click x3, gap + continuous companion, tooltip x2, legend, locales | type-predicate refactor, tests still green |
| 3.1 | `home-chart.test.tsx` (pre-written) | Unit | — | 4 fail (missing keys) | 12/12 pass | es + en cases | none |
| 3.2 | `app/(app)/page.test.tsx` | Unit (mocked hook) | 49/49 pass | import fails | 4/4 pass | title/default-30, window change, loading, error+retry | none needed |
| 3.3 | `components/app-sidebar.test.tsx` | Unit | 49/49 pass | 2 fail (no Home link) | 8/8 pass | active on `/` + inactive on `/runs` | none needed |
| 3.4 | `app/(app)/runs/page.test.tsx` | Unit (mocked api) | 49/49 pass | 3 fail (public leaks) | 3/3 pass | table + all counters + empty-state | none needed |

Test summary: 31 new tests written, all passing. Layers: Unit (31).
Approval tests: none — no refactoring tasks. Pure functions created: 3
(`isManualRun`, `bestRunId`, `handleChartClick`).

## Work Unit Evidence

| Unit | Focused test command + result | Runtime harness + result | Rollback boundary |
|------|-------------------------------|--------------------------|-------------------|
| 1 | `pnpm vitest run lib/run-status.test.ts ...` 23/23 pass; `tsc` no new errors | N/A (no UI; pure logic + types) | Revert `types.ts`, `run-status.ts`, 7 fixtures |
| 2 | `pnpm vitest run hooks/use-chart-series.test.tsx lib/api-client.test.ts` 18/18 pass | N/A (needs authed `GET /chart/series`) | Delete hook files, revert `api-client.ts` |
| 3 | `pnpm vitest run components/home-chart.test.tsx` 15/15 pass; `eslint` clean | N/A (needs authed session + live backend) | Delete component + test; revert `i18n.ts` |
| 4 | `pnpm vitest run app-sidebar + runs/page + (app)/page` 15/15 pass; `pnpm lint` 0 errors; `pnpm test` 264 pass / 2 pre-existing nodal flakes | `pnpm dev` authed walkthrough `/`, `/runs` — NOT run (no live session in this env; left for verify) | Restore `app/page.tsx` redirect; delete `(app)/page.tsx` + 2 page tests; revert sidebar/runs-page |

## Deviations from design

1. Task 3.1 (`home.*` keys) landed in unit-3 commit instead of unit 4: the
   chart RED tests assert translated strings, so GREEN was impossible without
   the keys. Same content, earlier commit — no design change.
2. Fixture updates beyond `runs-table.test.tsx` (5 sibling files): required for
   `tsc`/`next build` once `visibility`/`input_grade` became required. Minimal
   additions only (`visibility: "private"`, `input_grade: null`).
3. Added `home.retry` i18n key ("Reintentar"/"Retry"): spec scenario requires an
   error retry affordance but the key table had no entry for it.
4. Added two page-level test files not named in design (`(app)/page.test.tsx`,
   `(app)/runs/page.test.tsx` — the latter is the design's "run-status filter
   test"): required by Strict TDD (no task completes without a RED test).
5. `handleChartClick(rows, activeLabel, push)` exported pure click resolver
   (component wires recharts `onClick` state into it): recharts click state is
   not drivable in jsdom, so the exact function the chart calls is unit-tested
   directly instead.
6. `waitFor`/`findBy` around recharts-DOM assertions: full-parallel suite runs
   flake on synchronous recharts queries (same signature as the pre-existing
   nodal flakes); async polling keeps the tests deterministic under load.

## Issues found

- Pre-existing (develop, untouched): `pnpm test` nodal flakes (2-3, vary per run);
  `tsc` error `network-graph.test.tsx(214,12)` (breaks `next build` type-check on
  develop too); reported, not fixed (out of scope).
- Environmental: root-owned `.next/dev/types` (orphaned root build worker) holds a
  stale `validator.ts` referencing deleted `app/page.tsx`; not removable without
  sudo. `next build` compile passes; source `tsc` (excl. gitignored `.next`) is clean.

## Status

11/11 tasks complete. Ready for verify. PR NOT opened, branch NOT pushed
(verify phase + orchestrator own delivery).
