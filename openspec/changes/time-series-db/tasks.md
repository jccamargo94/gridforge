# Tasks: Time-Series DB — hourly storage, writers, serving, backfill

> Preamble: all series are price series, COP/MWh (B4 — REQ-HS-04 kW→MW vacuous). Threat matrix N/A. UI out of scope. strict_tdd: RED first; suite green per commit (B5).

## Review Workload Forecast

- Estimated changed lines: 1400–1800
- Suggested split: 4 work units; single PR needs size:exception

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

## Suggested Work Units

`uv run pytest -q <files>`.

| Unit | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|
| U1 — models + migrations 0007/0008 | tests/test_db_models.py test_db_migrations.py | alembic upgrade head (scratch SQLite) | downgrade 0008, then 0007 |
| U2 — ingest helper + writers A/B | tests/test_db_series.py + affected callers | N/A: SQLite session contract; no solver e2e | revert writer hooks; drop series.py |
| U3 — chart serving | tests/test_api_chart.py test_series_isolation.py | N/A: seeded-session API contract | revert chart.py + queries scope |
| U4 — backfill + goldens | tests/test_series_backfill.py test_series_golden.py | `uv run python -m app.db.series` twice on fixture dir | delete rows; CSVs remain truth |

## Phase 1: Models + Migrations (U1)

- [x] 1.1 RED `tests/test_db_models.py`: Tenant/TenantMember roundtrip (D7: surrogate id PK, no role, no auth FK)
- [x] 1.2 GREEN: models + `alembic/versions/0007_tenants.py` (0006 style, upgrade/downgrade)
- [x] 1.3 RED+GREEN: `HourlySeries` (D1 partial uniques, both dialects; D5 UTC; nullable FK) + `0008_hourly_series.py`
- [x] 1.4 Extend `tests/test_db_migrations.py` smoke: tables, FK, index names (SCN-HS-01-01)

## Phase 2: Ingest Helper + Writers (U2)

- [ ] 2.1 RED `tests/test_db_series.py`: upsert idempotent (SCN-HS-01-02); per-row conflict target public vs tenant (D2); B3 skip+log on unreadable source
- [ ] 2.2 GREEN `app/db/series.py`: `upsert_hourly_rows`, one statement/commit per batch
- [ ] 2.3 RED `tests/test_scheduler_refresh.py`: tick writes 24 public rows/series (SCN-HS-02-01/02)
- [ ] 2.4 GREEN: hook `ingest_external_window` into `refresh_tick` after ensure_data_for_date (refresh.py:107-108)
- [ ] 2.5 RED: `finish_run_ok` (queries.py:88): 24 ideal rows source=run_id; public→NULL; multi-tenant owner→each tenant (B1); zero-membership→none (SCN-HS-03-02); B3: bad price_path/absent CSVs never raise (executor.py:107-112)
- [ ] 2.6 GREEN: `ingest_run_price_rows` hook before queries.py:127 commit; membership keyed on owner user_id (JWT sub); `finish_nodal_run_ok` untouched (D6)

## Phase 3: Serving (U3)

- [ ] 3.1 RED `tests/test_api_chart.py`: seed DD via ingest (:11); `_finish_public_run` writes rows (:14); key-set (:98-108) gains 5 `*_hourly` keys; goldens (:88-89) unchanged; daily==mean(hours), empty day→null (SCN-HC-01-01/02)
- [ ] 3.2 GREEN `chart.py`: `fetch_visible_rows` scope NULL OR IN(caller tenants) (REQ-HS-05); runs-side winner per (day,key), grade then created_at desc (B2; extend queries.py:331); hourly arrays Bogota-local; `*_run_id` kept
- [ ] 3.3 `services/api/main.py` (:310): pass user_id into `build_chart_series`
- [ ] 3.4 RED+GREEN `tests/test_series_isolation.py`: member A sees public+A, never B; non-member public only (SCN-HS-05-02, SCN-HC-02-02)

## Phase 4: Backfill, Goldens, Closeout (U4)

- [ ] 4.1 GREEN `python -m app.db.series` (REQ-HS-06): replay year CSVs + done runs; idempotent (SCN-HS-06-02)
- [ ] 4.2 RED `tests/test_series_golden.py` (SCN-HS-04): raw 200.0 COP/kWh fails vs 200000.0; mpo 150000.0; run 3000→3000.0
- [ ] 4.3 `tests/test_series_backfill.py` vs `tests/fixtures/xm_smoke/`: 24 rows/day, correct unit (SCN-HS-06-01)
- [ ] 4.4 Final gates: ruff + full `uv run pytest -q`
