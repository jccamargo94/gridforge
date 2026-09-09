# Exploration: time-series-db (hourly series storage)

## Product decision (locked, not reopened)

NO daily averages. Real **hourly** values, with **public** charts + **per-tenant** charts.
Open question explored here: WHERE the hourly series live — the serving path / storage design.
Candidate volume: ~90k rows/year public, ~4.4M rows/year with 100 tenants.

---

## Current State (VERIFIED against code, 2026-09-09 @ develop)

### Serving path — `GET /chart/series` (`services/api/chart.py`)

`build_chart_series()` (chart.py:53) returns **one row per Bogota calendar day** with the
**daily mean (COP/MWh)** of 5 series. Series keys + source, exactly as coded:

| key | source | unit | aggregation |
|-----|--------|------|-------------|
| `bolsa_tx1` | `load_actual_bolsa` (actuals.py:21) → `load_precio_bolsa` (loaders.py:51) reads year CSV `precio_bolsa/precio_bolsa_{year}.csv`, column `precio_bolsa` scaled `*1e3` → COP/MWh | COP/MWh | `_mean_actual` daily mean of 24 values |
| `mpo_xm` | `load_actual_price` (actuals.py:12) → `parse_mpo` of per-date iMAR `.txt` blob (`resolve_input("iMAR")`), "MPO" row | COP/MWh | `_mean_actual` daily mean |
| `ideal_settled` (+`_run_id`) | `_mean_price` (chart.py:29): run artifact CSV `run.price_path`, column `ideal_marginal_price` | COP/MWh | `sub.astype(float).mean()` daily mean |
| `ideal_provisional` (+`_run_id`) | same | COP/MWh | daily mean |
| `preideal` (+`_run_id`) | same (settled wins, then provisional) | COP/MWh | daily mean |

Key mechanics:
- Simulated series: `queries.list_done_public_dispatch_runs` (queries.py:331) filters
  `visibility=="public" AND status=="done" AND level in (preideal, ideal)`, ordered
  `created_at desc`; first hit per `(dispatch_date, slot)` wins (chart.py:56-62).
- Externals: read live from `data/` files **on every request** (no cache, no DB).
- Row shape (chart.py:68-82): `date`, `bolsa_tx1`, `mpo_xm`, `ideal_settled`,
  `ideal_settled_run_id`, `ideal_provisional`, `ideal_provisional_run_id`, `preideal`,
  `preideal_run_id`.
- The underlying `run.price_path` CSV **already contains hourly values** (24 rows/hourly
  `ideal_marginal_price`, results.py:102); chart.py collapses them to a daily mean.

### Auth / tenant model today

- Supabase is used ONLY as (a) hosted Postgres (`DATABASE_URL` → `*.pooler.supabase.com`,
  `.env:1`) and (b) JWT issuer (`SUPABASE_JWKS_URL`, auth.py:13). **No** PostgREST, **no**
  RLS, **no** supabase CLI/migrations dir, **no** `config.toml`, **no** local `supabase/`.
- Auth is app-layer: `get_current_user_id` (auth.py:33) decodes the Supabase JWT and returns
  `payload["sub"]`. Every route takes `user_id: str = Depends(get_current_user_id)`.
- Tenant isolation is **app-layer column filtering**, not RLS:
  - `_get_authorized_run` (main.py:188): `run.user_id == user_id OR run.visibility == "public"`.
  - `list_visible_runs` (queries.py:248): `Run.user_id == user_id OR Run.visibility == "public"`.
  - "public" today = a boolean `visibility` column on `runs` (default `"private"`), NOT a
    tenant/workspace concept. There is no `tenants`/`orgs`/`workspaces` table.

### Writer / ingestion path (VERIFIED real module)

- `refresh_tick` is in **`app/scheduler/refresh.py`** (refresh.py:69) — the handoff path was correct.
- `plan_tick` is in **`app/scheduler/tick.py`** (tick.py:42) — NOT refresh.py.
- Worker loop: **`services/worker/main.py`** `main()` (main.py:84) — a **plain polling loop**
  (`POLL_INTERVAL_SECONDS = 5`, main.py:12), NOT Celery. Each `main_iteration` (main.py:30):
  1. `refresh.refresh_tick` when `fresh_next` due (cadence `DATA_REFRESH_INTERVAL_MINUTES`, default 60m).
  2. `tick.plan_tick` when `plan_next` due (cadence `PLAN_TICK_SECONDS`, default 60s).
  3. `plans.sweep_create_rows` daily at `sweep_time` 05:30.
  4. `process_once` → `claim_next_pending_run` + `execute_run` (manual lane).
