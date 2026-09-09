# Proposal: Home chart-first (issue #90, frontend-only)

## Intent

`/` redirects to `/runs` today — a manual-run list, no market overview. Users need a chart-first Home: continuous daily prices (real bolsa TX1, XM MPO, model ideal settled/provisional + preideal) with per-day drill-down into existing run detail. Backend `GET /chart/series` is live on develop; this change is frontend-only.

## Scope

### In Scope
- `/` becomes Home (redirect removed); `/runs` stays, filtered to manual-only via `visibility`/`input_grade`
- New `frontend/components/home-chart.tsx` + `frontend/hooks/use-chart-series.ts`; `ChartSeriesRow` + visibility/input_grade types
- `home.*` i18n keys (es/en; es ASCII-folded, no tildes); 7/30/90 selector, default 30
- `connectNulls={false}` gaps + TX1-lag caption; drill-down to best `*_run_id` via existing `/runs/[id]`

### Out of Scope
- LMP series, hourly overlay, weekly aggregation, new detail views
- Mobile bottom nav (exclude unless explicitly scoped); anonymous public access; any backend change

## Capabilities

### New Capabilities
- `home-chart`: chart-first Home at `/`, series selector, gap rendering, drill-down links, manual-only `/runs` filter

### Modified Capabilities
- None (no existing specs in `openspec/specs/`; backend contract unchanged)

## Approach

Composite recharts `LineChart` with date domain, 5 nullable lines from one authenticated `getChartSeries(days)` query. Reuse `PriceSeriesChart` patterns only (legend toggle, zoom, tooltip, empty state) — not the component (hour domain). Drill-down is `router.push` to best id (ideal settled first; preideal single merged id). Gaps render as `null`, never zero.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/app/page.tsx` | Modified | Remove redirect; render Home |
| `frontend/components/home-chart.tsx` | New | Date-domain chart + selector + caption |
| `frontend/hooks/use-chart-series.ts` | New | Fetcher hook for `GET /chart/series` |
| `frontend/lib/api-client.ts` | Modified | Add `getChartSeries(days)` |
| `frontend/lib/types.ts` | Modified | `ChartSeriesRow`; visibility/input_grade on run types |
| `frontend/lib/i18n.ts` | Modified | `home.*` keys es/en |
| `frontend/app/(app)/runs/page.tsx` | Modified | Filter out public daily runs |
| `frontend/components/app-sidebar.tsx` | Modified | Home nav entry |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `/runs` pollution breaks manual-only rule | High | Client filter on visibility/input_grade; spec covers it |
| Preideal single-lane asymmetry confuses users | Med | Document: settled wins, provisional id unreachable |
| Trailing nulls read as breakage | Med | Gap rendering + TX1-lag caption + tooltip note |
| Auth wall surprises (no anonymous access) | Low | Confirm expectation; no code change |
| Mobile nav already broken repo-wide | Low | Explicit non-goal unless scoped |

## Rollback Plan

Revert frontend files to restore `/` → `/runs` redirect. No migration, no backend change — zero data rollback.

## Dependencies

- Live `GET /chart/series` on develop (no #89 follow-up); Supabase bearer auth; pinned recharts.

## Success Criteria

- [ ] `/` shows 5-series daily chart with 7/30/90 selector (default 30), gaps for unpublished days
- [ ] Day click lands on that day's best `*_run_id` detail; `/runs` shows manual runs only
- [ ] es/en copy renders; strict TDD gates green (vitest + eslint + build)

## Proposal question round

Execution is non-interactive; lock these assumptions before spec:
1. Placement: `/` becomes Home, no separate `/home` route — confirmed?
2. Copy verbatim from explore (`"Precios del mercado"`, `"Bolsa real (TX1)"`, `"Ideal liquidado"`, `"Cargando serie..."`, `"Sin datos de serie todavia."`, `"No se pudo cargar la serie."`) — approved as-is?
3. Loading/empty/error follow `/runs` + `/compare` patterns; mobile bottom nav stays out of scope — agreed?
