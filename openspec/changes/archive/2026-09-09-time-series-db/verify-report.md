```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:742919c711252ec958d0efdbc0c4a7f677ca202fe3eba3ff668e4a60bcfb2a9a
verdict: pass
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 16/16
test_command: uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:5712e278381625cd3fac97260521af14130cbfe1bef211acf93f7e714cdac12e
build_command: uv run ruff check && uv run ruff format --check
build_exit_code: 0
build_output_hash: sha256:953aef1239c965ba0042552104e2c37461ba2814647d9b0dd340be37dbd22cea
```

## Verification Report

**Change**: time-series-db
**Version**: N/A (specs carry no version field)
**Mode**: Strict TDD (`openspec/config.yaml` `strict_tdd: true`; apply-progress obs #554 reports RED-first on every production change)
**Branch**: `fase8a-time-series-db` off `develop` @ 38c4fe4e7 — HEAD dfc05b54d, 7 apply commits, single PR vs develop (maintainer-approved `size:exception`).
**Evidence revision note**: `evidence_revision` is the SHA-256 of the evidence manifest (full pytest output bytes, ruff outputs, CLI backfill probe counts, non-constant mean probe results) assembled during this verification; recomputable from the digest list in "Build & Tests Execution".

**Gate scoping note (read before the envelope):** the envelope's `build_command` is the repo's lint/format gate (`ruff check` + `ruff format --check`) — this change is backend-only (UI explicitly out of scope in tasks.md preamble), so `config.yaml`'s frontend `pnpm --dir frontend build` is not a gate for it, matching the archived home-chart precedent of change-scoped gates. Full-suite pytest output and exit code are disclosed verbatim below.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 16 |
| Tasks complete | 16 |
| Tasks incomplete | 0 |

All 16 tasks `[x]` across U1–U4 in `openspec/changes/time-series-db/tasks.md`, each phase unit with an `## Apply status` block (commits `6982aeb03`…`dfc05b54d`, suite 440 → 467). No pending task blocks verification.

### Build & Tests Execution
**Build (ruff)**: ✅ Passed (exit 0)
```text
uv run ruff check:          exit 0 — "All checks passed!"
uv run ruff format --check: exit 0 — "195 files already formatted"
combined output sha256: 953aef1239c965ba0042552104e2c37461ba2814647d9b0dd340be37dbd22cea
```

**Tests**: ✅ 467 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
uv run pytest -q   (exit 0, 146.68s, 36 pre-existing deprecation/FutureWarnings)
467 passed, 36 warnings
full output sha256: 5712e278381625cd3fac97260521af14130cbfe1bef211acf93f7e714cdac12e
```
No failure required re-run classification. Pre-existing live-XM network tests were not exercised offline; nothing in the 467 depends on the network.

**Coverage**: ➖ Not available — `pytest-cov` not installed and `config.yaml` sets `coverage: null` / threshold 0. Changed-file coverage analysis skipped (informational, not blocking).

### Runtime probes (targeted, this verification)

1. **CLI backfill idempotence (task 4.3 harness, SCN-HS-06-01/02)** — NOT run against real `data/` (real CSVs present, 378M — production rows). Run against `tests/fixtures/xm_smoke` exactly as the apply runtime harness, twice, on a scratch SQLite DB:
   ```
   DATABASE_URL=sqlite:////tmp/opencode/tsdb-backfill-probe.db \
     uv run python -m app.db.series --data-dir tests/fixtures/xm_smoke \
     --start 2024-04-18 --end 2024-04-18
   ```
   Run 1 → "backfill ok: 48 external rows, 0 run rows"; Run 2 → identical. Final table: **48 rows total** — bolsa_tx1 24 × 200000.0 COP/MWh, mpo_xm 24 × 150000.0 COP/MWh, single source each. Re-run changes nothing → CLI-level idempotence proven.
2. **Non-constant hourly mean probe (strengthens SCN-HC-01-01 / SCN-HS-05-01)** — the suite's goldens use constant hourly values, which cannot discriminate a broken mean. Probe upserted 24 public `bolsa_tx1` rows with distinct values `100.0 + hour` (Bogota hour index, production `_bogota_to_utc`/`upsert_hourly_rows`), then `build_chart_series(days=1, today=2024-04-18, user_id=None)`: daily value **111.5 == mean of the 24 hourly values**; `bolsa_tx1_hourly[5] == 105.0` (hour index correct); absent `mpo_xm` day serves `null` with `[None]*24` (gap, never zero). PASS.

### Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| REQ-HS-01 Schema/migrations | SCN-HS-01-01 Migraciones aplicadas | `tests/test_db_migrations.py > test_alembic_upgrade_head_creates_tenants_and_hourly_series` (tables `tenants`/`tenant_members`/`hourly_series`, FK `tenant_id`→`tenants`, index names, both uniques, downgrade 0008→0007→0006 clean) | ✅ COMPLIANT |
| REQ-HS-01 | SCN-HS-01-02 Upsert fila publica repetida | `tests/test_db_series.py > test_upsert_hourly_rows_public_key_updates_in_place` (24→24 rows, values updated in place, tenant set `{None}`) + `tests/test_db_models.py > test_hourly_series_partial_unique_indexes_dedupe_by_scope` (IntegrityError on raw duplicate public/tenant key; public+tenant same key coexist) | ✅ COMPLIANT |
| REQ-HS-02 Externals ingest | SCN-HS-02-01 Dia completo publicado | `tests/test_scheduler_refresh.py > test_refresh_tick_ingests_public_hourly_external_rows` (24 rows per (series, Bogota day), all `tenant_id NULL`, bolsa 300 COP/kWh → **300000.0** COP/MWh, mpo 150000.0; merged days 04-14..04-21 all 24/24) | ✅ COMPLIANT |
| REQ-HS-02 | SCN-HS-02-02 Re-tick mismo periodo | same test, second tick → `counts_again == counts` (no duplicates/holes) | ✅ COMPLIANT |
| REQ-HS-03 Run ingest | SCN-HS-03-01 Run publico diario | `tests/test_db_series.py > test_finish_run_ok_public_run_writes_24_ideal_rows` (24 `ideal_marginal_price` rows, tenant NULL, `source == run_id`, value 3000.0) | ✅ COMPLIANT |
| REQ-HS-03 | SCN-HS-03-02 Run privado sin fuga publica | `tests/test_db_series.py > test_finish_run_ok_private_owner_without_membership_writes_nothing` (zero rows, none with `tenant_id NULL`) + `..._membership_rows_under_tenant` + `..._multiple_tenants_writes_each` (B1: every member tenant, 48 rows, never public) | ✅ COMPLIANT |
| REQ-HS-04 Unit invariants | SCN-HS-04-01 Precio en COP/MWh | `tests/test_series_golden.py > test_golden_external_scale_from_backfill` (bolsa `{200000.0}` — raw 200.0 never stored; mpo `{150000.0}`) + `test_golden_run_scale_from_finish` (run `{3000.0}`) + refresh tick assert 300000.0 | ✅ COMPLIANT |
| REQ-HS-04 | SCN-HS-04-02 Dorado detecta escala cruda | `tests/test_series_golden.py > test_golden_full_pipeline_pins_and_raw_scale_detection` (raw 200.0 row inserted → `_assert_scale_pins` raises AssertionError) | ✅ COMPLIANT |
| REQ-HS-05 Serving | SCN-HS-05-01 Respuesta 24 valores + promedio | `tests/test_api_chart.py > test_external_series_from_seeded_hourly_rows` (24 hourly values + daily == mean) + `test_series_endpoint_shape_and_days_bounds` (5 `*_hourly` length-24 arrays, days 1..90 contract) + runtime probe 2 (non-constant mean) | ✅ COMPLIANT |
| REQ-HS-05 | SCN-HS-05-02 Aislamiento publico vs tenant | `tests/test_series_isolation.py > test_member_a_sees_public_and_own_tenant_never_b` / `test_member_b_...` / `test_non_member_sees_public_only` + `test_hourly_rows_isolated_per_tenant` (hourly arrays follow same scope; `*_run_id` None when invisible) | ✅ COMPLIANT |
| REQ-HS-06 Backfill | SCN-HS-06-01 Backfill correcto | `tests/test_series_backfill.py > test_backfill_writes_24_rows_per_series_in_correct_unit` + `test_backfill_replays_done_run_rows` + CLI probe (48 rows: 24 bolsa @ 200000.0, 24 mpo @ 150000.0) | ✅ COMPLIANT |
| REQ-HS-06 | SCN-HS-06-02 Backfill re-ejecutado | `tests/test_series_backfill.py > test_backfill_rerun_is_idempotent` (48 → 48, counts unchanged) + CLI probe (run twice → 48 rows both times) | ✅ COMPLIANT |
| REQ-HC-01 Daily mean from hourly_series | SCN-HC-01-01 Promedio == media de 24 filas | `tests/test_api_chart.py > test_external_series_from_seeded_hourly_rows` (`bolsa_tx1 == sum(hourly)/24`) + `test_preideal_settled_wins_over_provisional` / `test_preideal_falls_back_to_provisional_when_no_settled` / `test_ideal_lanes_are_reported_separately` (winner: grade priority then created_at desc — parity with old CSV path verified by diff against `develop:services/api/chart.py`) + runtime probe 2 | ✅ COMPLIANT |
| REQ-HC-01 | SCN-HC-01-02 Dia sin datos → null | `tests/test_api_chart.py > test_gap_day_without_rows_serves_null_not_zero` (bolsa/mpo/preideal `None`, hourly `[None]*24`, `preideal_run_id None`) + runtime probe 2 | ✅ COMPLIANT |
| REQ-HC-02 Hourly values exposed | SCN-HC-02-01 Respuesta horaria publica | `tests/test_api_chart.py > test_external_series_from_seeded_hourly_rows` (mpo 24 hourly `[150000.0]*24` + daily mean over HTTP-backed shape test) | ✅ COMPLIANT |
| REQ-HC-02 | SCN-HC-02-02 Aislamiento por tenant | `tests/test_series_isolation.py > test_hourly_rows_isolated_per_tenant` (user-a sees public+A hourly, B day `[None]*24`) | ✅ COMPLIANT |

**Compliance summary**: 16/16 scenarios compliant. Every SCN exercised by a passing test; none unexercised.

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| REQ-HS-01 | ✅ Implemented | `Tenant`/`TenantMember`/`HourlySeries` at `app/db/models.py:158-212`; partial uniques carry both `postgresql_where` AND `sqlite_where` (models.py:186-204, D1); migrations `alembic/versions/0007_tenants.py`, `0008_hourly_series.py` (revises chain 0006→0007→0008, idempotent downgrade tested). |
| REQ-HS-02 | ✅ Implemented | `app/scheduler/refresh.py:107-117`: `ingest_external_window` inside the `DAILY_EARLIEST` block after `ensure_data_for_date`; window `end_day - data_refresh_window_days .. end_day`; `app/db/series.py:202-212` loops Bogota days; skip-on-missing at `_external_day_rows` (series.py:141-175) catches `(OSError, ValueError)` and logs — never raises, never zero-fills. |
| REQ-HS-03 | ✅ Implemented | Hook in `finish_run_ok` before commit (`app/db/queries.py:134-143`); `ingest_run_price_rows` (series.py:241-268): public → `[None]`, private → every member tenant of owner (B1), zero memberships → nothing; unreadable/missing `price_path` skipped (B3, run stays done — `test_finish_run_ok_unreadable_price_path_never_raises`); `finish_nodal_run_ok` untouched (D6). |
| REQ-HS-04 | ✅ Implemented | Conversion in the write path only: `load_precio_bolsa` x1e3 (`app/data/loaders.py:55`) — the only scale point; run/mpo values already COP/MWh, stored as-is; readers (`chart.py`, probes) never scale; goldens pin 200000.0 / 150000.0 / 3000.0. |
| REQ-HS-05 | ✅ Implemented | `chart.py` reads only `hourly_series` for values (no `pd.read_csv` anywhere in `services/api/chart.py`); `fetch_visible_rows` scope `tenant_id IS NULL OR tenant_id IN (...)` (series.py:179-199); winner per (Bogota day, chart key) ranked grade-priority-then-created_at-desc over caller-visible runs (`list_done_public_dispatch_runs(user_id)`, queries.py:346-372); hourly arrays Bogota-local; `*_run_id` preserved; `user_id` plumbed from JWT at `services/api/main.py:318-326`. |
| REQ-HS-06 | ✅ Implemented | `python -m app.db.series` (series.py:321-357) argparse entrypoint; external window replay + done-run replay; idempotent (CLI probe: 48 rows twice). |
| REQ-HC-01 | ✅ Implemented | Daily mean derived from the winner's 24 hourly rows (`_summary`, chart.py:48-59; `count` guards empty); winner selection parity with pre-change code verified by diff; gap day → `None` never 0. |
| REQ-HC-02 | ✅ Implemented | 5 `*_hourly` length-24 arrays (bolsa_tx1, mpo_xm, ideal_settled, ideal_provisional, preideal) with `null` holes; only `hourly_series` values served. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 two partial unique indexes (both dialect kwargs) | ✅ Yes | models.py:186-204 + 0008 migration:35-50 |
| D2 shared upsert, per-batch statement, one commit | ✅ Yes | `upsert_hourly_rows` series.py:101-133 |
| D3 keys/sources/winners; scope NULL OR IN(tenants) | ✅ Yes | chart.py:25-37, series.py:179-199; unreadable price_path → cell null, `*_run_id` None (documented edge) |
| D4 run-row tenant attribution | ⚠️ Superseded by B1 | Binding context B1 (tasks.md 2.5, apply-progress): multi-tenant owner → rows under EVERY member tenant, not "write nothing"; zero membership → nothing (no leak) preserved. Deviation recorded in tasks.md/apply status; design.md prose still shows D4 wording |
| D5 `ts` UTC convention, Bogota wall localize | ✅ Yes | `_bogota_to_utc`/`bogota_day_bounds` series.py:53-68; chart `_bogota_dt` attaches UTC for naive SQLite reads |
| D6 hook only in `finish_run_ok` | ✅ Yes | `finish_nodal_run_ok` untouched (queries.py:150+) |
| D7 membership minimal, surrogate id PK | ✅ Yes | models.py:158-177; composite PK tenant_members; no auth FK |
| B1/B2/B3/B4 | ✅ Yes | B1 multi-tenant writes; B2 runs-side winner scope == row visibility scope; B3 skip+log never raise; B4 conversions in writers, never readers (golden-pinned) |

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress obs #554 "TDD Cycle Evidence" table, one row per task group (1.1–4.4) |
| All tasks have tests | ✅ | 16/16 tasks map to the 8 change test files (56 test functions in change-related files) |
| RED confirmed (tests exist) | ✅ | All 8 test files exist and were executed green in the full suite |
| GREEN confirmed (tests pass) | ✅ | 467/467 pass on execution (exit 0); focused files re-run green inside suite |
| Triangulation adequate | ✅ | Multiple distinct test cases per scenario; non-constant mean probe closes the constant-value goldens gap |
| Safety Net for modified files | ✅ | Modified files (test_db_models, test_db_migrations, test_scheduler_refresh, test_api_chart) are extensions of existing suites; pre-existing tests kept green at every commit (440 → 467) per apply status |

**TDD Compliance**: 6/6 checks passed

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit / DB-layer (in-memory SQLite session) | 30 | 5 (`test_db_models`, `test_db_series`, `test_series_isolation`, `test_series_golden`, `test_series_backfill`) | pytest |
| Integration (alembic smoke, scheduler tick, HTTP shape) | 26 | 3 (`test_db_migrations`, `test_scheduler_refresh`, `test_api_chart`) | pytest, alembic, TestClient |
| E2E | 0 | 0 | — |
| **Total (change-related files)** | **56** | **8** | pytest |

Distribution is pytest-native for a backend repo with no solver-e2e runtime in scope (SQLite session + API contract per tasks.md U2/U3 runtime-harness N/A notes). Critical business logic (upsert idempotency, unit scale, tenant isolation) is covered at DB-layer and API-level; no missing-tool warnings.

### Changed File Coverage
Coverage analysis skipped — no coverage tool detected (`pytest-cov` not installed; `config.yaml` `coverage: null`, threshold 0). Informational only, never a failure.

### Assertion Quality
✅ All assertions verify real behavior. Audit of the 8 change-related files found no tautologies, no ghost loops (all collection loops guard emptiness via prior count asserts), no orphan empty checks without companion non-empty tests, no type-only-alone assertions, no mock-heavy tests (no mocks at all; scheduler tests use a shape-faithful `_FakeConsult` double and monkeypatched `ensure_data_for_date` boundaries).
**Assertion quality**: 0 CRITICAL, 0 WARNING — one SUGGESTION below (constant-value goldens → permanent non-constant mean test).

### Quality Metrics
**Linter**: ✅ `ruff check` no errors (whole repo, exit 0); `ruff format --check` clean.
**Type Checker**: ➖ Not run — repo convention: `ty` runs manual-only (`stages: [manual]`, non-blocking by design, per `.agents/rules/python-patterns.mdc`); not a verify gate for this repo.

### Issues Found
**CRITICAL**: None
**WARNING**: None
**SUGGESTION**:
1. `tests/test_api_chart.py` / `test_series_golden.py` seed constant hourly values, so `daily == mean(hours)` assertions cannot discriminate a broken mean/aggregation. The invariant was proven sound this session via a non-constant runtime probe, but a permanent suite test with varying per-hour values would lock it against regression.
2. `openspec/changes/time-series-db/design.md` D4 prose still reads "owner in 0 or >1 tenants → write nothing"; the binding B1 context (every member tenant) supersedes it. Behavior and tests match B1; refresh D4's wording during archive so design docs and implementation stay aligned.
3. Backfill of done runs replays with CURRENT memberships for runs finished before this change existed (multi-tenant attribution of historical rows). Accepted and documented in apply-progress; flag for operators running the one-time backfill.

### Verdict
PASS
All 16 tasks complete; full suite 467 passed (exit 0) with ruff clean; 8/8 requirements and 16/16 scenarios covered by passing tests plus CLI-level idempotence and non-constant-mean runtime probes; only SUGGESTION-level findings (no blockers, no criticals, no warnings).