- `refresh_tick` (refresh.py:69): pulls 5 XM series via `pydataxm.ReadDB` into **year CSVs**
  (`dispo_declarada`, `ofertas`, `demaCome`, `dispo_come`, `precio_bolsa`), keyed-merge, then
  `loaders.clear_loader_caches()`, then daily blob download (`download.ensure_data_for_date`),
  then monthly settled gate (`plans.next_settlement_month` + `create_settled_rows_for_month`).
  **Values are written UNSCALED to the CSVs** (xm_bulk.py docstring); scaling happens at read
  time in loaders.py / case_builder.py.
- Completing a run: `finish_run_ok` (queries.py:88) writes `status=done`, artifact paths
  (`price_path`, `dispatch_path`, `bess_path`, `marginal_plants_path`) and a `MetricSet`.
  `executor.execute_plan` → `execute_run` are the run pipeline entry points.

### DB schema (Alembic-managed, 7 tables, NO RLS)

Schema is managed by **Alembic** (`alembic/versions/0001..0006`), target metadata
`app.db.models.Base`. No `.sql` files, no supabase migrations, no RLS/policies/partitions/
Timescale/pg_partman anywhere in the repo. Tables:

1. `scenarios` — id, mode, penetration_level, units(JSON), created_by, created_at
2. `cases` — id, dispatch_date, level, solver, compute_prices, scenario_id, nodal_network(JSON)
3. `runs` — id, case_id, user_id(NULL ok since 0006), visibility(default private), input_grade,
   status, created_at, started_at, finished_at, error, out_dir, dispatch_path, price_path,
   bess_path, log_path, marginal_plants_path
4. `metric_sets` — id, run_id(unique FK), rmse, mae, bias, wape, smape, r2, bess_charge_mwh,
   bess_discharge_mwh, bess_avg_soc_mwh, bess_net_revenue, dispatch_mae_mw, dispatch_rmse_mw,
   reference, evaluated_at
5. `nodal_results` — id, run_id(unique FK), metrics/redistribution/gen_revenue_by_zone/network(JSON),
   lmp_path, dispatch_path, branch_flows_path, settlement_status_quo_path, settlement_lmp_path,
   comparison_path, summary_path
6. `input_datasets` — id, dataset, partition_key, source, checksum, row_count, fetched_at,
   unique(dataset, partition_key)
7. `run_plans` — id, kind, target_date, status, attempts, due_at, run_id, error, created_at,
   started_at, finished_at, unique(kind, target_date)

**Confirmed: NO series table exists. Postgres stores only operational data.**

### Units / scale (VERIFIED against code)

| data | source format | where scaled | final model unit |
|------|---------------|--------------|------------------|
| `dispo_declarada` | **kW** | case_builder.py:426-433 `* 1e-3` (biddings.py:209 confirms "esta en kW") | MW |
| `ofertas` Value | **COP/kWh** | case_builder.py:434-437 `* 1e3` | COP/MWh |
| `precio_bolsa` | COP/kWh (raw in CSV) | loaders.py:55 `* 1e3` | COP/MWh |
| `PrId` predespacho demand | **MW raw, unscaled** | case_builder.py (preideal uses `demand_pronos` raw `.sum()`); biddings.py:203 confirms | MW |
| `demaCome` demand | kW | case_builder.py:504 `* 1e-3` | MW |
| iMAR `parse_mpo` | COP/MWh already | none | COP/MWh |
| `ideal_marginal_price` (run price CSV) | COP/MWh | results.py:54 "MPO is in COP/MWh" | COP/MWh |

**Everything chart.py returns today is COP/MWh** (daily mean). Any hourly storage MUST carry the
same COP/MWh convention for prices and MW for dispatch, or the 1000x class of bug returns.

---

## Affected Areas

- `services/api/chart.py` — the serving path to replace/augment; today on-the-fly daily-mean.
- `services/api/main.py:310` — `GET /chart/series` endpoint (auth dependency, days 1..90).
- `app/db/models.py` + `alembic/versions/` — new series table + migration (0007+).
- `app/db/queries.py` — new read path (hourly, tenant-filtered).
- `app/scheduler/refresh.py` — `refresh_tick` would need to ALSO write hourly series rows
  (today it only writes year CSVs + `input_datasets` manifest).
- `app/scheduler/executor.py` / `app/db/queries.finish_run_ok` — completing a run would need to
  ALSO write the run's 24 hourly `ideal_marginal_price` rows (today only `price_path` is stored).
- `app/data/actuals.py`, `app/data/loaders.py` — the external hourly source readers (already hourly).

