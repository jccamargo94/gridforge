# Design: Hourly series DB — storage, writers, serving, backfill

## Technical Approach

Narrow `hourly_series` table (`ts`, `tenant_id` NULL=public, `series_key`, `value`, `source`) as single serving source. Writer 1: `refresh_tick` upserts public externals (`bolsa_tx1`, `mpo_xm`). Writer 2: `finish_run_ok` upserts 24 `ideal_marginal_price` rows (`source=run.id`) from `price_path`. Serving: `chart.py` reads hourly rows (public + user's tenants), derives daily means with today's winner-run priority; per-request CSV reads removed. Backfill from `data/` CSVs; Alembic 0007/0008. No RLS/partitioning (proposal-locked). Unit conversion happens in the writer path (loaders `*1e3` before upsert); readers never scale.

## Architecture Decisions

### D1 — Public-row dedupe: two partial unique indexes
| Option | Tradeoff | Decision |
|---|---|---|
| `NULLS NOT DISTINCT` (PG15+) | Prod PG is 17.6 (verified via psql), but all repo tests run SQLite (conftest.py:24, migration smoke files) — SQLite cannot express it → SCN-HS-01-02 untestable, prod/test DDL diverge | Rejected |
| **Two partial unique indexes** | SQLAlchemy 2.0.51 renders both dialects identically; each doubles as query index for its access mode | **Chosen** |
| Sentinel tenant | Spec locks `NULL`=public (REQ-HS-01) | Rejected |

`uq_hourly_series_public_key` UNIQUE `(series_key, ts, source)` WHERE `tenant_id IS NULL`; `uq_hourly_series_tenant_key` UNIQUE `(tenant_id, series_key, ts, source)` WHERE `tenant_id IS NOT NULL` — satisfying REQ-HS-01's index need with no third index.

### D2 — Shared upsert helper
`upsert_hourly_rows(session, rows)` — one function both writers call; conflict target per row: NULL tenant → `ON CONFLICT (series_key, ts, source) WHERE tenant_id IS NULL DO UPDATE SET value=excluded.value`; tenant row → 4-column target with `WHERE tenant_id IS NOT NULL`. One statement per batch, one commit → single idempotency (SCN-HS-01-02/02-02).

### D3 — Keys, sources, winners
`series_key` = chart-facing key; externals `source='xm'`; runs `source=run.id`. (level, grade)→key: ideal/settled→`ideal_settled`; ideal/provisional→`ideal_provisional`; preideal (either grade)→`preideal`. Serving ranks visible sources per (Bogota day, key): settled grade first, then `created_at` desc — mirrors `_SERIES_KEYS` + `list_done_public_dispatch_runs` recency. Scope = `tenant_id IS NULL OR tenant_id IN (user's tenants)` (REQ-HS-05). Accepted edge: run with unreadable `price_path` leaves no rows → cell `null` as today; only `*_run_id` differs (None).

### D4 — Run-row tenant attribution
`visibility=="public"` → `tenant_id NULL`. Private: owner in exactly 1 tenant → that `tenant_id`; in 0 or >1 → write nothing — no public leak by construction (SCN-HS-03-02).

### D5 — `ts` convention
`DateTime(timezone=True)`, stored UTC. Writers treat CSV naive datetimes as Bogota wall time (UTC−05:00, no DST) via `ZoneInfo("America/Bogota")`; readers bound Bogota day [D, D+1) in UTC for SQL, localize back for hourly arrays.

### D6 — Hook: `finish_run_ok` only
`finish_nodal_run_ok` untouched — nodal `RunResult` has no `price_path` (app/nodal/runner.py:105). `finish_run_ok` guards missing `price_path` (skip rows, run stays done). Call site executor.py:98-102 unchanged.

### D7 — Membership minimal
`Tenant(id String PK uuid-hex, name, created_at)`; `TenantMember(tenant_id FK→tenants.id, user_id; composite PK; no FK to auth.users, matching `runs.user_id`; role deferred)`. Surrogate `id` PK on `HourlySeries` (repo convention; ORM requires it) — dedupe comes from the partial uniques.

## Data Flow

```
refresh_tick ── year-CSV merge → cache clear ──┐
 ├─ ingest_external_window(start, end_day): bolsa_tx1 via load_precio_bolsa
 │    (already *1e3); mpo_xm via parse_mpo of ensured end_day iMAR blob;
 │    absent hours skipped (gap, never zero) ──┐
finish_run_ok ── price_path CSV (COP/MWh) → 24 rows source=run.id ┴─►
                 upsert_hourly_rows (one statement)
GET /chart/series ──► fetch_visible_rows(scope) ──► winner per (day, key)
     ──► daily mean of winner's rows + hourly arrays
backfill (`python -m app.db.series`) ──► ingest_external_window(full history)
     + replay done runs — same helpers, idempotent
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/db/models.py` | Modify | `Tenant`, `TenantMember`, `HourlySeries` + partial indexes |
| `alembic/versions/0007_tenants.py` | Create | `tenants` + `tenant_members` (0006 style) |
| `alembic/versions/0008_hourly_series.py` | Create | `hourly_series` + uniques (`postgresql_where`+`sqlite_where`) |
| `app/db/series.py` | Create | upsert helper, external/run ingest, `fetch_visible_rows`, tenant helpers, `__main__` backfill |
| `app/db/queries.py` | Modify | `finish_run_ok` calls `ingest_run_price_rows` in its tx |
| `app/scheduler/refresh.py` | Modify | call `ingest_external_window` after merge/ensure |
| `services/api/chart.py` | Modify | DB reads, winner ranking over visible scope, hourly exposure |
| `services/api/main.py` | Modify | pass `user_id` to `build_chart_series` |
| `tests/test_api_chart.py` | Modify | seed table from fixture via ingest; golden asserts unchanged |
| `tests/test_db_migrations.py` | Modify | assert 0007/0008 tables + index names |

## Interfaces / Contracts

Non-obvious pattern only (partial uniques must carry both dialect kwargs):

```python
class HourlySeries(Base):
    __tablename__ = "hourly_series"
    __table_args__ = (
        Index("uq_hourly_series_public_key", "series_key", "ts", "source", unique=True,
              postgresql_where=sa.text("tenant_id IS NULL"),
              sqlite_where=sa.text("tenant_id IS NULL")),
        Index("uq_hourly_series_tenant_key", "tenant_id", "series_key", "ts", "source",
              unique=True, postgresql_where=sa.text("tenant_id IS NOT NULL"),
              sqlite_where=sa.text("tenant_id IS NOT NULL")),
    )
    # id String PK (uuid4().hex, repo convention) + ts DateTime(timezone=True) NOT NULL,
    # tenant_id String FK tenants.id nullable, series_key/value/source NOT NULL
```

`Tenant`/`TenantMember` follow existing `Base` patterns (id PK, `_new_id`, utcnow default). API contract preserved; each row gains Bogota-hour-indexed length-24 arrays (`null` holes): `bolsa_tx1_hourly`, `mpo_xm_hourly`, `ideal_settled_hourly`, `ideal_provisional_hourly`, `preideal_hourly` (REQ-HC-02).

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit golden | COP/MWh invariant | fixture `xm_smoke`: bolsa 200 COP/kWh→**200000.0**, mpo **150000.0**, run 3000→**3000.0**; raw-scale row fails (SCN-HS-04) |
| Unit db | idempotency | write twice → 24 rows (01-02/02-02); private run, no tenant → no rows (03-02) |
| Integration | isolation | member of A sees public+A, never B (05-02, HC-02-02) |
| API | shape | daily mean == mean(hours) (HC-01-01); gap day → `null` (HC-01-02) |
| Migration | 0007/0008 | sqlite alembic smoke: tables, FKs, index names |
| Backfill | fixture dir | 24 rows/day, correct unit; re-run → unchanged (SCN-HS-06) |

Breaks first: `test_api_chart.py` externals test — seed table from `DD` fixture via ingest (doubles as backfill validation); `_finish_public_run` now also writes rows.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary; backfill is an in-process Python module entrypoint.

## Migration / Rollout

Additive: `alembic upgrade head` → backfill (idempotent) → deploy code; history appears once backfill runs (REQ-HS-06). Rollback: downgrade 0008→0007, revert writers/serving — CSVs remain source of truth.

## Open Questions

- [ ] D4 skips writing when an owner belongs to >1 tenant; if multi-tenant attribution becomes a product need, add a `tenant_id` choice at run creation — table and helper unchanged.
