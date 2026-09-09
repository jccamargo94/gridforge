```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:9b6d391152c013c6410fab6ef18daa572a47a9af16d963eb1337ad5b5a0da98c
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 12/12
test_command: pnpm vitest run lib/run-status.test.ts hooks/use-chart-series.test.tsx components/home-chart.test.tsx app/(app)/page.test.tsx app/(app)/runs/page.test.tsx lib/api-client.test.ts components/app-sidebar.test.tsx
test_exit_code: 0
test_output_hash: sha256:674df2804c898db991684736f753f0215e35302327e12f2a9e0c825a6d054da7
build_command: pnpm lint
build_exit_code: 0
build_output_hash: sha256:4edf218208ca7a4b570f60187dcc53e9b10f74c0cb63b91823350e95e74753d2
```

## Verification Report

**Change**: home-chart (issue #90, Home chart-first frontend)
**Version**: N/A (spec has no version field)
**Mode**: Strict TDD
**Branch**: `fase7b-home-chart` off develop @03b63fbc3, HEAD 65abbcc5f. Backend untouched.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 11 |
| Tasks complete | 11 |
| Tasks incomplete | 0 |

All 11 tasks `[x]` in `openspec/changes/home-chart/tasks.md` (Phases 1-4). No pending task blocks verification.

### Build & Tests Execution

**Gate scoping note (read before the envelope):** the envelope's `test_command`
is the change-scoped suite (all 7 test files this change creates or touches:
56/56 pass, exit 0) and its `build_command` is the lint gate (exit 0). The
full gates (`pnpm test`, `npx tsc --noEmit`) are disclosed verbatim below with
their own exit codes and output hashes: each exits non-zero SOLELY because of
one proven pre-existing issue that fails identically on unmodified
`origin/develop` (session preflight: known pre-existing, must not fail
verify). Nothing is hidden; the WARNINGS in the verdict point exactly here.

- Full-suite output hash: `sha256:14369400296ae77b1bc2874269a89d90af66580aa7bd6b81088daf3eed5a7bd5` (`pnpm test`, exit 1, two consecutive runs identical)
- Full type-check output hash: `sha256:38377f045e4adecb9a56d52d59812a6bfbd9edd74dc35cf52b981dc7dec92ab8` (`npx tsc --noEmit`, exit 1, single-line output below)

**Build** (`npx tsc --noEmit` in `frontend/`): exit 1 caused ONLY by one pre-existing error in an untouched file; zero errors in any changed file.

```text
components/nodal/network-graph.test.tsx(214,12): error TS18048: 'pill.data.displayName' is possibly 'undefined'.
```

Pre-existing proof: `git diff origin/develop...HEAD -- frontend/components/nodal/` is empty (file untouched); error matches the apply-phase record of develop.

**Lint** (`pnpm lint` in `frontend/`): 0 errors, 2 warnings, both in untouched files (`components/ui/data-table.tsx` react-hooks/incompatible-library, `lib/auth-context.test.tsx` unused `expect`).

**Tests**: focused new-code run 56/56 pass across 7 files; full suite 265 pass / 1 fail out of 266.

```text
$ pnpm test  (frontend/, 2026-09-09, two consecutive full-suite runs, identical result)
 Test Files  1 failed | 50 passed (51)
      Tests  1 failed | 265 passed (266)
 FAIL  app/(app)/runs/[id]/nodal/page.test.tsx > Nodal dashboard page > changes the selected hour via the selector
 Error: Test timed out in 5000ms. (took 7569ms / 7865ms under full-parallel load)
```

The single failure is the documented pre-existing nodal flake, proven NOT a regression:

1. Same file passes 6/6 in isolation on this branch AND on unmodified `origin/develop` (clean worktree + symlinked node_modules, vitest run directly).
2. The branch diff to that file is fixture-only (`visibility: "private", input_grade: null`, required by the new `RunSummary` shape) — logically unrelated to the hour-selector timeout.
3. Failure signature (timeout only under full-parallel load) matches the apply-phase record of 2-3 varying nodal flakes on develop.

**Coverage**: ➖ Not available — no coverage tooling in this repo (design explicitly states no coverage gate).

### Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Home chart-first en `/` | Visita autenticada a `/` | `app/(app)/page.test.tsx` > renders title + default 30-day window; `app-sidebar.test.tsx` > Home nav item links `/` | ✅ COMPLIANT |
| Home chart-first en `/` | `/runs` sigue accesible | `app/(app)/runs/page.test.tsx` > shows only manual runs in table | ✅ COMPLIANT |
| Serie 5 lineas nulables | Dia sin TX1 publicado | `home-chart.test.tsx` > gaps for null instead of zero (multi-segment path check) | ✅ COMPLIANT |
| Serie 5 lineas nulables | Cola con nulos (lag normal) | `home-chart.test.tsx` > partial chart plus caption when trailing days null | ✅ COMPLIANT |
| Selector 7/30/90 | Carga inicial | `page.test.tsx` > default 30 (`useChartSeries` called with 30, `aria-pressed`); `use-chart-series.test.tsx` > fetches requested window | ✅ COMPLIANT |
| Selector 7/30/90 | Cambio de ventana | `page.test.tsx` > refetches on selector change; `use-chart-series.test.tsx` > refetches on days change; `api-client.test.ts` > `?days=7` / `?days=30` query assert | ✅ COMPLIANT |
| Estados + aviso TX1 | Ventana totalmente vacia | `home-chart.test.tsx` > empty state only when whole window null (Zap + `home.empty`) | ✅ COMPLIANT |
| Estados + aviso TX1 | Fallo de red | `page.test.tsx` > alert with retry (`role="alert"`, `home.error`, refetch on `home.retry`) | ✅ COMPLIANT |
| Drill-down mejor run | Dia con ideal liquidado | `home-chart.test.tsx` > bestRunId prefers settled; handleChartClick navigates `/runs/run-settled` | ✅ COMPLIANT |
| Drill-down mejor run | Dia sin runs | `home-chart.test.tsx` > bestRunId null; handleChartClick no-nav on null ids and on undefined label | ✅ COMPLIANT |
| `/runs` solo manuales | Lista mixta | `runs/page.test.tsx` > table excludes public daily; stats count only manual (`["1","0","0","1","0"]`); empty state when all public | ✅ COMPLIANT |
| i18n home.\* es+en | Cambio de idioma | `home-chart.test.tsx` > English copy with `gridforge-lang=en` (all other tests assert ASCII-folded es defaults) | ✅ COMPLIANT |

**Compliance summary**: 12/12 scenarios compliant. Every scenario has a covering test that passed at runtime (focused run 56/56; full suite 265/266 with the only failure in an unrelated pre-existing nodal file).

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Home chart-first en `/` | ✅ Implemented | `(app)/page.tsx` (title/subtitle, 7/30/90 default 30, loading/empty/error `role="alert"` + retry); root `app/page.tsx` deleted (verified absent); sidebar Home `href "/"` active only on exact `/` |
| Serie 5 lineas, gaps | ✅ Implemented | `home-chart.tsx`: 5 `Line` with `connectNulls={false}` on date domain; nulls pass through untouched (no `?? 0`); empty only when all 5 series null across window (`isEmptyWindow`) |
| Selector 7/30/90 | ✅ Implemented | `WINDOWS=[7,30,90]`, `useState(30)`, `queryKey ["chart-series", days]`, no `refetchInterval` |
| Estados + TX1 caption | ✅ Implemented | `home.loading` / `home.empty` (Zap) / `home.error` + retry / permanent `home.tx1Lag` caption |
| Drill-down prioridad | ✅ Implemented | `bestRunId` = settled ?? provisional ?? preideal ?? null; `handleChartClick` no-nav on null; preideal single-lane asymmetry documented in code comment |
| `/runs` manual-only | ✅ Implemented | `(runs/page.tsx`: `(runsQuery.data ?? []).filter(isManualRun)` applied to table AND all 5 counters AND empty-state; `isManualRun = visibility !== "public"`, tolerant of `undefined` |
| i18n 12+1 keys es+en | ✅ Implemented | All spec key values verified byte-identical in `lib/i18n.ts` es+en (ASCII-folded es, no tildes); plus documented `home.retry` addition |
| Backend untouched | ✅ Confirmed | `git diff origin/develop...HEAD -- services/ app/ tests/` empty; `git status` clean outside `frontend/` + `openspec/` + orchestrator-owned `.atl`/handoff files |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| `(app)/page.tsx` + delete root `app/page.tsx` | ✅ Yes | Route conflict resolved as designed |
| New `home-chart.tsx`, no `PriceSeriesChart` reuse | ✅ Yes | Only patterns copied (`useChartZoom`, `ChartLegend`, `formatNumber`, empty-state) |
| `isManualRun` on `visibility`, type `input_grade` | ✅ Yes | Predicate `!== "public"`; `RunSummary`/`RunDetail` carry required `visibility` + `input_grade` |
| `ChartSeriesRow` 9-key backend mirror | ✅ Yes | date + 5 nullable values + 3 nullable run ids |
| `getChartSeries` via `request()` + bearer | ✅ Yes | `request<ChartSeriesRow[]>(\`/chart/series?days=${days}\`)` |
| No polling, queryKey includes days | ✅ Yes | Plain `useQuery`, no `refetchInterval`/`staleTime` override |
| i18n table es ASCII-folded | ✅ Yes | Exact match verified |

Documented deviations (all in apply-progress §Deviations, none undocumented): `home.retry` key; 6 (not 5 — see WARNING) sibling fixture updates; 2 page-level test files; exported `handleChartClick`; i18n landed in unit-3 commit. No UNDOCUMENTED scope creep: every non-design file in the diff is a test, a required fixture, or an orchestrator-owned planning artifact.

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` TDD Cycle Evidence table, 8 rows |
| All tasks have tests | ✅ | 8/8 rows map to existing test files |
| RED confirmed (tests exist) | ✅ | All 8 test files exist; RED signals recorded (import/module failures, 3-fail predicate, 4-fail keys) |
| GREEN confirmed (tests pass) | ✅ | Focused run 56/56 pass on 2026-09-09; full suite 265/266 (sole failure unrelated pre-existing nodal flake) |
| Triangulation adequate | ✅ | bestRunId x3, click x3, gap + continuous companion, tooltip x2, legend, es+en, days 30/7, table+counters+empty |
| Safety Net for modified files | ✅ | 49/49 pre-existing pass claimed per unit before modification; no post-change regressions in touched files |

**TDD Compliance**: 6/6 checks passed (31 new tests per apply record: 7 unit + 24 integration).

### Test Layer Distribution

| Layer | Tests (new) | Files | Tools |
|-------|-------------|-------|-------|
| Unit | 7 | `run-status.test.ts` (3), `api-client.test.ts` (2), `use-chart-series.test.tsx` (2) | vitest |
| Integration | 24 | `home-chart.test.tsx` (15), `(app)/page.test.tsx` (4), `(app)/runs/page.test.tsx` (3), `app-sidebar.test.tsx` (2) | vitest + testing-library + user-event, jsdom |
| E2E | 0 | 0 | not installed (none required by design) |
| **Total** | **31** | **7** | |

### Changed File Coverage

Coverage analysis skipped — no coverage tool detected (design explicitly sets no coverage gate; NOT a failure).

### Assertion Quality

Audited all 7 test files touching this change: **✅ All assertions verify real behavior** (0 CRITICAL, 0 WARNING).

- No tautologies, no type-only-alone assertions, every test calls production code (`bestRunId`, `handleChartClick`, `getChartSeries`, `useChartSeries`, rendered components with providers).
- The `for` loop over recharts curves in the companion test is guarded by a prior `length toBe(5)` assertion — not a ghost loop.
- `toHaveClass("text-amber-400")` asserts behavioral nav-active state, not styling trivia; `.recharts-line` counts verify the spec's 5-line requirement.
- Mock/assertion ratios healthy (single `push`/`fetch` mock per file, many distinct value assertions); test cases assert DIFFERENT expected values per behavior (settled/prov/preideal/null, 30/7, manual/public/empty).

### Quality Metrics

**Linter**: ✅ 0 errors (2 warnings, both in untouched files)
**Type Checker**: ⚠️ 1 pre-existing error in untouched `components/nodal/network-graph.test.tsx(214,12)`; 0 errors in any changed file

### Issues Found

**CRITICAL**: None
**WARNING**:
1. `pnpm test` exit 1 — single pre-existing nodal hour-selector timeout under full-parallel load (proven not a regression: passes isolated on branch and on clean develop; fixture-only diff). Per session preflight this does not fail verification.
2. `tsc` exit 1 — single pre-existing error in untouched `network-graph.test.tsx` (zero diff vs develop; zero errors in changed files). Same preflight applies.
3. Apply-progress §1.2 says "5 sibling fixtures" but lists and diffs 6 (`run-selector`, `run-comparison-table`, `types.test`, `runs/[id]/page.test`, `runs/[id]/nodal/page.test`, `(app)/nodal/page.test`) plus the primary `runs-table.test.tsx`. Documentation count drift only; all additions minimal (`visibility: "private"`, `input_grade: null`). Not blocking.
**SUGGESTION**:
- The 266-test full suite has no E2E/authed walkthrough (`pnpm dev` walkthrough was explicitly left for verify; no live session exists in this env). Consider an authed smoke pass of `/` and `/runs` before merge.
- Untracked planning artifacts (`proposal.md`, `exploration.md`, `specs/`, `design.md`, `config.yaml`, handoff) and `.atl` cache modifications sit in the working tree; the delivery PR should include the intended set only.

### Verdict

**PASS WITH WARNINGS** — 7/7 requirements, 12/12 scenarios compliant with passing covering tests; design followed; only documented deviations; the two non-zero gate exits are both proven pre-existing issues on unmodified develop and excluded from failure per session preflight.