---

## Approaches (grounded in what exists)

### Option A — Flat Postgres table `(ts, tenant_id NULL=public, series_key, value, source)`
Index `(tenant_id, series_key, ts)`. Volume ~90k-4.4M rows/yr is trivial for Postgres
(no partitioning needed at these sizes).

- Pros: single serving path (one SQL query filters tenant + key + range); fits existing
  SQLAlchemy/Alembic stack with zero new infra; simplest migration (one `op.create_table`).
- Cons: tenant_id semantics need a real tenant concept (none exists today — `visibility` is a
  boolean); NULL=public needs an index with `NULLS` support; hot range scans still fine at this size.
- Effort: Low.

### Option B — Native declarative monthly partitioning + cron maintenance
Partition by `ts` range monthly; cron drops old partitions.

- Pros: bounded partition size; drop-old-partition is cheap.
- Cons: pure over-engineering at 4.4M rows/yr (~367k rows/mo); adds cron + partition DDL to a
  codebase with no cron/pg_partman today; tenant isolation still unresolved.
- Effort: Medium-High.

### Option C — RLS-native Supabase for tenant isolation + single serving path
Expose the series table via Supabase Data API with RLS policies per tenant.

- Pros: real tenant isolation at the DB layer; anonymous/public charts via `anon` role.
- Cons: **architecture shift** — the repo does NOT use PostgREST/RLS today; auth is app-layer JWT;
  no `supabase/` migrations dir; would require enabling RLS + policies + Data API grants + a
  tenant table that does not exist. Highest blast radius for the least immediate benefit.
- Effort: High.

### Note (user correction honored)
TimescaleDB is NOT valid on new Supabase versions; if maintenance ever gets tedious the
escape hatch is **pg_partman** (not Timescale). Recorded here so the proposal does not reach for it.

---

## Recommendation

**Option A** (flat Postgres table, indexed `(tenant_id, series_key, ts)`), with one caveat:

- The **driver is the access model** (tenant isolation + single serving path), NOT volume —
  4.4M rows/yr does not justify partitioning (Option B) and RLS (Option C) is a Supabase-native
  shift this repo has not made (it uses app-layer JWT + column filters).
- Prefer a minimal `tenant_id` **string** column (nullable = public) matching the existing
  `runs.user_id`/`visibility` model, keeping the serving path in FastAPI (app-layer filtering,
  consistent with today) rather than jumping to RLS. RLS can be layered later if a real
  multi-tenant product requirement appears.
- Reuse the existing convention: write hourly values **unscaled** at the source, apply the one
  unit conversion at read/load (as loaders.py already does) to keep the 1000x class of bug out.

Writer responsibilities (for the proposal):
- `refresh_tick` must additionally upsert hourly public series rows (`bolsa_tx1`, `mpo_xm`, and
  the raw `dispo`/`ofertas`/`precio_bolsa` lanes as needed) alongside the year-CSV merge.
- Run completion (`finish_run_ok`/executor) must additionally write 24 hourly
  `ideal_marginal_price` rows keyed by run + tenant (public iff `visibility=="public"`).
- `GET /chart/series` becomes a thin read over the table (or a new `GET /chart/series/hourly`),
  removing the per-request `pd.read_csv` + daily-mean collapse.

---

## Risks

- **Tenant concept gap**: "per-tenant charts" imply a tenant/workspace that does not exist in the
  schema today (only `runs.user_id` + `visibility`). The proposal must define tenant_id = user_id
  or introduce a tenants table — this is a product/design decision, not a storage one.
- **Unit convention drift**: hourly storage must preserve COP/MWh (price) and MW (dispatch);
  mixing the raw kW/COP-per-kWh conventions into the table reintroduces the 1000x bug class.
- **Dual-write consistency**: series rows are written by two writers (refresh_tick for externals,
  run completion for simulated); a missing upsert path silently shows stale/gapped charts.
- **Backfill**: existing historical data lives only in year CSVs + run artifact CSVs, not the DB;
  a one-time backfill migration is required or historical hourly charts start empty.
- **Supabase pooling caveat**: `DATABASE_URL` uses the **pooler** (`.pooler.supabase.com`); bulk
  upserts from the worker go through the transactional pooler — no new concern for a flat table,
  but worth noting if a heavy backfill is planned.

## Ready for Proposal

**Yes.** The exploration closes the storage question: flat table + app-layer serving (Option A),
tenant_id defined in the proposal, both writers extended, backfill planned. The proposal should
not spend cycles on partitioning/RLS/Timescale — none are warranted by the volume or the current
architecture.
