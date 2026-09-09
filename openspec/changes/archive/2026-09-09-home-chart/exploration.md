## Exploration: Home con grafica continua (issue #90, frontend-only)

### Current State

Backend (#89) is live on `develop`: `GET /chart/series?days=N` (default 30,
clamped 1..90, auth = any logged-in user, `today` in America/Bogota) returns
one row per calendar day with daily-mean COP/MWh series plus drill-down ids.
Verified against `services/api/chart.py`, `services/api/main.py:310-321` and
`tests/test_api_chart.py` (exact 9-key shape asserted):

- `date`, `bolsa_tx1`, `mpo_xm` (externals; `null` when unpublished),
  `ideal_settled` + `ideal_settled_run_id`,
  `ideal_provisional` + `ideal_provisional_run_id`,
  `preideal` + `preideal_run_id`.
- Precedence is server-side and asymmetric: ideal reports BOTH lanes
  separately, but preideal is a SINGLE merged lane (settled wins, provisional
  `run_id` unreachable once settled exists).
- Fixture ground truth: `bolsa_tx1 = 200000.0` (raw 200 COP/kWh x1e3),
  `mpo_xm = 150000.0` (iMAR).

Frontend today (`frontend/`): `/` redirects to `/runs` (`app/page.tsx`);
sidebar has Runs / Scenarios / Compare / Nodal (`app-sidebar.tsx`, hidden
below `md` with NO mobile nav). `/runs` page = stats cards + CreateRunForm +
RunsTable, all via `useT` i18n (default `es`, localStorage `gridforge-lang`).
`lib/api-client.ts` has NO chart fetcher; every request needs a Supabase
bearer token. `lib/types.ts` `RunSummary`/`RunDetail` have NO
`visibility`/`input_grade` (stale vs backend `_run_summary`, which sends both).
Reusable for drill-down with zero new detail work: `/runs/[id]` page
(MetricCards, DispatchChart, PriceSeriesChart, MarginalPlantsTable,
ArtifactDownloads, LogViewer) plus `RunComparisonTable`
(RMSE/MAE/Bias/WAPE/sMAPE/R2/BESS). `PriceSeriesChart` itself is NOT directly
reusable for Home: its X domain is intraday hour (0-23, 2 series), while Home
needs a date domain with 5 nullable series — only its patterns transfer
(`useChartZoom`, `ChartLegend` toggle, `ChartTooltip`, `formatNumber`,
empty-state `chart.pricesNoData`).

### Affected Areas

- `frontend/app/page.tsx` — remove redirect; Home lives here (`/` = chart-first landing).
- `frontend/components/app-sidebar.tsx` — new Home nav entry (`sidebar.home` key); mobile has no nav at all (flag, may stay out of scope).
- `frontend/lib/api-client.ts` — add `getChartSeries(days)` reusing `request()` + `NEXT_PUBLIC_API_BASE_URL`.
- `frontend/lib/types.ts` — add `ChartSeriesRow`; add `visibility`/`input_grade` to `RunSummary`/`RunDetail` (needed to keep `/runs` manual-only, see Risks).
- `frontend/lib/i18n.ts` — new `home.*` keys in BOTH `es` and `en` (existing es copy is ASCII-folded, no tildes — match it).
- `frontend/app/(app)/runs/page.tsx` — filter out public daily runs (backend `list_visible_runs` returns them; without a filter the closed "manual-only" decision breaks).
- New (proposed, not created): `frontend/components/home-chart.tsx` + `frontend/hooks/use-chart-series.ts` + co-located vitest files following `price-series-chart.test.tsx` patterns.

### Approaches

1. **Composite multi-date series** — one recharts `LineChart`, X = `date`,
   5 lines (bolsa_tx1, mpo_xm, ideal_settled, ideal_provisional, preideal),
   `connectNulls={false}` so unpublished days render as gaps; click
   dot/day navigates to the day's best `*_run_id` (`/runs/[id]` reuse);
   `?days=` selector (7/30/90, default 30); legend toggles + zoom copied
   from `PriceSeriesChart` patterns.
   - Pros: directly implements the closed chart-first decision; one
     authenticated query; drill-down is a plain link to existing detail.
   - Cons: new date-domain chart component (hourly one not reusable as-is);
     tooltip must explain trailing nulls.
   - Effort: Low/Medium

2. **Widget-per-day / cards with mini-charts** — a list of day cards, each
   with its own sparkline and per-run links.
   - Pros: none decisive; day cards read well on narrow screens.
   - Cons: contradicts the closed chart-first decision (a runs list by
     another name); O(days) rendering cost; continuity/trend comparison
     lost; more new code than option 1.
   - Effort: Medium (and wrong direction)

3. **Periodicity variants** — (a) daily means exactly as the contract serves
   (v1); (b) hourly overlay across days; (c) weekly aggregation.
   - Pros of (a): zero backend work, matches `GET /chart/series` v1; hourly
     detail already exists one click away in `/runs/[id]`.
   - Cons of (b)/(c): need new aggregation (backend or client), outside
     frontend-only scope; LMP explicitly deferred.
   - Effort: (a) included in option 1; (b)/(c) Medium/High — defer.

Fine-question resolutions (options considered, recommendation first):
- Default window: **30d** (backend default) + selector 7/30/90 (cap 90
  enforced server-side, 422 beyond).
- Today with unpublished TX1: render **gap (`null`), never zero**; tooltip/
  caption explains the 2-4 day TX1 lag is normal.
- Copy: follow existing app language (default `es`); verbatim proposals:
  title `"Precios del mercado"`, subtitle `"Bolsa real, MPO de XM y
  simulaciones del modelo por dia"`, series `"Bolsa real (TX1)"`,
  `"MPO XM (iMAR)"`, `"Ideal liquidado"`, `"Ideal provisional"`,
  `"Preideal"`; loading `"Cargando serie..."`, empty
  `"Sin datos de serie todavia."`, error `"No se pudo cargar la serie."`.
- Loading/empty/error: copy `/runs` + `/compare` patterns (Loader2 +
  muted text; Zap-icon empty state; `role="alert"` error box).
- Responsive: `ResponsiveContainer` + horizontal scroll fallback; legend
  wraps (existing `ChartLegend` already `flex-wrap`).
- Placement: **`/` becomes Home** (redirect removed), **`/runs` stays** as
  the manual-runs tab + sidebar gains Home. A separate `/home` route adds
  a redirect rule for zero benefit.
- Drill-down: **reuse, no new view** — click day → `router.push` to best
  available `*_run_id` (ideal: settled first; preideal: the single merged
  id). `RunComparisonTable` reuse across a day's 3 runs is a possible
  fast-follow, not v1.

### Recommendation

Option 1 (composite multi-date series, daily means, `/` = Home, drill-down
by deep-link into existing `/runs/[id]`) with the fine resolutions above.
It is the smallest change satisfying all four closed decisions, reuses the
live contract verbatim, and adds zero backend, zero new detail views, and
zero new charting dependencies (recharts already pinned).

### Risks

- `/runs` pollution: `GET /runs` returns public daily runs
  (`list_visible_runs`: own OR public). Without a client-side
  `visibility`/`input_grade` filter, the closed manual-only decision
  breaks on day one. (Requires the `types.ts` update above.)
- Preideal lane merge: only ONE `preideal_run_id` per day is exposed; the
  provisional preideal run becomes unreachable from the chart once settled
  lands. Accept for v1 (frontend-only scope cannot change it); spec MUST
  document it.
- Trailing nulls are NORMAL (TX1 lag 2-4d, monthly settled gate): chart
  must gap, tooltip must say so, empty-state copy must not cry wolf when
  only the tail is null vs the whole window.
- Mobile: sidebar is `hidden md:flex` with no bottom nav — Home content
  works, but in-app navigation on phones is already broken repo-wide;
  decide in proposal whether #90 fixes it or explicitly excludes it.
- Auth wall: chart endpoint needs a logged-in user; public runs are NOT
  anonymously visible. Confirm that matches product expectation (no
  change needed if yes).
- `PriceSeriesChart` looks reusable but is not (hour domain, non-nullable
  pairs); spec must forbid "just reuse it" shortcuts that would corrupt
  the date domain.

### Ready for Proposal

Yes. Orchestrator should tell the user: exploration confirms the backend
contract is sufficient as-is (no #89 follow-up needed), recommends
composite daily chart at `/` with deep-link drill-down, and flags two
spec-must-cover items — the `/runs` public-run filter and the preideal
single-lane asymmetry — plus a scope call on mobile nav. Next: sdd-propose
for `home-chart` (Spanish spec downstream, English plan downstream).
