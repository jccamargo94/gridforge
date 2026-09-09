# Automated Daily Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-scheduling daily-automation layer inside the existing polling worker: a `run_plans` table plus pure, clock-injected scheduler ticks that run two labeled lanes per date (provisional early, settled when the real inputs arrive), incrementally refresh the five real XM year CSVs (keyed merge/upsert + loader-cache invalidation), roll offer-price estimates forward (real ∪ estimated union), re-evaluate metrics without re-solving (iMAR / bolsa TX1 references), expose daily system runs publicly (`runs.user_id` nullable, `visibility`, `input_grade`), and serve `GET /chart/series` — backend only (#89); frontend Home (#90) is out of scope.

**Architecture:** The worker keeps its manual claim loop (`process_once`, `POLL_INTERVAL_SECONDS=5`) and gains separately-gated ticks — plan tick (default 60 s), freshness tick (default 60 min), a 05:30 sweep, and a monthly gate — implemented as pure functions in a new `app/scheduler/` package with an injected clock (`plan_tick(session, now)`), DB-only plan CRUD in `app/db/queries.py`, postgres-only `FOR UPDATE SKIP LOCKED` claim helpers in `app/db/claim.py` (never executed on sqlite), and a thin `services/worker/main.py` loop wiring them. Execution reuses the exact manual solve path (`run_case` → `finish_run_ok`/`finish_nodal_run_ok`/`finish_run_failed`) extracted into a shared `execute_run`. Run-plan semantics: `UNIQUE(kind, target_date)` rows are claimed/retried within kind windows (America/Bogota wall time, stored UTC); windowed kinds expire to `skipped(reason)`; reeval kinds (`reeval_preideal`, `reeval_ideal`) overwrite the source run's `metric_set` row with `reference` + `evaluated_at`, never re-solving. A `DAILY_ENABLED` env kill-switch defaults to `true` and lets the deployment land dark.

**Tech Stack:** Python 3.12, SQLAlchemy 2, pandas 2.2.2, Pyomo/cbc, FastAPI/TestClient, pytest, alembic, `app.storage.get_storage` for I/O, `pydataxm` for the incremental pull. No new dependencies, no Celery/Redis, no new service.

**Spec:** `docs/superpowers/specs/2026-09-08-daily-runs-design.md` — this plan argues from the spec; executors read both. Config env defaults come verbatim from spec §8 (Task 6). Where the spec leaves a rule open, this plan states the chosen policy in the task code/docstring and flags it in "Notes for orchestrator" at the end.

## Global Constraints

- **Dependency pins stay put**: `pandas==2.2.2` (verified `.stack()` behavior on empty frames) and `numpy==1.26.4` (`numpy<2` — Pyomo 6.7.3 uses `np.float_`, removed in NumPy 2; without the pin `import pyomo.environ` fails). Do not let a resolver move them.
- **Solver default is `cbc`, never `appsi_highs`** — `pyo.SolverFactory("appsi_highs")` crashes on every solve via Pyomo's legacy wrapper (documented root cause, `docs/superpowers/specs/2026-08-05-fase2-docker-design.md` §3). Plan-created runs use `solver="cbc"`, `compute_prices=True`.
- **`pytest` is dev-only** (`[dependency-groups] dev`), never a runtime dependency.
- **Pre-commit: `ruff` is blocking** (`select = ["E", "F", "I"]`, `line-length = 100`); `ty` is informational (`stages: [manual]`) and must not be made blocking.
- **`FOR UPDATE SKIP LOCKED` is postgres-only** — tests run single-process sqlite, whose dialect does not support the clause. Any locking branch must be dialect-guarded (`session.bind.dialect.name == "postgresql"`) and the guard unit-tested (monkeypatch), exactly as `app/db/claim.py` does today.
- **All app I/O goes through `app.storage.get_storage`** (`exists`/`open`/`list_dir`) except the two documented direct `open()` blocks in `case_builder.py` (dCondIniP/dCondIniU). New app code follows the Storage abstraction; test code may write plain files under `tmp_path`.
- **`data/` is git-ignored** — never commit data; never claim "works with real data" from synthetic fixtures. Fixtures live under `tests/fixtures/`, anchored with `Path(__file__).parent`, never cwd-relative strings.
- **`.gitignore` has a global `*.csv`** — `tests/fixtures/**/*.csv` is already excepted; every new fixture CSV stays under that path (`tests/fixtures/xm_smoke/`).
- **No commits to `develop`.** Branch `fase7a-daily-automation` is checked out; every task commits there.
- **Conventional commits in English** (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`), tests+code in the same commit per task.
- **NO AI co-authorship/attribution** in commit messages, PR titles, or PR bodies (no `Co-Authored-By:`, no `🤖`, no model names).
- **DB access in tests is sqlite** (in-memory `create_engine("sqlite:///:memory:")` + `Base.metadata.create_all`, or alembic `command.upgrade` on a tmp file); postgres-only branches stay dormant on sqlite and are verified via monkeypatch.
- **The scheduler never runs in tests**: ticks are pure functions with an injected `now`; worker integration is minimal and monkeypatched (spec §10).
- **Reuse before new code**: plan-created runs execute through the existing `run_case`/`finish_run_*` path; do not write a second solve path.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/db/models.py` | Modify: new `RunPlan` model; `Run.user_id` nullable + `visibility`/`input_grade`; `MetricSet.reference`/`evaluated_at` |
| `alembic/versions/0006_daily_automation.py` | Create: run_plans table + runs/metric_sets column migration (sqlite-safe batch alters) + defaults backfill |
| `app/db/queries.py` | Modify: `create_case_and_run` (nullable user_id, `visibility`, `input_grade`), `finish_run_ok` reference stamping, `update_metric_set`, `list_visible_runs`, run_plans CRUD (`create_run_plan`, `get_run_plan`, `list_claimable_plans`, `mark_plan_done/failed/skipped`) |
| `app/db/claim.py` | Modify: `claim_run_by_id`, `claim_run_plan_by_id` — postgres-only lock lives here and only here |
| `app/scheduler/__init__.py` | Create: package marker |
| `app/scheduler/config.py` | Create: `SchedulerConfig` dataclass + `from_env()` with spec §8 defaults read via `os.getenv` |
| `app/scheduler/timeutil.py` | Create: tz helpers (America/Bogota ↔ UTC) and per-kind window edges `window_edges(kind, target, config)` |
| `app/scheduler/inputs.py` | Create: input-availability predicates (`blobs_ready`, `series_has_day`, `month_complete`, `source_run_done`, `kind_inputs_ready`) |
| `app/scheduler/plans.py` | Create: plan-row creation ticks (`ensure_daily_plans`, `sweep_create_rows`, `create_settled_rows_for_month`, `next_settlement_month`) + kind metadata maps |
| `app/scheduler/reeval.py` | Create: `reevaluate_metrics` (reads run price CSV, scores vs iMAR/bolsa TX1, writes `metric_set.reference`/`evaluated_at`) |
| `app/scheduler/executor.py` | Create: `execute_run` (shared solve path extracted from `process_once`), `execute_plan`, `execute_reeval` |
| `app/scheduler/tick.py` | Create: `plan_tick(session, now, config)` — window/input checks, claim, dispatch, expiry-to-`skipped` |
| `app/scheduler/refresh.py` | Create: `refresh_tick` (windowed pull → keyed merge/rewrite → cache clear → monthly gate) |
| `app/data/loaders.py` | Modify: add `clear_loader_caches()` (the five `lru_cache` loaders) |
| `app/data/xm_bulk.py` | Modify: windowed incremental refresh per series (keyed merge + full rewrite + manifest upsert), shared core with the one-shot `ensure_*` |
| `app/data/heuristic/biddings.py` | Modify: `ensure_ofertas_estimado` computes `ultimo_precio` over real ∪ estimated (ties → real wins) |
| `services/api/main.py` | Modify: visibility gates (list/detail/artifacts/log, uniform 404), payload `visibility`/`input_grade`, `GET /chart/series` |
| `services/api/chart.py` | Create: `build_chart_series` — daily means + run precedence per spec §7 |
| `services/worker/main.py` | Modify: extraction of `execute_run`; loop wiring with `main_iteration`/`WorkerState` |
| `README.md` | Modify: scheduler env vars + daily-runs behavior note under §8.3 |
| `tests/fixtures/xm_smoke/generate_fixture.py` + outputs | Modify: closed synthetic month (2024-03) + settled-day blob set (2024-03-15) |
| `tests/test_db_run_plans.py` | Create: RunPlan/column model tests |
| `tests/test_db_migrations.py` | Modify: 0006 upgrade/downgrade assertions |
| `tests/test_db_queries.py`, `tests/test_db_claim.py`, `tests/test_loaders.py`, `tests/test_xm_bulk.py`, `tests/test_ofertas_heuristic.py`, `tests/test_worker_main.py` | Modify: per-area additions |
| `tests/test_scheduler_timeutil.py`, `tests/test_scheduler_inputs.py`, `tests/test_scheduler_plans.py`, `tests/test_scheduler_reeval.py`, `tests/test_scheduler_executor.py`, `tests/test_scheduler_tick.py`, `tests/test_scheduler_refresh.py` | Create: scheduler unit tests (injected clock, sqlite, fake consult) |
| `tests/test_xm_smoke_settled.py` | Create: closed-month fixture checks + settled run end-to-end |
| `tests/test_api_visibility.py`, `tests/test_api_chart.py` | Create: API visibility + chart contract tests |

---

### Task 1: DB models — `RunPlan`, nullable `runs.user_id`, `visibility`/`input_grade`, `metric_sets.reference`/`evaluated_at`

**Files:**
- Modify: `app/db/models.py`
- Create: `tests/test_db_run_plans.py`

**Interfaces:**
- Consumes: existing model conventions (`_new_id`, `DateTime(timezone=True)`, `default=lambda: datetime.now(timezone.utc)`).
- Produces:
  - `RunPlan(Base)` — `__tablename__ = "run_plans"`, columns `id: Mapped[str]` (uuid hex, repo pattern), `kind: Mapped[str]`, `target_date: Mapped[date_]`, `status: Mapped[str]` default `"pending"`, `attempts: Mapped[int]` default `0`, `due_at: Mapped[datetime]` (tz-aware), `run_id: Mapped[str | None]` FK `runs.id`, `error: Mapped[str | None]`, `created_at`/`started_at`/`finished_at`; `UniqueConstraint("kind", "target_date", name="uq_run_plans_kind_target_date")`.
  - `Run.user_id: Mapped[str | None]` (nullable), `Run.visibility: Mapped[str]` default `"private"`, `Run.input_grade: Mapped[str | None]` (nullable).
  - `MetricSet.reference: Mapped[str | None]`, `MetricSet.evaluated_at: Mapped[datetime | None]` (nullable, `DateTime(timezone=True)`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db_run_plans.py
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Base, MetricSet, Run, RunPlan


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_run_plan_roundtrip_with_defaults():
    session = _session()
    plan = RunPlan(
        kind="preideal_daily",
        target_date=date(2026, 9, 10),
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
    )
    session.add(plan)
    session.commit()
    assert plan.id
    assert plan.status == "pending"
    assert plan.attempts == 0
    assert plan.run_id is None
    assert plan.error is None


def test_run_plan_unique_kind_target_date():
    session = _session()
    session.add(RunPlan(
        kind="ideal_daily",
        target_date=date(2026, 9, 10),
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
    ))
    session.commit()
    session.add(RunPlan(
        kind="ideal_daily",
        target_date=date(2026, 9, 10),
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_run_columns_carry_spec_defaults():
    session = _session()
    run = Run(case_id="case-1", user_id=None, visibility="public", input_grade="provisional")
    session.add(run)
    session.commit()
    assert run.user_id is None
    assert run.visibility == "public"
    assert run.input_grade == "provisional"


def test_run_user_id_and_metric_reference_are_nullable():
    session = _session()
    run = Run(case_id="case-1", user_id=None)
    session.add(run)
    session.commit()
    ms = MetricSet(run_id=run.id, reference=None, evaluated_at=None)
    session.add(ms)
    session.commit()
    fetched = session.scalars(select(MetricSet)).first()
    assert fetched.reference is None
    assert fetched.evaluated_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_run_plans.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.models.RunPlan'` (and `NOT NULL constraint failed` for the bare `user_id`).

- [ ] **Step 3: Write minimal implementation**

```python
# app/db/models.py — append the RunPlan class after InputDataset

class RunPlan(Base):
    __tablename__ = "run_plans"
    __table_args__ = (
        UniqueConstraint("kind", "target_date", name="uq_run_plans_kind_target_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    target_date: Mapped[date_] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("runs.id"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# app/db/models.py — Run: replace the user_id column and append two columns after it

    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    visibility: Mapped[str] = mapped_column(String, default="private")
    input_grade: Mapped[str | None] = mapped_column(String, nullable=True)
```

```python
# app/db/models.py — MetricSet: append after dispatch_rmse_mw

    reference: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_run_plans.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the existing db smoke tests**

Run: `uv run pytest tests/test_db_models.py tests/test_db_queries.py tests/test_db_claim.py -q`
Expected: PASS — no existing test constructs `Run` without a `case_id`.

- [ ] **Step 6: Commit**

```bash
git add app/db/models.py tests/test_db_run_plans.py
git commit -m "feat(db): add run_plans model and daily-run columns on runs/metric_sets"
```

---

### Task 2: Alembic migration 0006 (run_plans + column changes, sqlite-safe)

**Files:**
- Create: `alembic/versions/0006_daily_automation.py`
- Modify: `tests/test_db_migrations.py`

**Interfaces:**
- Consumes: current head `0005_nodal_results` (`revision = "0005"`).
- Produces: revision `"0006"` (`down_revision = "0005"`). SQLite has no `ALTER COLUMN`, so the `user_id` nullability change (and its downgrade) uses `op.batch_alter_table`; plain adds/drops inside the same batch keep the migration dialect-agnostic. Existing rows backfill via column defaults: `visibility` gets `server_default="private"` (NOT NULL); `input_grade`/`reference`/`evaluated_at` stay NULL (spec §3.4).

- [ ] **Step 1: Write the failing migration test**

```python
# tests/test_db_migrations.py — append

def test_alembic_upgrade_head_adds_run_plans_and_daily_columns(tmp_path):
    db_path = tmp_path / "migration_smoke_daily.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "run_plans" in tables

    plan_columns = {c["name"] for c in inspect(engine).get_columns("run_plans")}
    assert {
        "id", "kind", "target_date", "status", "attempts", "due_at",
        "run_id", "error", "created_at", "started_at", "finished_at",
    }.issubset(plan_columns)
    unique_constraints = inspect(engine).get_unique_constraints("run_plans")
    assert {c["name"] for c in unique_constraints} == {"uq_run_plans_kind_target_date"}

    run_columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    assert {"visibility", "input_grade"}.issubset(run_columns)
    user_id_nullable = next(
        c for c in inspect(engine).get_columns("runs") if c["name"] == "user_id"
    )
    assert user_id_nullable["nullable"] is True

    metric_columns = {c["name"] for c in inspect(engine).get_columns("metric_sets")}
    assert {"reference", "evaluated_at"}.issubset(metric_columns)

    command.downgrade(cfg, "0005")
    tables = set(inspect(engine).get_table_names())
    assert "run_plans" not in tables
    run_columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    assert "visibility" not in run_columns
    assert "input_grade" not in run_columns
    metric_columns = {c["name"] for c in inspect(engine).get_columns("metric_sets")}
    assert "reference" not in metric_columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_migrations.py::test_alembic_upgrade_head_adds_run_plans_and_daily_columns -q`
Expected: FAIL — `'run_plans' not in tables` (head is still 0005).

- [ ] **Step 3: Write the migration**

```python
# alembic/versions/0006_daily_automation.py
"""add run_plans and daily-run columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "target_date", name="uq_run_plans_kind_target_date"),
    )
    with op.batch_alter_table("runs") as batch:
        batch.alter_column("user_id", existing_type=sa.String(), nullable=True)
        batch.add_column(
            sa.Column("visibility", sa.String(), nullable=False, server_default="private")
        )
        batch.add_column(sa.Column("input_grade", sa.String(), nullable=True))
    with op.batch_alter_table("metric_sets") as batch:
        batch.add_column(sa.Column("reference", sa.String(), nullable=True))
        batch.add_column(sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("metric_sets") as batch:
        batch.drop_column("reference")
        batch.drop_column("evaluated_at")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("input_grade")
        batch.drop_column("visibility")
        batch.alter_column("user_id", existing_type=sa.String(), nullable=False)
    op.drop_table("run_plans")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_migrations.py -q`
Expected: PASS — all migration tests, including the new upgrade/downgrade-to-0005 (batch alters run on sqlite).

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/0006_daily_automation.py tests/test_db_migrations.py
git commit -m "feat(db): migrate run_plans and daily-run columns"
```

---

### Task 3: `queries.py` — manual-run surface: nullable user_id, visibility/input_grade, metric reference stamping, `update_metric_set`, `list_visible_runs`

**Files:**
- Modify: `app/db/queries.py`
- Modify: `tests/test_db_queries.py`

**Interfaces:**
- Consumes: `Run`/`MetricSet` model changes (Task 1).
- Produces:
  - `create_case_and_run(session, *, dispatch_date, level, solver, compute_prices, scenario_id, user_id: str | None = None, nodal_network=None, visibility: str = "private", input_grade: str | None = None) -> Run` — keyword-only as today; existing callers keep working unchanged.
  - `finish_run_ok(session, run, result, out_dir, *, reference: str | None = None) -> None` — stamps the created `MetricSet` with `reference` and `evaluated_at=now` only when `reference` is given (manual runs and un-reevaluated provisionals keep them NULL).
  - `update_metric_set(session, run_id: str, *, metrics: dict[str, float], reference: str) -> MetricSet` — overwrites the price-metric columns + `reference` + `evaluated_at=now`; creates the row when the run finished without metrics. Dispatch columns stay untouched (post-hoc re-eval has no solved model).
  - `list_visible_runs(session, user_id: str) -> list[Run]` — `(Run.user_id == user_id) | (Run.visibility == "public")`, `created_at` desc (spec §7). `list_runs_for_user` stays until Task 17 switches `GET /runs` over.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db_queries.py — append; keep the file's existing helpers (_session / imports)

def test_create_case_and_run_defaults_to_private_no_grade():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    assert run.user_id is None
    assert run.visibility == "private"
    assert run.input_grade is None


def test_create_case_and_run_system_grade_and_visibility():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
        input_grade="provisional",
    )
    assert run.visibility == "public"
    assert run.input_grade == "provisional"


def test_finish_run_ok_stamps_reference_only_when_given():
    session = _session()
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal)

    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    queries.finish_run_ok(
        session, run, RunResult(case=case, ok=True, metrics={"mae": 1.0}), out_dir="out"
    )
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference is None
    assert ms.evaluated_at is None

    run2 = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    queries.finish_run_ok(
        session,
        run2,
        RunResult(case=case, ok=True, metrics={"mae": 2.0}),
        out_dir="out",
        reference="iMAR",
    )
    ms2 = queries.get_metric_set(session, run2.id)
    assert ms2.reference == "iMAR"
    assert ms2.evaluated_at is not None


def test_update_metric_set_overwrites_price_metrics_and_reference():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.ideal)
    queries.finish_run_ok(
        session, run, RunResult(case=case, ok=True, metrics={"mae": 1.0}), out_dir="out"
    )
    ms = queries.update_metric_set(
        session, run.id, metrics={"mae": 9.0, "rmse": 3.0}, reference="bolsa_tx1"
    )
    assert ms.reference == "bolsa_tx1"
    assert ms.mae == 9.0
    assert ms.rmse == 3.0
    assert ms.evaluated_at is not None


def test_list_visible_runs_returns_own_and_public():
    session = _session()
    mine = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    other_private = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 19),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
    )
    public_other = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 20),
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
        input_grade="provisional",
    )
    visible = queries.list_visible_runs(session, "user-1")
    ids = [r.id for r in visible]
    assert mine.id in ids
    assert other_private.id not in ids
    assert public_other.id in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_queries.py -q`
Expected: FAIL — `create_case_and_run() got an unexpected keyword argument 'visibility'` (plus the NOT NULL failure on the default test).

- [ ] **Step 3: Write minimal implementation**

```python
# app/db/queries.py — import line change + function edits

from sqlalchemy import or_, select

def create_case_and_run(
    session: Session,
    *,
    dispatch_date: date_,
    level: str,
    solver: str,
    compute_prices: bool,
    scenario_id: str | None,
    user_id: str | None = None,
    nodal_network: dict | None = None,
    visibility: str = "private",
    input_grade: str | None = None,
) -> Run:
    case = Case(
        dispatch_date=dispatch_date,
        level=level,
        solver=solver,
        compute_prices=compute_prices,
        scenario_id=scenario_id,
        nodal_network=nodal_network,
    )
    session.add(case)
    session.flush()  # populate case.id before Run references it

    run = Run(
        case_id=case.id,
        user_id=user_id,
        status="pending",
        visibility=visibility,
        input_grade=input_grade,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
```

```python
# app/db/queries.py — finish_run_ok: new keyword param; MetricSet gains the stamp

def finish_run_ok(
    session: Session,
    run: Run,
    result: RunResult,
    out_dir: str,
    *,
    reference: str | None = None,
) -> None:
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc)
    run.out_dir = out_dir
    run.dispatch_path = result.dispatch_path
    run.price_path = result.price_path
    run.bess_path = result.bess_path
    run.marginal_plants_path = result.marginal_plants_path
    session.add(run)

    if result.metrics is not None or result.bess_summary is not None:
        metrics = result.metrics or {}
        bess = result.bess_summary or {}
        session.add(
            MetricSet(
                run_id=run.id,
                rmse=metrics.get("rmse"),
                mae=metrics.get("mae"),
                bias=metrics.get("bias"),
                wape=metrics.get("wape"),
                smape=metrics.get("smape"),
                r2=metrics.get("r2"),
                bess_charge_mwh=bess.get("bess_charge_mwh"),
                bess_discharge_mwh=bess.get("bess_discharge_mwh"),
                bess_avg_soc_mwh=bess.get("bess_avg_soc_mwh"),
                bess_net_revenue=bess.get("bess_net_revenue"),
                dispatch_mae_mw=metrics.get("dispatch_mae_mw"),
                dispatch_rmse_mw=metrics.get("dispatch_rmse_mw"),
                reference=reference,
                evaluated_at=datetime.now(timezone.utc) if reference else None,
            )
        )
    session.commit()
```

```python
# app/db/queries.py — append these two functions

def update_metric_set(
    session: Session, run_id: str, *, metrics: dict[str, float], reference: str
) -> MetricSet:
    """Overwrite a run's price metrics against an explicit reference.

    Keeps the dispatch columns (dispatch_mae_mw/dispatch_rmse_mw) untouched —
    they need the solved model, which post-hoc re-evaluation does not have.
    """
    ms = get_metric_set(session, run_id)
    if ms is None:
        ms = MetricSet(run_id=run_id)
    ms.rmse = metrics.get("rmse")
    ms.mae = metrics.get("mae")
    ms.bias = metrics.get("bias")
    ms.wape = metrics.get("wape")
    ms.smape = metrics.get("smape")
    ms.r2 = metrics.get("r2")
    ms.reference = reference
    ms.evaluated_at = datetime.now(timezone.utc)
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return ms


def list_visible_runs(session: Session, user_id: str) -> list[Run]:
    stmt = (
        select(Run)
        .where(or_(Run.user_id == user_id, Run.visibility == "public"))
        .order_by(Run.created_at.desc())
    )
    return list(session.scalars(stmt))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_queries.py tests/test_db_claim.py tests/test_worker_main.py -q`
Expected: PASS — existing `create_case_and_run` callers pass `user_id=` explicitly; the new default does not change them.

- [ ] **Step 5: Commit**

```bash
git add app/db/queries.py tests/test_db_queries.py
git commit -m "feat(db): support system runs with nullable user_id and visibility/input_grade"
```

---

### Task 4: `queries.py` — run_plans CRUD

**Files:**
- Modify: `app/db/queries.py`
- Modify: `tests/test_db_run_plans.py`

**Interfaces:**
- Consumes: `RunPlan` model (Task 1).
- Produces:
  - `create_run_plan(session, *, kind: str, target_date: date_, due_at: datetime) -> RunPlan`
  - `get_run_plan(session, kind: str, target_date: date_) -> RunPlan | None`
  - `list_claimable_plans(session, *, now: datetime, max_attempts: int) -> list[RunPlan]` — `status in ("pending", "failed")`, `due_at <= now`, and (`status == "pending"` or `attempts < max_attempts`); ordered `due_at`, `created_at`.
  - `mark_plan_done(session, plan, *, run_id: str | None = None) -> None` — `done`, `finished_at=now`; `run_id` stays None for reeval kinds.
  - `mark_plan_failed(session, plan, *, error: str, run_id: str | None = None, retry_at: datetime | None = None) -> None` — `failed` + `error` (+ optional `run_id`); `due_at=retry_at` and `finished_at` unset when a retry is scheduled; `finished_at=now` on terminal failure (`retry_at is None`).
  - `mark_plan_skipped(session, plan, *, reason: str) -> None` — `skipped`, `error=reason`, `finished_at=now`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db_run_plans.py — append (add `from app.db import queries` to imports)

def _plan(session, kind="preideal_daily", target=date(2026, 9, 10), due=None):
    if due is None:
        due = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)
    return queries.create_run_plan(session, kind=kind, target_date=target, due_at=due)


def test_create_and_get_run_plan():
    session = _session()
    plan = _plan(session)
    fetched = queries.get_run_plan(session, "preideal_daily", date(2026, 9, 10))
    assert fetched is not None
    assert fetched.id == plan.id
    assert queries.get_run_plan(session, "preideal_daily", date(2026, 9, 11)) is None


def test_list_claimable_plans_filters_status_attempts_and_due():
    session = _session()
    now = datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc)
    due = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)
    pending = _plan(session, kind="preideal_daily", due=due)
    future = _plan(
        session,
        kind="ideal_daily",
        target=date(2026, 9, 10),
        due=datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc),
    )
    terminal = _plan(session, kind="reeval_preideal", due=due)
    queries.mark_plan_failed(session, terminal, error="intentos agotados", retry_at=None)
    retryable = _plan(session, kind="reeval_ideal", target=date(2026, 9, 11), due=due)
    queries.mark_plan_failed(session, retryable, error="boom", retry_at=due)

    claimable = {
        p.id for p in queries.list_claimable_plans(session, now=now, max_attempts=3)
    }
    assert pending.id in claimable
    assert future.id not in claimable
    assert terminal.id not in claimable
    assert retryable.id in claimable


def test_plan_status_transitions():
    session = _session()
    plan = _plan(session)
    queries.mark_plan_done(session, plan, run_id="run-1")
    assert plan.status == "done"
    assert plan.run_id == "run-1"
    assert plan.finished_at is not None

    plan2 = _plan(session, kind="ideal_daily")
    retry = datetime(2026, 9, 9, 21, 15, tzinfo=timezone.utc)
    queries.mark_plan_failed(session, plan2, error="boom", retry_at=retry)
    assert plan2.status == "failed"
    assert plan2.error == "boom"
    assert plan2.due_at == retry
    assert plan2.finished_at is None

    plan3 = _plan(session, kind="reeval_preideal", target=date(2026, 9, 11))
    queries.mark_plan_skipped(session, plan3, reason="insumos no publicados")
    assert plan3.status == "skipped"
    assert plan3.error == "insumos no publicados"
    assert plan3.finished_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_run_plans.py -q`
Expected: FAIL — `AttributeError: module 'app.db.queries' has no attribute 'create_run_plan'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/db/queries.py — extend the models import:

from app.db.models import Case, InputDataset, MetricSet, NodalResult, Run, RunPlan, Scenario

# append:

def create_run_plan(
    session: Session, *, kind: str, target_date: date_, due_at: datetime
) -> RunPlan:
    row = RunPlan(kind=kind, target_date=target_date, due_at=due_at)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_run_plan(session: Session, kind: str, target_date: date_) -> RunPlan | None:
    stmt = select(RunPlan).where(
        RunPlan.kind == kind, RunPlan.target_date == target_date
    )
    return session.scalars(stmt).first()


def list_claimable_plans(
    session: Session, *, now: datetime, max_attempts: int
) -> list[RunPlan]:
    stmt = (
        select(RunPlan)
        .where(
            RunPlan.due_at <= now,
            RunPlan.status.in_(["pending", "failed"]),
            or_(RunPlan.status == "pending", RunPlan.attempts < max_attempts),
        )
        .order_by(RunPlan.due_at, RunPlan.created_at)
    )
    return list(session.scalars(stmt))


def mark_plan_done(session: Session, plan: RunPlan, *, run_id: str | None = None) -> None:
    plan.status = "done"
    plan.run_id = run_id
    plan.finished_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()


def mark_plan_failed(
    session: Session,
    plan: RunPlan,
    *,
    error: str,
    run_id: str | None = None,
    retry_at: datetime | None = None,
) -> None:
    plan.status = "failed"
    plan.error = error
    if run_id is not None:
        plan.run_id = run_id
    if retry_at is not None:
        plan.due_at = retry_at
    else:
        plan.finished_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()


def mark_plan_skipped(session: Session, plan: RunPlan, *, reason: str) -> None:
    plan.status = "skipped"
    plan.error = reason
    plan.finished_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_run_plans.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/db/queries.py tests/test_db_run_plans.py
git commit -m "feat(db): add run_plans CRUD and status transitions"
```

---

### Task 5: `claim.py` — locked claim-by-id for runs and run_plans

**Files:**
- Modify: `app/db/claim.py`
- Modify: `tests/test_db_claim.py`

**Interfaces:**
- Consumes: `RunPlan`/`Run` models; existing dialect-guard pattern (`app/db/claim.py` docstring: postgres-only locking lives here and only here).
- Produces:
  - `_locked(stmt, session)` (module-private) — applies `with_for_update(skip_locked=True)` only when `session.bind.dialect.name == "postgresql"`; unit-tested via monkeypatch so the postgres branch is verified without a postgres server.
  - `claim_run_by_id(session, run_id: str) -> Run | None` — pending run → `running` + `started_at`; `None` when already claimed/missing.
  - `claim_run_plan_by_id(session, plan_id: str) -> RunPlan | None` — plan in `("pending", "failed")` → `running` + `started_at` + `attempts += 1` (one increment per claim = one execution attempt, matching spec §6.2's retry accounting); `None` when already claimed/missing.
  - `claim_next_pending_run` keeps its exact current behavior (reimplemented through `_locked`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db_claim.py — extend imports:
# from app.db.claim import _locked, claim_next_pending_run, claim_run_by_id, claim_run_plan_by_id
# from app.db.models import Base, Run, RunPlan
# from sqlalchemy import create_engine, select  (select is needed by the lock test)
# from datetime import datetime, timezone

def test_claim_run_by_id_claims_pending_run():
    session = _session()
    run = _make_pending_run(session)
    claimed = claim_run_by_id(session, run.id)
    assert claimed is not None
    assert claimed.id == run.id
    assert claimed.status == "running"
    assert claimed.started_at is not None


def test_claim_run_by_id_returns_none_for_running_or_missing():
    session = _session()
    run = _make_pending_run(session)
    claim_run_by_id(session, run.id)
    assert claim_run_by_id(session, run.id) is None
    assert claim_run_by_id(session, "does-not-exist") is None


def test_claim_plan_marks_running_and_increments_attempts():
    session = _session()
    plan = RunPlan(
        kind="preideal_daily",
        target_date=date(2026, 9, 10),
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
    )
    session.add(plan)
    session.commit()

    claimed = claim_run_plan_by_id(session, plan.id)
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.started_at is not None
    # a running plan cannot be claimed twice
    assert claim_run_plan_by_id(session, plan.id) is None


def test_claim_plan_reclaims_failed_plan_below_max_attempts():
    session = _session()
    plan = RunPlan(
        kind="ideal_daily",
        target_date=date(2026, 9, 10),
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
        status="failed",
        attempts=1,
    )
    session.add(plan)
    session.commit()
    claimed = claim_run_plan_by_id(session, plan.id)
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 2


def test_lock_applied_only_on_postgresql_dialect():
    from types import SimpleNamespace

    session = _session()
    stmt = select(RunPlan).where(RunPlan.id == "x")
    locked = _locked(stmt, session)
    assert "FOR UPDATE" not in str(locked).upper()  # sqlite: no lock clause

    session.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    locked = _locked(stmt, session)
    assert "FOR UPDATE" in str(locked).upper()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_claim.py -q`
Expected: FAIL — `AttributeError: module 'app.db.claim' has no attribute 'claim_run_by_id'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/db/claim.py — full replacement (claim_next_pending_run semantics unchanged)

"""Postgres-only locking lives here, and only here: `FOR UPDATE SKIP LOCKED`
is what lets more than one worker replica claim rows safely without
stepping on each other. SQLite's dialect doesn't support that clause at
all, so on SQLite (tests, single process) it's simply never added --
there's nothing broken by its absence since SQLite doesn't run concurrent
worker replicas anyway."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Run, RunPlan


def _locked(stmt, session: Session):
    """Apply the postgres-only row lock; unchanged on every other dialect."""
    if session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    return stmt


def claim_next_pending_run(session: Session) -> Run | None:
    stmt = select(Run).where(Run.status == "pending").order_by(Run.created_at).limit(1)
    run = session.scalars(_locked(stmt, session)).first()
    if run is None:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    session.commit()
    return run


def claim_run_by_id(session: Session, run_id: str) -> Run | None:
    """Claim one specific pending run (used by the plan executor right after
    creating it). Returns None if another worker claimed it first."""
    stmt = select(Run).where(Run.id == run_id, Run.status == "pending")
    run = session.scalars(_locked(stmt, session)).first()
    if run is None:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    session.commit()
    return run


def claim_run_plan_by_id(session: Session, plan_id: str) -> RunPlan | None:
    """Claim one run_plans row for execution.

    pending rows are claimable; failed rows are re-claimable (retry). The
    caller only lists failed rows whose attempts are below the max, and the
    attempt counter increments on every claim (one claim == one attempt).
    """
    stmt = select(RunPlan).where(
        RunPlan.id == plan_id, RunPlan.status.in_(["pending", "failed"])
    )
    plan = session.scalars(_locked(stmt, session)).first()
    if plan is None:
        return None
    plan.status = "running"
    plan.started_at = datetime.now(timezone.utc)
    plan.attempts += 1
    session.commit()
    return plan
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_claim.py -q`
Expected: PASS — the pre-existing `claim_next_pending_run` tests still pass (identical semantics via `_locked`).

- [ ] **Step 5: Commit**

```bash
git add app/db/claim.py tests/test_db_claim.py
git commit -m "feat(db): add locked claim-by-id for runs and run_plans"
```

---

### Task 6: `app/scheduler/` scaffold — `config.py` + `timeutil.py` (windows, tz, sweep helpers)

**Files:**
- Create: `app/scheduler/__init__.py`
- Create: `app/scheduler/config.py`
- Create: `app/scheduler/timeutil.py`
- Create: `tests/test_scheduler_timeutil.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `SchedulerConfig` — frozen dataclass, fields with spec §8 defaults: `daily_enabled: bool = True`, `scheduler_tz: str = "America/Bogota"`, `plan_tick_seconds: int = 60`, `plan_max_attempts: int = 3`, `plan_retry_minutes: int = 15`, `data_refresh_interval_minutes: int = 60`, `data_refresh_window_days: int = 7`, `sweep_time: str = "05:30"`, `reeval_preideal_time: str = "18:00"`, `daily_earliest: str = "15:00"`, `daily_deadline: str = "23:59"`.
  - `SchedulerConfig.from_env() -> SchedulerConfig` — reads `os.getenv("DAILY_ENABLED"|"SCHEDULER_TZ"|"PLAN_TICK_SECONDS"|"PLAN_MAX_ATTEMPTS"|"PLAN_RETRY_MINUTES"|"DATA_REFRESH_INTERVAL_MINUTES"|"DATA_REFRESH_WINDOW_DAYS"|"SWEEP_TIME"|"REEVAL_PREIDEAL_TIME"|"DAILY_EARLIEST"|"DAILY_DEADLINE")` with exactly those defaults (spec §8).
  - `timeutil.bogota_tz(tz_name: str) -> tzinfo`
  - `timeutil.in_tz(now: datetime, tz_name: str) -> datetime` — aware→aware conversion
  - `timeutil.tz_date(now: datetime, tz_name: str) -> date`
  - `timeutil.wall_to_utc(d: date, hhmm: str, tz_name: str) -> datetime` — Bogota wall time → UTC aware
  - `timeutil.window_edges(kind: str, target: date, config: SchedulerConfig) -> tuple[datetime | None, datetime | None]` — UTC-aware `(open, close)`; `None` = unbounded. `preideal_daily`/`ideal_daily`/`reeval_preideal` are windowed on the D-1 Bogota day; `reeval_ideal`/`lmp_settled`/`preideal_settled`/`ideal_settled` are open-ended (spec §4 + §12: execution by input availability, not fixed hour).
  - `timeutil.retry_due(now: datetime, config: SchedulerConfig) -> datetime`
  - `timeutil.sweep_due(now: datetime, config: SchedulerConfig, last_sweep_date: date | None) -> tuple[bool, date]` — fires once per Bogota day at/after `sweep_time`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_timeutil.py
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.scheduler.config import SchedulerConfig
from app.scheduler.timeutil import (
    in_tz,
    retry_due,
    sweep_due,
    tz_date,
    wall_to_utc,
    window_edges,
)

UTC = timezone.utc
BOG = ZoneInfo("America/Bogota")


def test_config_defaults_match_spec_section8():
    config = SchedulerConfig()
    assert config.daily_enabled is True
    assert config.scheduler_tz == "America/Bogota"
    assert config.plan_tick_seconds == 60
    assert config.plan_max_attempts == 3
    assert config.plan_retry_minutes == 15
    assert config.data_refresh_interval_minutes == 60
    assert config.data_refresh_window_days == 7
    assert config.sweep_time == "05:30"
    assert config.reeval_preideal_time == "18:00"
    assert config.daily_earliest == "15:00"
    assert config.daily_deadline == "23:59"


def test_config_from_env_uses_exact_defaults(monkeypatch):
    monkeypatch.delenv("DAILY_ENABLED", raising=False)
    monkeypatch.delenv("PLAN_MAX_ATTEMPTS", raising=False)
    config = SchedulerConfig.from_env()
    assert config.daily_enabled is True
    assert config.plan_max_attempts == 3

    monkeypatch.setenv("DAILY_ENABLED", "false")
    monkeypatch.setenv("PLAN_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("SWEEP_TIME", "06:00")
    config = SchedulerConfig.from_env()
    assert config.daily_enabled is False
    assert config.plan_max_attempts == 5
    assert config.sweep_time == "06:00"


def test_wall_to_utc():
    # Bogota is UTC-5, no DST
    utc = wall_to_utc(date(2026, 9, 8), "15:00", "America/Bogota")
    assert utc == datetime(2026, 9, 8, 20, 0, tzinfo=UTC)


def test_tz_date_and_in_tz():
    now = datetime(2026, 9, 9, 5, 30, tzinfo=UTC)
    assert tz_date(now, "America/Bogota") == date(2026, 9, 9)
    assert in_tz(now, "America/Bogota") == datetime(2026, 9, 9, 0, 30, tzinfo=BOG)


def test_window_edges_daily_kinds_on_previous_bogota_day():
    config = SchedulerConfig()
    target = date(2026, 9, 10)  # window is D-1 = 2026-09-09, 15:00-23:59 Bogota
    open_at, close_at = window_edges("preideal_daily", target, config)
    assert open_at == datetime(2026, 9, 9, 20, 0, tzinfo=UTC)  # 15:00 Bogota
    assert close_at == datetime(2026, 9, 10, 4, 59, 0, tzinfo=UTC)  # 23:59 Bogota
    assert window_edges("ideal_daily", target, config) == (open_at, close_at)


def test_window_edges_reeval_preideal_uses_reeval_time():
    config = SchedulerConfig()
    open_at, close_at = window_edges("reeval_preideal", date(2026, 9, 10), config)
    assert open_at == datetime(2026, 9, 9, 23, 0, tzinfo=UTC)  # 18:00 Bogota
    assert close_at == datetime(2026, 9, 10, 4, 59, 0, tzinfo=UTC)


def test_window_edges_open_ended_kinds_have_no_bounds():
    config = SchedulerConfig()
    for kind in ("reeval_ideal", "lmp_settled", "preideal_settled", "ideal_settled"):
        assert window_edges(kind, date(2026, 9, 10), config) == (None, None)


def test_retry_due_adds_retry_minutes():
    config = SchedulerConfig()
    now = datetime(2026, 9, 9, 21, 0, tzinfo=UTC)
    assert retry_due(now, config) == datetime(2026, 9, 9, 21, 15, tzinfo=UTC)


def test_sweep_due_fires_once_per_bogota_day():
    config = SchedulerConfig()
    before = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)  # 05:00 Bogota
    at_sweep = datetime(2026, 9, 9, 10, 30, tzinfo=UTC)  # 05:30 Bogota
    assert sweep_due(before, config, None) == (False, date(2026, 9, 9))
    due, day = sweep_due(at_sweep, config, None)
    assert due is True and day == date(2026, 9, 9)
    # already swept today -> no fire; yesterday -> fires again
    assert sweep_due(at_sweep, config, date(2026, 9, 9)) == (False, date(2026, 9, 9))
    assert sweep_due(at_sweep, config, date(2026, 9, 8))[0] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_timeutil.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/scheduler/__init__.py
"""Scheduler ticks for automated daily runs (spec 2026-09-08-daily-runs-design).
Pure, clock-injected functions; the worker loop is the only integration."""
```

```python
# app/scheduler/config.py
"""Env configuration for the daily scheduler.

Defaults are spec section 8 verbatim; every variable has a default so the
worker runs without any env setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True)
class SchedulerConfig:
    daily_enabled: bool = True
    scheduler_tz: str = "America/Bogota"
    plan_tick_seconds: int = 60
    plan_max_attempts: int = 3
    plan_retry_minutes: int = 15
    data_refresh_interval_minutes: int = 60
    data_refresh_window_days: int = 7
    sweep_time: str = "05:30"
    reeval_preideal_time: str = "18:00"
    daily_earliest: str = "15:00"
    daily_deadline: str = "23:59"

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        return cls(
            daily_enabled=_env_bool("DAILY_ENABLED", True),
            scheduler_tz=os.getenv("SCHEDULER_TZ", "America/Bogota"),
            plan_tick_seconds=_env_int("PLAN_TICK_SECONDS", 60),
            plan_max_attempts=_env_int("PLAN_MAX_ATTEMPTS", 3),
            plan_retry_minutes=_env_int("PLAN_RETRY_MINUTES", 15),
            data_refresh_interval_minutes=_env_int("DATA_REFRESH_INTERVAL_MINUTES", 60),
            data_refresh_window_days=_env_int("DATA_REFRESH_WINDOW_DAYS", 7),
            sweep_time=os.getenv("SWEEP_TIME", "05:30"),
            reeval_preideal_time=os.getenv("REEVAL_PREIDEAL_TIME", "18:00"),
            daily_earliest=os.getenv("DAILY_EARLIEST", "15:00"),
            daily_deadline=os.getenv("DAILY_DEADLINE", "23:59"),
        )
```

```python
# app/scheduler/timeutil.py
"""America/Bogota <-> UTC window math for plan kinds.

Window policy (documented for the orchestrator, see plan Notes):
- preideal_daily / ideal_daily: previous Bogota calendar day,
  DAILY_EARLIEST..DAILY_DEADLINE (spec section 4: D-1 15:00-23:59).
- reeval_preideal: same day, REEVAL_PREIDEAL_TIME..DAILY_DEADLINE (iMAR(D) is
  final by ~16:25 Bogota: published 09:00-13:40 with a ~165 min modification
  window, so 18:00 is safely past it).
- reeval_ideal / lmp_settled / preideal_settled / ideal_settled: open-ended —
  execution is input-driven, not wall-clock driven (spec section 12). They
  never auto-skip on time; deterministic input failures skip them with a
  closed reason from the inputs layer.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.scheduler.config import SchedulerConfig

UTC = timezone.utc

_WINDOWED_KINDS = ("preideal_daily", "ideal_daily", "reeval_preideal")


def bogota_tz(tz_name: str) -> tzinfo:
    return ZoneInfo(tz_name)


def in_tz(now: datetime, tz_name: str) -> datetime:
    """Convert an aware datetime into the scheduler zone (stays aware)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(bogota_tz(tz_name))


def tz_date(now: datetime, tz_name: str) -> date:
    return in_tz(now, tz_name).date()


def _parse_hhmm(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def wall_to_utc(d: date, hhmm: str, tz_name: str) -> datetime:
    """Interpret (d, hh:mm) as Bogota wall time and return UTC aware."""
    wall = datetime.combine(d, _parse_hhmm(hhmm), tzinfo=bogota_tz(tz_name))
    return wall.astimezone(UTC)


def window_edges(
    kind: str, target: date, config: SchedulerConfig
) -> tuple[datetime | None, datetime | None]:
    """UTC (open, close) for a plan (kind, target_date); None = unbounded.

    Daily kinds act on the day BEFORE target (the D-1 window of spec section
    4). The close instant is 23:59:00 Bogota — a 00:00 boundary would wrongly
    let the whole next day keep claiming.
    """
    if kind not in _WINDOWED_KINDS:
        return None, None
    prev = target - timedelta(days=1)
    earliest = (
        config.reeval_preideal_time if kind == "reeval_preideal" else config.daily_earliest
    )
    open_at = wall_to_utc(prev, earliest, config.scheduler_tz)
    close_at = wall_to_utc(prev, config.daily_deadline, config.scheduler_tz)
    return open_at, close_at


def retry_due(now: datetime, config: SchedulerConfig) -> datetime:
    return now + timedelta(minutes=config.plan_retry_minutes)


def sweep_due(
    now: datetime, config: SchedulerConfig, last_sweep_date: date | None
) -> tuple[bool, date]:
    """(fire, bogota_date) — fire once per Bogota day at/after sweep_time."""
    wall = in_tz(now, config.scheduler_tz)
    day = wall.date()
    if day == last_sweep_date:
        return False, day
    return wall.time() >= _parse_hhmm(config.sweep_time), day
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_timeutil.py -q`
Expected: PASS (the `23:59` close maps to next-day 04:59 UTC — matches the tests).

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/ tests/test_scheduler_timeutil.py
git commit -m "feat(scheduler): add config and Bogota/UTC window helpers"
```

---

### Task 7: `inputs.py` — input-availability predicates per plan kind

**Files:**
- Create: `app/scheduler/inputs.py`
- Create: `tests/test_scheduler_inputs.py`

**Interfaces:**
- Consumes: `resolve_input` (`app/data/paths.py`), loaders (`app/data/loaders.py`), `get_run_plan`/`get_run` (`app/db/queries.py`), `get_storage`.
- Produces:
  - `REASON_INPUTS = "insumos no publicados"`, `REASON_SOURCE_FAILED = "plan fuente fallido"` — the closed skip-reason vocabulary of spec §9.
  - `blobs_ready(dispatch_date: date, data_dir: str) -> bool` — every per-date blob kind (`OFEI`, `PrId`, `iMAR`, `dCondIniU`, `dCondIniP`, `dAGCUNIDAD`) resolves via `resolve_input`.
  - `series_max_date(series: str, year: int, data_dir: str) -> date | None` — max published day in the year CSV of `dispo_declarada|ofertas|demaCome|dispo_come|precio_bolsa`; `None` when missing/empty. Reads through the cached loaders (cheap after the freshness tick clears them).
  - `series_has_day(series: str, day: date, data_dir: str) -> bool`
  - `month_complete(series: str, month_start: date, data_dir: str) -> bool` — every calendar day of the month has ≥ 1 row.
  - `network_cached(data_dir: str) -> bool` — `topology/network.json` exists under the data dir.
  - `source_run_done(session, kind: str, target_date: date) -> bool` — plan row for `(kind, target_date)` has a `run_id` whose run is `done`.
  - `source_plan_terminal(session, kind: str, target_date: date) -> bool` — the source can never become done (plan row missing/skipped, or run row missing/failed/skipped).
  - `kind_inputs_ready(session, kind: str, target_date: date, *, data_dir: str) -> tuple[bool, str, bool]` — `(ready, reason, permanent)`. `permanent=True` means the condition can never become true → the caller skips the plan with `reason` instead of waiting for the window to close. Mapping (spec §4):
    - `preideal_daily`/`ideal_daily`: blobs of D + `dispo_declarada` rows up to D. demaCome(D)/ofertas(D) intentionally do NOT gate: on D-1 they do not exist — `build_case` falls back to PrId forecast demand and to the offer heuristic (spec §1, §4 provisional semantics).
    - `reeval_preideal`: source `preideal_daily` done + blobs of D (iMAR(D) blob is final by the 18:00 earliest).
    - `reeval_ideal`: source `ideal_daily` done + TX1 row for D in `precio_bolsa`.
    - `lmp_settled`: TX1(D) + real rows of D for `demaCome`/`dispo_declarada`/`ofertas` (what `app/nodal/runner.py` loads) + `network_cached`.
    - `preideal_settled`: real `ofertas` row for D + blobs of D.
    - `ideal_settled`: real rows of D for `ofertas` + `demaCome` + `dispo_come` + TX1(D) (inline evaluation scores against bolsa TX1 at run time).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_inputs.py
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base
from app.scheduler import inputs

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_blobs_ready_true_on_smoke_fixture():
    assert inputs.blobs_ready(FECHA, DD) is True
    assert inputs.blobs_ready(date(2024, 4, 17), DD) is False


def test_series_has_day_and_max_date():
    assert inputs.series_has_day("dispo_declarada", FECHA, DD) is True
    assert inputs.series_has_day("dispo_declarada", date(2024, 4, 19), DD) is False
    assert inputs.series_max_date("ofertas", 2024, DD) == FECHA
    assert inputs.series_max_date("no_such_series", 2024, DD) is None


def test_month_complete_false_when_fixture_month_partial():
    # the fixture only has 2024-04-18 rows -> April is not complete
    assert inputs.month_complete("ofertas", date(2024, 4, 1), DD) is False


def test_source_run_done_and_terminal():
    session = _session()
    assert inputs.source_run_done(session, "preideal_daily", FECHA) is False
    assert inputs.source_plan_terminal(session, "preideal_daily", FECHA) is True

    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    plan = queries.create_run_plan(
        session,
        kind="preideal_daily",
        target_date=FECHA,
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
    )
    queries.mark_plan_done(session, plan, run_id=run.id)
    assert inputs.source_run_done(session, "preideal_daily", FECHA) is False  # run pending
    run.status = "done"
    session.commit()
    assert inputs.source_run_done(session, "preideal_daily", FECHA) is True
    assert inputs.source_plan_terminal(session, "preideal_daily", FECHA) is False


def test_daily_kind_ready_on_fixture():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "preideal_daily", FECHA, data_dir=DD
    )
    assert ready is True
    assert reason == "" and permanent is False


def test_daily_kind_not_ready_without_blobs():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "ideal_daily", date(2024, 4, 17), data_dir=DD
    )
    assert ready is False
    assert reason == inputs.REASON_INPUTS
    assert permanent is False


def test_reeval_preideal_requires_source_done():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "reeval_preideal", FECHA, data_dir=DD
    )
    assert ready is False
    assert permanent is True  # no source plan row ever -> deterministic
    assert reason == inputs.REASON_SOURCE_FAILED


def test_settled_requires_real_month_rows_not_present_in_fixture():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "preideal_settled", FECHA, data_dir=DD
    )
    assert ready is False
    assert reason == inputs.REASON_INPUTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_inputs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler.inputs'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/scheduler/inputs.py
"""Input-availability predicates for plan kinds (spec section 4).

Every predicate answers: "can a run for (kind, target_date) produce a
meaningful result right now?" — blobs published, year CSVs with rows up to
the needed day, source plan done for reeval kinds. File checks go through
the real loaders (lru-cached; the freshness tick clears them after every
rewrite). Reasons use the closed vocabulary of spec section 9.

Note: `dispo_declarada` rows up to D is the only year-series requirement of
the fresh daily lanes — demaCome(D)/ofertas(D) do not exist on D-1 by
design (spec section 1: ideal falls back to the PrId forecast, offers are
estimated by the heuristic).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.data import loaders
from app.data.paths import resolve_input
from app.db import queries
from app.storage import get_storage

REASON_INPUTS = "insumos no publicados"
REASON_SOURCE_FAILED = "plan fuente fallido"

BLOB_KINDS = ("OFEI", "PrId", "iMAR", "dCondIniU", "dCondIniP", "dAGCUNIDAD")

_SERIES_LOADER = {
    "dispo_declarada": loaders.load_dispo,
    "ofertas": loaders.load_ofertas,
    "demaCome": loaders.load_demanda,
    "dispo_come": loaders.load_dispo_come,
    "precio_bolsa": loaders.load_precio_bolsa,
}


def _days(series: str, df) -> set[date]:
    """Distinct published calendar days in a loader frame."""
    col = df["Date"].dt.date if series == "ofertas" else df["datetime"].dt.date
    return set(col)


def blobs_ready(dispatch_date: date, data_dir: str) -> bool:
    for kind in BLOB_KINDS:
        try:
            resolve_input(kind, dispatch_date, data_dir)
        except FileNotFoundError:
            return False
    return True


def series_max_date(series: str, year: int, data_dir: str) -> date | None:
    """Max published day in the year CSV of `series` (explicit year: callers
    pull for the year of their end day; tests use fixture years)."""
    loader = _SERIES_LOADER.get(series)
    if loader is None:
        return None
    try:
        df = loader(data_dir, year)
    except FileNotFoundError:
        return None
    if df.empty:
        return None
    return max(_days(series, df))


def series_has_day(series: str, day: date, data_dir: str) -> bool:
    loader = _SERIES_LOADER.get(series)
    if loader is None:
        return False
    try:
        df = loader(data_dir, day.year)
    except FileNotFoundError:
        return False
    return day in _days(series, df)


def month_complete(series: str, month_start: date, data_dir: str) -> bool:
    """True when every calendar day of month_start's month has a row."""
    loader = _SERIES_LOADER.get(series)
    if loader is None:
        return False
    try:
        df = loader(data_dir, month_start.year)
    except FileNotFoundError:
        return False
    days = _days(series, df)
    if month_start.month == 12:
        end = date(month_start.year + 1, 1, 1)
    else:
        end = date(month_start.year, month_start.month + 1, 1)
    return all((month_start + timedelta(days=i)) in days for i in range((end - month_start).days))


def network_cached(data_dir: str) -> bool:
    return get_storage(data_dir).exists("topology/network.json")


def source_run_done(session, kind: str, target_date: date) -> bool:
    plan = queries.get_run_plan(session, kind, target_date)
    if plan is None or plan.run_id is None:
        return False
    run = queries.get_run(session, plan.run_id)
    return run is not None and run.status == "done"


def source_plan_terminal(session, kind: str, target_date: date) -> bool:
    """True when (kind, target) can never produce a done source run."""
    plan = queries.get_run_plan(session, kind, target_date)
    if plan is None or plan.status == "skipped":
        return True
    if plan.status == "failed":
        run = queries.get_run(session, plan.run_id) if plan.run_id else None
        return run is None or run.status in ("failed", "skipped")
    return False  # pending / running / done


def kind_inputs_ready(
    session, kind: str, target_date: date, *, data_dir: str
) -> tuple[bool, str, bool]:
    """(ready, reason, permanent) for (kind, target_date).

    permanent=True means the condition can never become true -> the caller
    skips the plan with `reason` instead of waiting for the window to close.
    """
    if kind in ("preideal_daily", "ideal_daily"):
        ok = blobs_ready(target_date, data_dir) and series_has_day(
            "dispo_declarada", target_date, data_dir
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    if kind == "reeval_preideal":
        if source_run_done(session, "preideal_daily", target_date):
            ok = blobs_ready(target_date, data_dir)
            return (ok, "" if ok else REASON_INPUTS, False)
        terminal = source_plan_terminal(session, "preideal_daily", target_date)
        return (False, REASON_SOURCE_FAILED, terminal)

    if kind == "reeval_ideal":
        if source_run_done(session, "ideal_daily", target_date):
            ok = series_has_day("precio_bolsa", target_date, data_dir)
            return (ok, "" if ok else REASON_INPUTS, False)
        terminal = source_plan_terminal(session, "ideal_daily", target_date)
        return (False, REASON_SOURCE_FAILED, terminal)

    if kind == "lmp_settled":
        ok = (
            series_has_day("precio_bolsa", target_date, data_dir)
            and series_has_day("demaCome", target_date, data_dir)
            and series_has_day("dispo_declarada", target_date, data_dir)
            and series_has_day("ofertas", target_date, data_dir)
            and network_cached(data_dir)
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    if kind == "preideal_settled":
        ok = series_has_day("ofertas", target_date, data_dir) and blobs_ready(
            target_date, data_dir
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    if kind == "ideal_settled":
        ok = (
            series_has_day("ofertas", target_date, data_dir)
            and series_has_day("demaCome", target_date, data_dir)
            and series_has_day("dispo_come", target_date, data_dir)
            and series_has_day("precio_bolsa", target_date, data_dir)
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    raise ValueError(f"unknown plan kind: {kind}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_inputs.py -q`
Expected: PASS. (The fixture has no `topology/network.json`, so the lmp predicate simply returns False there — not asserted in these tests.)

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/inputs.py tests/test_scheduler_inputs.py
git commit -m "feat(scheduler): add per-kind input availability predicates"
```

---

### Task 8: `plans.py` — plan-row creation ticks (daily ensure, TX1 sweep, monthly gate)

**Files:**
- Create: `app/scheduler/plans.py`
- Create: `tests/test_scheduler_plans.py`

**Interfaces:**
- Consumes: `queries` CRUD (Task 4), `timeutil` (Task 6), `inputs` (Task 7).
- Produces:
  - `KIND_LEVEL: dict[str, str]` — `preideal_daily→preideal`, `ideal_daily→ideal`, `preideal_settled→preideal`, `ideal_settled→ideal`, `lmp_settled→lmp`.
  - `KIND_INPUT_GRADE: dict[str, str]` — daily kinds → `provisional`; settled/lmp kinds → `settled`.
  - `ensure_daily_plans(session, *, now: datetime, config) -> int` — creates (when missing) `preideal_daily`, `ideal_daily`, `reeval_preideal` rows for tomorrow's Bogota date; `due_at = max(window open, now)` so a late worker start still runs in-window; returns rows created.
  - `sweep_create_rows(session, *, now: datetime, config, data_dir: str) -> int` — called at/after `SWEEP_TIME` once per Bogota day: for dates in the last `_SWEEP_LOOKBACK_DAYS = 7` Bogota days that have a TX1 row, creates missing `lmp_settled`/`reeval_ideal` rows (`due_at=now`); also heals a `reeval_preideal` row a downed night never created (source done + blob present). Lookback is a code constant, not env config — it prevents a historical backfill stampede on first deploy (TX1 dates older than ~7 days predate the feature).
  - `create_settled_rows_for_month(session, *, month_start: date, config, due_at: datetime) -> int` — creates `preideal_settled`/`ideal_settled` rows for every day of the month (missing only), `due_at` given (the gate's now); rows pend until TX1/reals arrive (open-ended kinds).
  - `next_settlement_month(session, *, now: datetime, config, data_dir: str) -> date | None` — most recent calendar month before the current Bogota month whose `ofertas` series is complete; the monthly gate fires when it becomes non-None after a pull.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_plans.py
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base, RunPlan
from app.scheduler.config import SchedulerConfig
from app.scheduler.plans import (
    KIND_INPUT_GRADE,
    KIND_LEVEL,
    create_settled_rows_for_month,
    ensure_daily_plans,
    next_settlement_month,
    sweep_create_rows,
)

UTC = timezone.utc
CONFIG = SchedulerConfig()
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _kinds(session, target):
    rows = session.scalars(
        select(RunPlan).where(RunPlan.target_date == target)
    ).all()
    return {row.kind for row in rows}


def test_kind_metadata_maps_to_level_and_grade():
    assert KIND_LEVEL["preideal_daily"] == "preideal"
    assert KIND_LEVEL["ideal_daily"] == "ideal"
    assert KIND_LEVEL["lmp_settled"] == "lmp"
    assert KIND_INPUT_GRADE["preideal_daily"] == "provisional"
    assert KIND_INPUT_GRADE["ideal_settled"] == "settled"


def test_ensure_daily_plans_creates_tomorrow_rows_once():
    session = _session()
    # 2026-09-08 20:00 UTC == 2026-09-08 15:00 Bogota (window open for D=09-09)
    now = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    created = ensure_daily_plans(session, now=now, config=CONFIG)
    assert created == 3
    assert _kinds(session, date(2026, 9, 9)) == {
        "preideal_daily", "ideal_daily", "reeval_preideal",
    }
    assert ensure_daily_plans(session, now=now, config=CONFIG) == 0


def test_ensure_daily_plans_due_at_is_window_open_when_before_open():
    session = _session()
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)  # 07:00 Bogota, before 15:00
    ensure_daily_plans(session, now=now, config=CONFIG)
    plan = queries.get_run_plan(session, "preideal_daily", date(2026, 9, 9))
    assert plan.due_at == datetime(2026, 9, 8, 20, 0, tzinfo=UTC)  # 15:00 Bogota


def test_ensure_daily_plans_due_at_now_when_late():
    session = _session()
    now = datetime(2026, 9, 8, 23, 0, tzinfo=UTC)  # 18:00 Bogota, after open
    ensure_daily_plans(session, now=now, config=CONFIG)
    plan = queries.get_run_plan(session, "ideal_daily", date(2026, 9, 9))
    assert plan.due_at == now


def test_sweep_create_rows_creates_lmp_and_reeval_ideal_for_tx1_dates():
    session = _session()
    # fixture precio_bolsa has TX1 for 2024-04-18; 2024-04-21 10:30 UTC is
    # 05:30 Bogota on 04-21 -> 04-18 is inside the 7-day lookback
    now = datetime(2024, 4, 21, 10, 30, tzinfo=UTC)
    created = sweep_create_rows(session, now=now, config=CONFIG, data_dir=DD)
    assert created == 2  # lmp_settled(04-18) + reeval_ideal(04-18)
    assert queries.get_run_plan(session, "lmp_settled", date(2024, 4, 18)) is not None
    assert queries.get_run_plan(session, "reeval_ideal", date(2024, 4, 18)) is not None
    assert sweep_create_rows(session, now=now, config=CONFIG, data_dir=DD) == 0


def test_create_settled_rows_for_month_creates_every_day_once():
    session = _session()
    due = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)
    created = create_settled_rows_for_month(
        session, month_start=date(2024, 3, 1), config=CONFIG, due_at=due
    )
    assert created == 60  # 30 days x 2 kinds
    assert queries.get_run_plan(session, "preideal_settled", date(2024, 3, 15)) is not None
    assert queries.get_run_plan(session, "ideal_settled", date(2024, 3, 31)) is not None
    again = create_settled_rows_for_month(
        session, month_start=date(2024, 3, 1), config=CONFIG, due_at=due
    )
    assert again == 0


def test_next_settlement_month_requires_complete_previous_month():
    # fixture ofertas only covers 2024-04-18 -> no complete month before April
    session = _session()
    now = datetime(2024, 5, 10, 12, 0, tzinfo=UTC)
    assert next_settlement_month(session, now=now, config=CONFIG, data_dir=DD) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_plans.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler.plans'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/scheduler/plans.py
"""Plan-row creation: daily lanes, TX1 sweep, monthly settled gate.

Creation is event-driven but idempotent: rows are created once per
(kind, target_date) (schema UNIQUE) and then live through the claim/retry/
expiry machine of tick.py. The sweep lookback is a code constant, not env
config: TX1 dates older than ~7 days predate this feature and would flood
the worker with a historical backfill on first deploy.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.db import queries
from app.scheduler import inputs, timeutil

_SWEEP_LOOKBACK_DAYS = 7

KIND_LEVEL = {
    "preideal_daily": "preideal",
    "ideal_daily": "ideal",
    "preideal_settled": "preideal",
    "ideal_settled": "ideal",
    "lmp_settled": "lmp",
}

KIND_INPUT_GRADE = {
    "preideal_daily": "provisional",
    "ideal_daily": "provisional",
    "preideal_settled": "settled",
    "ideal_settled": "settled",
    "lmp_settled": "settled",
}

_DAILY_KINDS = ("preideal_daily", "ideal_daily", "reeval_preideal")


def ensure_daily_plans(session, *, now: datetime, config) -> int:
    """Create tomorrow's daily + reeval_preideal rows if missing."""
    if not config.daily_enabled:
        return 0
    target = timeutil.tz_date(now, config.scheduler_tz) + timedelta(days=1)
    created = 0
    for kind in _DAILY_KINDS:
        if queries.get_run_plan(session, kind, target) is not None:
            continue
        open_at, _close = timeutil.window_edges(kind, target, config)
        due_at = now if open_at is None or now > open_at else open_at
        queries.create_run_plan(session, kind=kind, target_date=target, due_at=due_at)
        created += 1
    return created


def sweep_create_rows(session, *, now: datetime, config, data_dir: str) -> int:
    """Create lmp_settled/reeval_ideal rows for TX1 dates; heal reeval_preideal.

    Called at/after SWEEP_TIME once per Bogota day (worker wiring decides).
    Only dates inside the last _SWEEP_LOOKBACK_DAYS Bogota days are considered
    (TX1 publishes D+2..D+4, so a fresh date is never dropped).
    """
    if not config.daily_enabled:
        return 0
    created = 0
    today = timeutil.tz_date(now, config.scheduler_tz)
    for offset in range(1, _SWEEP_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=offset)
        has_tx1 = inputs.series_has_day("precio_bolsa", day, data_dir)
        if has_tx1:
            for kind in ("lmp_settled", "reeval_ideal"):
                if queries.get_run_plan(session, kind, day) is None:
                    queries.create_run_plan(session, kind=kind, target_date=day, due_at=now)
                    created += 1
        if (
            queries.get_run_plan(session, "reeval_preideal", day) is None
            and inputs.source_run_done(session, "preideal_daily", day)
        ):
            queries.create_run_plan(session, kind="reeval_preideal", target_date=day, due_at=now)
            created += 1
    return created


def _month_days(month_start: date) -> list[date]:
    if month_start.month == 12:
        end = date(month_start.year + 1, 1, 1)
    else:
        end = date(month_start.year, month_start.month + 1, 1)
    return [month_start + timedelta(days=i) for i in range((end - month_start).days)]


def create_settled_rows_for_month(
    session, *, month_start: date, config, due_at: datetime
) -> int:
    """Create preideal_settled/ideal_settled rows for every day of the month."""
    if not config.daily_enabled:
        return 0
    created = 0
    for day in _month_days(month_start):
        for kind in ("preideal_settled", "ideal_settled"):
            if queries.get_run_plan(session, kind, day) is None:
                queries.create_run_plan(session, kind=kind, target_date=day, due_at=due_at)
                created += 1
    return created


def next_settlement_month(session, *, now: datetime, config, data_dir: str) -> date | None:
    """Most recent complete calendar month before the current Bogota month.

    A month publishes ~1st of the next month; the gate fires after the pull
    that completes it. Only months strictly before the current one count.
    """
    today = timeutil.tz_date(now, config.scheduler_tz)
    first = date(today.year, today.month, 1) - timedelta(days=1)  # last day of prev month
    cursor = date(first.year, first.month, 1)
    while cursor >= date(today.year - 1, 1, 1):
        if inputs.month_complete("ofertas", cursor, data_dir):
            return cursor
        cursor = (
            date(cursor.year - 1, 12, 1)
            if cursor.month == 1
            else date(cursor.year, cursor.month - 1, 1)
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_plans.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/plans.py tests/test_scheduler_plans.py
git commit -m "feat(scheduler): create daily, TX1-sweep and monthly-gate plan rows"
```

---

### Task 9: `reeval.py` — metric re-evaluation without re-solving

**Files:**
- Create: `app/scheduler/reeval.py`
- Create: `tests/test_scheduler_reeval.py`

**Interfaces:**
- Consumes: `queries.update_metric_set`/`get_metric_set`/`get_case` (Task 3), `load_actual_price`/`load_actual_bolsa` (`app/data/actuals.py`), `price_metrics` (`app/utils/metrics.py`), `get_storage`; `run.price_path` is the saved model MPO CSV (columns `datetime`, `ideal_marginal_price`).
- Produces:
  - `REEVAL_SOURCE_KIND = {"reeval_preideal": "preideal_daily", "reeval_ideal": "ideal_daily"}`
  - `REEVAL_REFERENCE = {"reeval_preideal": "iMAR", "reeval_ideal": "bolsa_tx1"}`
  - `reevaluate_metrics(session, run, *, reference: str, data_dir: str = "data") -> dict[str, float]` — reads the run's price CSV (sorted by datetime), aligns against the reference actual (`iMAR` → `load_actual_price`, `bolsa_tx1` → `load_actual_bolsa`), computes `price_metrics`, overwrites the price columns of the run's `metric_set`, stamps `reference`/`evaluated_at`. Raises `ValueError`/`FileNotFoundError` when the price CSV or the actual is missing — the plan executor turns that into a failed plan with a readable error.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_reeval.py
from datetime import date, timezone
from pathlib import Path

import pandas as pd

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base
from app.schemas import DispatchCase, DispatchLevel, RunResult
from app.scheduler.reeval import (
    REEVAL_REFERENCE,
    REEVAL_SOURCE_KIND,
    reevaluate_metrics,
)

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _done_run(session, tmp_path, level=DispatchLevel.preideal):
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level=level.value,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    out = tmp_path / "results" / run.id
    out.mkdir(parents=True)
    hours = pd.date_range("2024-04-18", periods=24, freq="h")
    pd.DataFrame(
        {"datetime": hours, "ideal_marginal_price": [180000.0] * 24}
    ).to_csv(out / "price.csv", index=False)
    result = RunResult(
        case=DispatchCase(dispatch_date=FECHA, level=level),
        ok=True,
        price_path=str(out / "price.csv"),
        metrics={"mae": 30000.0},
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out))
    return run


def test_reeval_metadata_maps():
    assert REEVAL_SOURCE_KIND == {
        "reeval_preideal": "preideal_daily",
        "reeval_ideal": "ideal_daily",
    }
    assert REEVAL_REFERENCE == {"reeval_preideal": "iMAR", "reeval_ideal": "bolsa_tx1"}


def test_reevaluate_metrics_against_imar_stamps_reference(tmp_path):
    session = _session()
    run = _done_run(session, tmp_path)
    metrics = reevaluate_metrics(session, run, reference="iMAR", data_dir=DD)
    assert metrics["mae"] == 30000.0  # 180000 model vs 150000 iMAR fixture
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference == "iMAR"
    assert ms.evaluated_at is not None
    assert ms.mae == 30000.0
    assert ms.rmse == 30000.0


def test_reevaluate_metrics_against_bolsa_stamps_reference(tmp_path):
    session = _session()
    run = _done_run(session, tmp_path, level=DispatchLevel.ideal)
    metrics = reevaluate_metrics(session, run, reference="bolsa_tx1", data_dir=DD)
    # fixture precio_bolsa raw COP/kWh = 200 -> loader scales x1e3 -> 200000.0
    assert metrics["mae"] == 20000.0
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference == "bolsa_tx1"


def test_reevaluate_metrics_raises_when_price_csv_missing(tmp_path):
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    try:
        reevaluate_metrics(session, run, reference="iMAR", data_dir=DD)
        assert False, "expected an exception"
    except ValueError as exc:
        assert "precio" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_reeval.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler.reeval'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/scheduler/reeval.py
"""Re-evaluate a finished run's metrics against the final reference without
re-solving (spec sections 2 and 3.3): iMAR(D) final for preideal, bolsa
TX1(D) for ideal. Overwrites the same metric_set row (unique per run),
stamping reference + evaluated_at so a provisional-vs-iMAR score is never
mistaken for a settled-vs-TX1 one. Dispatch columns are kept: they need the
solved model, which post-hoc re-evaluation does not have.
"""

from __future__ import annotations

import pandas as pd

from app.data.actuals import load_actual_bolsa, load_actual_price
from app.db import queries
from app.storage import get_storage
from app.utils.metrics import price_metrics

REEVAL_SOURCE_KIND = {
    "reeval_preideal": "preideal_daily",
    "reeval_ideal": "ideal_daily",
}

REEVAL_REFERENCE = {
    "reeval_preideal": "iMAR",
    "reeval_ideal": "bolsa_tx1",
}

_ACTUAL_BY_REFERENCE = {
    "iMAR": load_actual_price,
    "bolsa_tx1": load_actual_bolsa,
}


def _model_mpo(run) -> list[float]:
    if run.price_path is None:
        raise ValueError("run tiene price_path nulo; no hay precio modelo que reevaluar")
    with get_storage(".").open(run.price_path) as f:
        price_df = pd.read_csv(f, parse_dates=["datetime"]).sort_values("datetime")
    return price_df["ideal_marginal_price"].astype(float).tolist()


def reevaluate_metrics(session, run, *, reference: str, data_dir: str = "data") -> dict[str, float]:
    actual_fn = _ACTUAL_BY_REFERENCE.get(reference)
    if actual_fn is None:
        raise ValueError(f"referencia desconocida: {reference!r}")
    model_mpo = _model_mpo(run)
    case = queries.get_case(session, run.case_id)
    if case is None:
        raise ValueError(f"run {run.id} sin case")
    xm = actual_fn(case.dispatch_date, data_dir=data_dir)
    n = min(len(xm), len(model_mpo))
    metrics = price_metrics(xm[:n], model_mpo[:n])
    queries.update_metric_set(session, run.id, metrics=metrics, reference=reference)
    return metrics
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_reeval.py -q`
Expected: PASS — fixture iMAR MPO = 150000.0 COP/MWh; raw bolsa = 200 COP/kWh → 200000.0 COP/MWh after the loader's ×1e3.

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/reeval.py tests/test_scheduler_reeval.py
git commit -m "feat(scheduler): re-evaluate run metrics against iMAR or bolsa TX1"
```

---

### Task 10: `executor.py` — shared `execute_run` + plan/reeval execution

**Files:**
- Create: `app/scheduler/executor.py`
- Modify: `services/worker/main.py` (`process_once` delegates to `execute_run`; `_build_case` moves to the executor)
- Create: `tests/test_scheduler_executor.py`

**Interfaces:**
- Consumes: `run_case` (`app/pipeline/runner.py`), `queries` (Tasks 3-4), `claim_run_by_id` (Task 5), `reeval` (Task 9), `timeutil` (Task 6), `get_storage`, `KIND_LEVEL`/`KIND_INPUT_GRADE` (Task 8).
- Produces:
  - `_build_case(session, case_row) -> DispatchCase` — moved verbatim from `services/worker/main.py`.
  - `execute_run(session, run, *, data_dir: str = "data", results_root: str = "data/results") -> None` — the exact body of today's `process_once` after its claim (case build, nodal network JSON write, idle-commit, log capture, `run_case(case, evaluate=True, ...)`, log write, `finish_run_ok`/`finish_nodal_run_ok`/`finish_run_failed`, exception isolation). Never raises; sets the run's final status.
  - `execute_plan(session, plan, *, now: datetime, config, data_dir: str = "data", results_root: str = "data/results") -> None` — creates the run row (`create_case_and_run` with `user_id=None`, `visibility="public"`, `input_grade` from the kind map, `solver="cbc"`, `compute_prices=True`; for `lmp`, loads `data_dir/topology/network.json` into `cases.nodal_network`), claims it by id, runs `execute_run`, then records `done` (with `run_id`) or `failed` on the plan. Failures with attempts left schedule `due_at = now + PLAN_RETRY_MINUTES`; `attempts >= PLAN_MAX_ATTEMPTS` is terminal (`finished_at` set). May raise only before the run is claimed (e.g. missing network file) — the tick catches and records the failure.
  - `execute_reeval(session, plan, *, now: datetime, config, data_dir: str = "data") -> None` — resolves the source plan/run from `REEVAL_SOURCE_KIND`, calls `reevaluate_metrics`, marks the plan `done` (no `run_id`). Failures (missing run, unparseable files) raise; the tick records them with the same retry accounting.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_executor.py
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base
from app.scheduler.config import SchedulerConfig
from app.scheduler.executor import execute_plan

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
CONFIG = SchedulerConfig()
NOW = datetime(2024, 4, 17, 22, 0, tzinfo=timezone.utc)  # 17:00 Bogota, in window


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_execute_plan_runs_system_public_run_and_marks_done(tmp_path, monkeypatch):
    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)

    session = _session()
    plan = queries.create_run_plan(
        session, kind="preideal_daily", target_date=FECHA, due_at=NOW
    )
    results_root = str(tmp_path / "results")
    execute_plan(
        session, plan, now=NOW, config=CONFIG,
        data_dir=DD, results_root=results_root,
    )
    session.expire_all()
    assert plan.status == "done"
    assert plan.run_id is not None

    run = queries.get_run(session, plan.run_id)
    assert run is not None
    assert run.status == "done"
    assert run.user_id is None
    assert run.visibility == "public"
    assert run.input_grade == "provisional"
    ms = queries.get_metric_set(session, run.id)
    assert ms is not None  # fixture iMAR exists -> inline metrics computed
    assert ms.mae == 30000.0  # model MPO 180000 vs fixture iMAR 150000


def test_execute_plan_marks_failed_with_retry_when_run_fails(tmp_path, monkeypatch):
    session = _session()
    plan = queries.create_run_plan(
        session, kind="ideal_daily", target_date=FECHA, due_at=NOW
    )

    def _boom(session, run, *, data_dir="data", results_root="data/results"):
        run.status = "failed"
        run.error = "solve exploded"
        session.commit()

    monkeypatch.setattr("app.scheduler.executor.execute_run", _boom)
    execute_plan(
        session, plan, now=NOW, config=CONFIG,
        data_dir=DD, results_root=str(tmp_path / "results"),
    )
    assert plan.status == "failed"
    assert plan.error == "solve exploded"
    assert plan.run_id is not None
    # attempts (0) < PLAN_MAX_ATTEMPTS -> retry scheduled 15 minutes out
    assert plan.due_at == datetime(2024, 4, 17, 22, 15, tzinfo=timezone.utc)
    assert plan.finished_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_executor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler.executor'`.

- [ ] **Step 3: Write the executor and rewire `process_once`**

```python
# app/scheduler/executor.py
"""Execution half of the scheduler: shared solve path + plan/reeval execution.

execute_run is the body of the worker's process_once after its claim,
extracted so the plan tick executes plan runs through the exact same path
(log capture, finish_run_ok/nodal/failed). Plan runs are system runs:
user_id NULL, visibility public, input_grade per kind.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import traceback
from datetime import datetime

from app.db import queries
from app.db.claim import claim_run_by_id
from app.pipeline.runner import run_case
from app.schemas import BessScenario, DispatchCase, DispatchLevel
from app.storage import get_storage

from app.scheduler import reeval, timeutil
from app.scheduler.plans import KIND_INPUT_GRADE, KIND_LEVEL


def _build_case(session, case_row) -> DispatchCase:
    scenario = None
    if case_row.scenario_id is not None:
        scenario_row = queries.get_scenario(session, case_row.scenario_id)
        scenario = BessScenario(
            mode=scenario_row.mode,
            penetration_level=scenario_row.penetration_level,
            units=scenario_row.units,
        )
    return DispatchCase(
        dispatch_date=case_row.dispatch_date,
        level=DispatchLevel(case_row.level),
        solver=case_row.solver,
        compute_prices=case_row.compute_prices,
        bess_scenario=scenario,
    )


def execute_run(session, run, *, data_dir: str = "data", results_root: str = "data/results") -> None:
    """Solve one claimed run to completion; never raises."""
    out_dir = f"{results_root}/{run.id}"
    log_path = f"{out_dir}/run.log"

    try:
        case_row = queries.get_case(session, run.case_id)
        case = _build_case(session, case_row)

        if case_row.nodal_network:
            network_path = f"{out_dir}/network.json"
            with get_storage(".").open(network_path, "w") as f:
                json.dump(case_row.nodal_network, f)
            case.nodal_network = network_path

        # Close the read-only transaction _build_case's queries opened so the
        # session sits idle for the duration of the solve (see worker main.py).
        session.commit()

        log_buffer = io.StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)
        try:
            with contextlib.redirect_stdout(log_buffer), contextlib.redirect_stderr(log_buffer):
                result = run_case(
                    case, evaluate=True, out=out_dir, data_dir=data_dir, session=session
                )
        finally:
            root_logger.removeHandler(log_handler)

        with contextlib.suppress(OSError):
            with get_storage(".").open(log_path, "w") as f:
                f.write(log_buffer.getvalue())
            run.log_path = log_path

        if result.ok:
            if result.nodal is not None:
                queries.finish_nodal_run_ok(session, run, result, out_dir=out_dir)
            else:
                queries.finish_run_ok(session, run, result, out_dir=out_dir)
        else:
            queries.finish_run_failed(
                session, run, result.error or "unknown error", log_path=log_path
            )
    except Exception as exc:
        session.rollback()
        try:
            queries.finish_run_failed(session, run, f"{type(exc).__name__}: {exc}")
        except Exception:
            traceback.print_exc()


def execute_plan(
    session,
    plan,
    *,
    now: datetime,
    config,
    data_dir: str = "data",
    results_root: str = "data/results",
) -> None:
    """Create, claim and solve the run for a run-producing plan kind."""
    level = KIND_LEVEL[plan.kind]
    grade = KIND_INPUT_GRADE[plan.kind]
    nodal_network = None
    if level == DispatchLevel.lmp:
        with get_storage(data_dir).open("topology/network.json") as fh:
            nodal_network = json.load(fh)

    run = queries.create_case_and_run(
        session,
        dispatch_date=plan.target_date,
        level=level.value,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        nodal_network=nodal_network,
        visibility="public",
        input_grade=grade,
    )
    claimed = claim_run_by_id(session, run.id)
    if claimed is None:
        queries.mark_plan_failed(
            session,
            plan,
            error="run reclamado por otro worker",
            retry_at=timeutil.retry_due(now, config),
        )
        return

    execute_run(session, claimed, data_dir=data_dir, results_root=results_root)

    if claimed.status == "done":
        queries.mark_plan_done(session, plan, run_id=claimed.id)
    else:
        error = claimed.error or "unknown error"
        if plan.attempts >= config.plan_max_attempts:
            queries.mark_plan_failed(session, plan, error=error, run_id=claimed.id)
        else:
            queries.mark_plan_failed(
                session,
                plan,
                error=error,
                run_id=claimed.id,
                retry_at=timeutil.retry_due(now, config),
            )


def execute_reeval(session, plan, *, now: datetime, config, data_dir: str = "data") -> None:
    """Re-evaluate the source run's metric_set against its final reference."""
    source_kind = reeval.REEVAL_SOURCE_KIND[plan.kind]
    reference = reeval.REEVAL_REFERENCE[plan.kind]
    source = queries.get_run_plan(session, source_kind, plan.target_date)
    if source is None or source.run_id is None:
        queries.mark_plan_failed(
            session,
            plan,
            error="plan fuente sin run",
            retry_at=timeutil.retry_due(now, config),
        )
        return
    run = queries.get_run(session, source.run_id)
    if run is None:
        raise ValueError(f"plan fuente {source_kind} sin run {source.run_id}")
    reeval.reevaluate_metrics(session, run, reference=reference, data_dir=data_dir)
    queries.mark_plan_done(session, plan)
```

Note: `execute_reeval` intentionally raises on an unresolvable source run — the plan tick (Task 11) wraps both executors in the same try/except and applies the shared retry/terminal accounting, so failures here follow the same policy as solve failures.

```python
# services/worker/main.py — replace the whole file content

import time
import traceback
from datetime import datetime, timezone

from app.db.claim import claim_next_pending_run
from app.db.session import get_engine, get_sessionmaker
from app.scheduler.executor import execute_run

POLL_INTERVAL_SECONDS = 5


def process_once(
    session, *, data_dir: str = "data", results_root: str = "data/results"
) -> bool:
    run = claim_next_pending_run(session)
    if run is None:
        return False
    execute_run(session, run, data_dir=data_dir, results_root=results_root)
    return True


def main() -> None:
    engine = get_engine()
    session_factory = get_sessionmaker(engine)
    while True:
        with session_factory() as session:
            try:
                processed = process_once(session)
            except Exception:
                traceback.print_exc()
                processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
```

Note: Task 19 re-adds the scheduler wiring and `main_iteration`; this task only moves the solve body out so plan execution can share it. `process_once` semantics are unchanged (test `test_process_once_solves_pending_run_end_to_end` in `tests/test_worker_main.py` must still pass).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_executor.py tests/test_worker_main.py -q`
Expected: PASS — executor tests solve the 2-generator fixture with cbc (a few seconds), and the worker tests still pass against the extracted path.

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/executor.py services/worker/main.py tests/test_scheduler_executor.py
git commit -m "feat(scheduler): extract shared execute_run and add plan/reeval executors"
```

---

### Task 11: `tick.py` — `plan_tick`: claim, execute, expire

**Files:**
- Create: `app/scheduler/tick.py`
- Create: `tests/test_scheduler_tick.py`

**Interfaces:**
- Consumes: `list_claimable_plans`/`mark_plan_*` (Task 4), `claim_run_plan_by_id` (Task 5), `timeutil` (Task 6), `inputs` (Task 7), `ensure_daily_plans` (Task 8), `executor` (Task 10), `reeval` metadata (Task 9).
- Produces:
  - `plan_tick(session, *, now: datetime, config, data_dir: str = "data", results_root: str = "data/results") -> int` — one scheduler pass:
    1. returns 0 when `config.daily_enabled` is False (kill switch);
    2. calls `ensure_daily_plans` (tomorrow's rows);
    3. walks `list_claimable_plans` in `due_at` order: window closed (`now > close_at`) → `mark_plan_skipped("ventana vencida")`; window not open yet → skip; inputs not ready → skip, or `mark_plan_skipped(reason)` when `permanent`; otherwise `claim_run_plan_by_id` (None → another replica won) and dispatch to `execute_plan`/`execute_reeval`, catching any exception into `mark_plan_failed` with the retry/terminal accounting;
    4. executes at most ONE plan per tick (the solve blocks the loop; the worker re-enters every `PLAN_TICK_SECONDS`) — returns 1 when a plan was executed/expired-to-skipped, else 0.
  - Policy note (documented): a `pending` plan whose whole window passed while the worker was down is `skipped` with `"ventana vencida"` on the first tick after wake — the auditable-evidence behavior of spec §3.1. Open-ended kinds (`reeval_ideal`, `lmp_settled`, `*_settled`) never expire on time; deterministic input failures skip them via the `permanent` path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_tick.py
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base, RunPlan
from app.scheduler import tick
from app.scheduler.config import SchedulerConfig

UTC = timezone.utc
CONFIG = SchedulerConfig()
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")

NOW_OPEN = datetime(2026, 9, 8, 21, 0, tzinfo=UTC)  # D-1 16:00 Bogota, window open
TARGET = date(2026, 9, 9)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _plan_row(session, kind="preideal_daily", target=TARGET, status="pending",
              attempts=0, due=NOW_OPEN):
    plan = RunPlan(
        kind=kind, target_date=target, status=status, attempts=attempts,
        due_at=due,
    )
    session.add(plan)
    session.commit()
    return plan


def test_plan_tick_returns_zero_when_disabled():
    session = _session()
    config = SchedulerConfig(daily_enabled=False)
    assert tick.plan_tick(session, now=NOW_OPEN, config=config) == 0
    rows = session.scalars(select(RunPlan)).all()
    assert rows == []


def test_plan_tick_claims_and_dispatches_one_plan(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    executed = []

    def _fake_execute_plan(session, plan, *, now, config, data_dir, results_root):
        executed.append(plan.kind)
        queries.mark_plan_done(session, plan, run_id="run-1")

    monkeypatch.setattr(tick.executor, "execute_plan", _fake_execute_plan)
    monkeypatch.setattr(
        tick.inputs, "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),
    )
    plan = _plan_row(session)

    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)

    assert result == 1
    assert executed == ["preideal_daily"]
    session.expire_all()
    assert plan.status == "done"
    assert plan.run_id == "run-1"
    assert plan.attempts == 1  # claimed once


def test_plan_tick_skips_expired_window_with_reason(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    plan = _plan_row(session, kind="ideal_daily", due=NOW_OPEN)
    now_after_close = datetime(2026, 9, 9, 5, 30, tzinfo=UTC)  # 00:30 Bogota D
    monkeypatch.setattr(
        tick.inputs, "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),  # would be ready -> expiry, not inputs
    )
    result = tick.plan_tick(session, now=now_after_close, config=CONFIG, data_dir=DD)
    assert result == 0
    session.expire_all()
    assert plan.status == "skipped"
    assert plan.error == "ventana vencida"


def test_plan_tick_waits_when_inputs_missing_not_permanent(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    plan = _plan_row(session)
    monkeypatch.setattr(
        tick.inputs, "kind_inputs_ready",
        lambda *a, **kw: (False, "insumos no publicados", False),
    )
    monkeypatch.setattr(tick.executor, "execute_plan", lambda *a, **kw: 1 / 0)
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 0
    session.expire_all()
    assert plan.status == "pending"  # untouched, retried next tick


def test_plan_tick_skips_permanent_input_failure(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    plan = _plan_row(session)
    monkeypatch.setattr(
        tick.inputs, "kind_inputs_ready",
        lambda *a, **kw: (False, "plan fuente fallido", True),
    )
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 0
    session.expire_all()
    assert plan.status == "skipped"
    assert plan.error == "plan fuente fallido"


def test_plan_tick_records_execution_exception_with_retry(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    plan = _plan_row(session)

    def _raise(session, plan, *, now, config, data_dir, results_root):
        raise RuntimeError("solve exploded")

    monkeypatch.setattr(tick.executor, "execute_plan", _raise)
    monkeypatch.setattr(
        tick.inputs, "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),
    )
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 1
    session.expire_all()
    assert plan.status == "failed"
    assert plan.error == "RuntimeError: solve exploded"
    assert plan.due_at == datetime(2026, 9, 8, 21, 15, tzinfo=UTC)  # retry +15 min
    assert plan.finished_at is None


def test_plan_tick_marks_terminal_failure_at_max_attempts(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    plan = _plan_row(session, status="failed", attempts=2, due=NOW_OPEN)

    def _raise(session, plan, *, now, config, data_dir, results_root):
        raise RuntimeError("solve exploded")

    monkeypatch.setattr(tick.executor, "execute_plan", _raise)
    monkeypatch.setattr(
        tick.inputs, "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),
    )
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 1
    session.expire_all()
    assert plan.status == "failed"
    assert plan.attempts == 3
    assert plan.finished_at is not None  # terminal: no retry
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_tick.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler.tick'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/scheduler/tick.py
"""The plan tick: windows -> inputs -> claim -> execute (one plan per pass).

Policy documented for the orchestrator (plan Notes): at most one plan per
tick because a plan run solves inline and blocks the worker loop; the loop
re-enters every PLAN_TICK_SECONDS. Windowed kinds that age out while the
worker is down become `skipped` with reason "ventana vencida" on the first
tick after wake (auditable evidence, spec section 3.1). Open-ended kinds
never expire on time — deterministic input failures skip them via the
`permanent` path from inputs.kind_inputs_ready.
"""

from __future__ import annotations

from datetime import datetime

from app.db import queries
from app.db.claim import claim_run_plan_by_id
from app.scheduler import executor, inputs, reeval, timeutil
from app.scheduler.plans import ensure_daily_plans


def plan_tick(
    session,
    *,
    now: datetime,
    config,
    data_dir: str = "data",
    results_root: str = "data/results",
) -> int:
    """One plan-tick pass; executes at most one plan. Returns 1 when it did."""
    if not config.daily_enabled:
        return 0
    ensure_daily_plans(session, now=now, config=config)

    for plan in queries.list_claimable_plans(
        session, now=now, max_attempts=config.plan_max_attempts
    ):
        open_at, close_at = timeutil.window_edges(plan.kind, plan.target_date, config)
        if close_at is not None and now > close_at:
            queries.mark_plan_skipped(session, plan, reason="ventana vencida")
            continue
        if open_at is not None and now < open_at:
            continue

        ready, reason, permanent = inputs.kind_inputs_ready(
            session, plan.kind, plan.target_date, data_dir=data_dir
        )
        if not ready:
            if permanent:
                queries.mark_plan_skipped(session, plan, reason=reason)
            continue

        claimed = claim_run_plan_by_id(session, plan.id)
        if claimed is None:
            continue  # another replica claimed it first
        try:
            if claimed.kind in reeval.REEVAL_SOURCE_KIND:
                executor.execute_reeval(
                    session, claimed, now=now, config=config, data_dir=data_dir
                )
            else:
                executor.execute_plan(
                    session,
                    claimed,
                    now=now,
                    config=config,
                    data_dir=data_dir,
                    results_root=results_root,
                )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if claimed.attempts >= config.plan_max_attempts:
                queries.mark_plan_failed(session, claimed, error=error)
            else:
                queries.mark_plan_failed(
                    session,
                    claimed,
                    error=error,
                    retry_at=timeutil.retry_due(now, config),
                )
        return 1
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_tick.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/tick.py tests/test_scheduler_tick.py
git commit -m "feat(scheduler): plan tick with claim, expiry and retry accounting"
```

---

### Task 12: `loaders.py` — `clear_loader_caches`

**Files:**
- Modify: `app/data/loaders.py`
- Modify: `tests/test_loaders.py`

**Interfaces:**
- Consumes: the five year-level `functools.lru_cache(maxsize=16)` loaders.
- Produces: `clear_loader_caches() -> None` — calls `.cache_clear()` on `load_dispo`, `load_ofertas`, `load_demanda`, `load_precio_bolsa`, `load_dispo_come`. The freshness tick (Task 14) calls it after every rewrite, or the same worker process would keep reading the stale CSV (spec §5.1, critical).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loaders.py — append. The file imports individual functions
# (`from app.data.loaders import load_demanda, load_dispo, ...`); add
# `clear_loader_caches` to that existing import list (no new module import).

def test_clear_loader_caches_empties_year_loader_caches(tmp_path):
    sub = tmp_path / "dispo_declarada"
    sub.mkdir()
    (sub / "dispo_declarada_2024.csv").write_text(
        "datetime,resource_name,dispo,gen_type\n"
    )
    load_dispo(str(tmp_path), 2024)
    assert load_dispo.cache_info().currsize >= 1
    clear_loader_caches()
    assert load_dispo.cache_info().currsize == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loaders.py::test_clear_loader_caches_empties_year_loader_caches -q`
Expected: FAIL — `ImportError: cannot import name 'clear_loader_caches'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/loaders.py — append

def clear_loader_caches() -> None:
    """Invalidate the year-level CSV caches.

    The freshness tick rewrites the year CSVs in place; without clearing
    these caches the same worker process would keep reading the stale file
    (spec 2026-09-08-daily-runs, section 5.1).
    """
    for loader in (load_dispo, load_ofertas, load_demanda, load_precio_bolsa, load_dispo_come):
        loader.cache_clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loaders.py -q`
Expected: PASS (the new test plus the pre-existing cache tests, which still pass unchanged).

- [ ] **Step 5: Commit**

```bash
git add app/data/loaders.py tests/test_loaders.py
git commit -m "feat(data): add clear_loader_caches for year CSV invalidation"
```

---

### Task 13: `xm_bulk.py` — windowed incremental refresh (keyed merge + full rewrite)

**Files:**
- Modify: `app/data/xm_bulk.py`
- Modify: `tests/test_xm_bulk.py`

**Interfaces:**
- Consumes: existing `_melt_hourly`, `upsert_input_dataset`, pydataxm `ReadDB` shapes; existing one-shot `ensure_*` functions (kept as bootstrap/backfill, now delegating to the refresh core).
- Produces (one per real series, all single-year ranges; `crosswalk` is `None` for the system series):
  - `_read_year_csv(storage, rel_path: str) -> pd.DataFrame | None`
  - `_rewrite_year_csv(storage, rel_path: str, df: pd.DataFrame) -> None` — full rewrite through `storage.open(path, "w")`; the caller (`refresh_tick`) clears the loaders right after. The Storage protocol has no rename primitive, so "atomic" is: complete in-memory merge then one full write, single writer (see plan Notes).
  - `_merge_keyed(existing: pd.DataFrame | None, fresh: pd.DataFrame, keys: list[str]) -> pd.DataFrame` — concat, `drop_duplicates(subset=keys, keep="last")` (fresh rows overwrite existing rows with the same key — spec §5.1), sort by the time column, reset index. Idempotent: re-pulling the same window does not duplicate.
  - `refresh_dispo_declarada(start, end, data_dir, consult, crosswalk, session=None)`, `refresh_dispo_come(...)`, `refresh_dema_come(...)`, `refresh_precio_bolsa(...)`, `refresh_ofertas(...)` — request the window via `consult.request_data`, reshape exactly like the current `ensure_*` (hourly `_melt_hourly` per-resource with crosswalk / system; `PrecOferDesp` daily rows `Date,resource_name,Value`), merge into the existing year CSV, rewrite, `upsert_input_dataset` when `session` given.
  - The one-shot `ensure_*` functions delegate to the refresh core: `if storage.exists(path): return` guard stays, then refresh over `[Jan 1 .. Dec 31]` of the year — identical output to today, no duplicated fetch code.
- Merge semantics per spec §5.1: keys are `["datetime", "resource_name"]` for per-resource hourly series, `["datetime"]` for system hourly series (`demaCome`, `precio_bolsa`), `["Date", "resource_name"]` for `ofertas`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_xm_bulk.py — append

from datetime import timedelta

def test_merge_keyed_dedupes_keep_last_and_sorts():
    existing = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2024-04-17 00:00", "2024-04-17 01:00"]),
            "resource_name": ["A", "A"],
            "dispo": [100.0, 110.0],
        }
    )
    fresh = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2024-04-17 00:00", "2024-04-18 00:00"]),
            "resource_name": ["A", "A"],
            "dispo": [999.0, 120.0],
        }
    )
    out = _merge_keyed(existing, fresh, ["datetime", "resource_name"])
    assert len(out) == 3  # 17:00 row overwritten by fresh, no duplicate
    row = out[out["datetime"] == pd.Timestamp("2024-04-17 00:00")].iloc[0]
    assert row["dispo"] == 999.0  # fresh wins on key collision
    assert (out["datetime"] == out["datetime"].sort_values()).all()


class _FakeConsultWindow:
    """ReadDB stand-in: returns two hourly days for the requested range."""

    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.calls = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.calls.append((coleccion, metrica, start_date, end_date))
        if coleccion == "ListadoRecursos":
            return pd.DataFrame(
                {
                    "Values_Code": ["2QEK", "3ENA"],
                    "Values_Name": ["SALTO II", "TERMO NORTE"],
                    "Values_Type": ["HIDRAULICA", "TERMICA"],
                }
            )
        days = [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]
        rows = []
        for day in days:
            rows.append({"Values_code": "2QEK", "Date": day})
            rows.append({"Values_code": "3ENA", "Date": day})
        df = pd.DataFrame(rows)
        for h in range(1, 25):
            df[f"Values_Hour{h:02d}"] = 300.0
        return df


def test_refresh_dispo_declarada_is_idempotent_and_merges(tmp_path):
    from app.data import loaders as loaders_mod
    from app.data.xm_bulk import refresh_dispo_declarada

    start, end = date(2024, 4, 17), date(2024, 4, 19)
    consult = _FakeConsultWindow(start, end)
    crosswalk = pd.DataFrame(
        {"code": ["2QEK", "3ENA"], "resource_name": ["SALTO II", "TERMO NORTE"],
         "gen_type": ["HIDRAULICA", "TERMICA"]}
    )
    data_dir = str(tmp_path)
    sub = tmp_path / "dispo_declarada"
    sub.mkdir()
    first_day = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "resource_name": ["SALTO II"] * 24,
            "dispo": [100.0] * 24,
            "gen_type": ["HIDRAULICA"] * 24,
        }
    )
    first_day.to_csv(sub / "dispo_declarada_2024.csv", index=False)

    refresh_dispo_declarada(start, end, data_dir, consult, crosswalk)
    df = loaders_mod.load_dispo(data_dir, 2024)
    assert df["datetime"].dt.date.max() == date(2024, 4, 19)
    assert len(df) == 144  # 3 days x 2 resources x 24h

    # the keyed merge overwrote the stale local 04-17 value (100.0 -> 300.0)
    row = df[(df["datetime"].dt.date == date(2024, 4, 17))
             & (df["resource_name"] == "SALTO II")].iloc[0]
    assert row["dispo"] == 300.0

    # second identical pull must not duplicate rows
    refresh_dispo_declarada(start, end, data_dir, consult, crosswalk)
    df2 = loaders_mod.load_dispo(data_dir, 2024)
    assert len(df2) == 144
    assert consult.calls.count(("DispoDeclarada", "Recurso", start, end)) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xm_bulk.py -q`
Expected: FAIL — `ImportError: cannot import name '_merge_keyed'` / `refresh_dispo_declarada`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/xm_bulk.py — append the shared core

def _read_year_csv(storage, rel_path: str) -> pd.DataFrame | None:
    if not storage.exists(rel_path):
        return None
    with storage.open(rel_path, "rb") as f:
        return pd.read_csv(f)


def _rewrite_year_csv(storage, rel_path: str, df: pd.DataFrame) -> None:
    """Full rewrite through Storage. Single writer: the caller (refresh_tick)
    invalidates the loader caches right after the rewrite."""
    with storage.open(rel_path, "w") as f:
        df.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")


def _merge_keyed(
    existing: pd.DataFrame | None, fresh: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    """Keyed merge: existing rows are overwritten by fresh rows with the same
    key, new rows are appended, the file content is rewritten complete."""
    if existing is None or existing.empty:
        merged = fresh
    else:
        merged = pd.concat([existing, fresh], ignore_index=True)
    merged = merged.drop_duplicates(subset=keys, keep="last")
    time_col = keys[0]
    return merged.sort_values(time_col).reset_index(drop=True)


def _merge_into_year_csv(
    storage, rel_path: str, fresh: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    merged = _merge_keyed(_read_year_csv(storage, rel_path), fresh, keys)
    _rewrite_year_csv(storage, rel_path, merged)
    return merged
```

```python
# app/data/xm_bulk.py — replace each ensure_* body with the guard + a call to its
# refresh_* twin, and add the five refresh functions (single-year ranges)

def _year_range(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def refresh_dispo_declarada(
    start: date, end: date, data_dir: str, consult, crosswalk: pd.DataFrame, session=None
) -> None:
    storage = get_storage(data_dir)
    rel_path = f"dispo_declarada/dispo_declarada_{start.year}.csv"
    raw = consult.request_data("DispoDeclarada", "Recurso", start, end)
    fresh = _melt_hourly(raw, "dispo").merge(crosswalk, on="code", how="inner")[
        ["datetime", "resource_name", "dispo", "gen_type"]
    ]
    merged = _merge_into_year_csv(
        storage, rel_path, fresh, keys=["datetime", "resource_name"]
    )
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_declarada",
            partition_key=str(start.year),
            source="pydataxm:DispoDeclarada",
            row_count=len(merged),
        )


def ensure_dispo_declarada(year, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"dispo_declarada/dispo_declarada_{year}.csv"):
        return
    refresh_dispo_declarada(*_year_range(year), data_dir, consult, crosswalk, session)
```

The other four series follow the same shape — refresh + one-shot guard pair each, with these exact differences (keep the reshape identical to today's `ensure_*` output columns):

```python
# dispo_come (per-resource hourly, no gen_type; loaders.load_dispo_come columns)
def refresh_dispo_come(start, end, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    rel_path = f"dispo_come/dispo_come_{start.year}.csv"
    raw = consult.request_data("DispoCome", "Recurso", start, end)
    fresh = _melt_hourly(raw, "dispo").merge(crosswalk, on="code", how="inner")[
        ["datetime", "resource_name", "dispo"]
    ]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime", "resource_name"])
    if session is not None:
        upsert_input_dataset(
            session, dataset="dispo_come", partition_key=str(start.year),
            source="pydataxm:DispoCome", row_count=len(merged),
        )


def ensure_dispo_come(year, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"dispo_come/dispo_come_{year}.csv"):
        return
    refresh_dispo_come(*_year_range(year), data_dir, consult, crosswalk, session)


# demaCome (system hourly, key datetime)
def refresh_dema_come(start, end, data_dir, consult, crosswalk=None, session=None) -> None:
    """crosswalk is accepted for interface uniformity; DemaCome is a system
    series and never needs it."""
    storage = get_storage(data_dir)
    rel_path = f"demaCome/demaCome_{start.year}.csv"
    raw = consult.request_data("DemaCome", "Sistema", start, end)
    fresh = _melt_hourly(raw, "dema")[["datetime", "dema"]]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime"])
    if session is not None:
        upsert_input_dataset(
            session, dataset="demaCome", partition_key=str(start.year),
            source="pydataxm:DemaCome", row_count=len(merged),
        )


def ensure_dema_come(year, data_dir, consult, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"demaCome/demaCome_{year}.csv"):
        return
    refresh_dema_come(*_year_range(year), data_dir, consult, session=session)


# precio_bolsa (system hourly, key datetime)
def refresh_precio_bolsa(start, end, data_dir, consult, crosswalk=None, session=None) -> None:
    """crosswalk is accepted for interface uniformity; PrecBolsNaci is a
    system series and never needs it."""
    storage = get_storage(data_dir)
    rel_path = f"precio_bolsa/precio_bolsa_{start.year}.csv"
    raw = consult.request_data("PrecBolsNaci", "Sistema", start, end)
    fresh = _melt_hourly(raw, "precio_bolsa")[["datetime", "precio_bolsa"]]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime"])
    if session is not None:
        upsert_input_dataset(
            session, dataset="precio_bolsa", partition_key=str(start.year),
            source="pydataxm:PrecBolsNaci", row_count=len(merged),
        )


def ensure_precio_bolsa(year, data_dir, consult, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"precio_bolsa/precio_bolsa_{year}.csv"):
        return
    refresh_precio_bolsa(*_year_range(year), data_dir, consult, session=session)


# ofertas (PrecOferDesp, daily rows, key Date + resource_name)
def refresh_ofertas(start, end, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    rel_path = f"ofertas/ofertas_{start.year}.csv"
    raw = consult.request_data("PrecOferDesp", "Recurso", start, end)
    daily = raw.rename(columns={"Values_code": "code", "Values_Hour01": "Value"})
    daily = daily[["code", "Date", "Value"]]
    fresh = daily.merge(crosswalk, on="code", how="inner")[["Date", "resource_name", "Value"]]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["Date", "resource_name"])
    if session is not None:
        upsert_input_dataset(
            session, dataset="ofertas", partition_key=str(start.year),
            source="pydataxm:PrecOferDesp", row_count=len(merged),
        )


def ensure_ofertas(year, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"ofertas/ofertas_{year}.csv"):
        return
    refresh_ofertas(*_year_range(year), data_dir, consult, crosswalk, session)
```

Note on datetime formats: existing year CSVs are written with `date_format="%Y-%m-%d %H:%M:%S"` (see the current `ensure_*`), so `_rewrite_year_csv` keeps that exact format — the loaders parse it back losslessly. If a local CSV was written by an older tool with a different datetime string, `pd.to_csv` on the merged frame normalizes it; existing smoke fixtures already use this format.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_xm_bulk.py -q`
Expected: PASS — the pre-existing one-shot tests keep passing (guards unchanged, delegation produces identical files), plus the new merge/idempotency tests. The `input_datasets` manifest keeps the original short `source` strings (`pydataxm:DispoDeclarada`, etc. — provenance of the dataset, not of the window), so existing manifest assertions stay valid.

- [ ] **Step 5: Run the loader smoke tests**

Run: `uv run pytest tests/test_xm_smoke_loaders.py tests/test_xm_smoke_build_case.py -q`
Expected: PASS — fixture CSVs untouched by this task.

- [ ] **Step 6: Commit**

```bash
git add app/data/xm_bulk.py tests/test_xm_bulk.py
git commit -m "feat(data): incremental keyed-merge refresh for the five XM year series"
```

---

### Task 14: `refresh.py` — freshness tick + monthly gate

**Files:**
- Create: `app/scheduler/refresh.py`
- Create: `tests/test_scheduler_refresh.py`

**Interfaces:**
- Consumes: `xm_bulk.refresh_*` (Task 13), `clear_loader_caches` (Task 12), `inputs` (Task 7), `plans.next_settlement_month`/`create_settled_rows_for_month` (Task 8), `ReadDB` (`pydataxm`), `SchedulerConfig`.
- Produces:
  - `refresh_tick(session, *, now: datetime, config, data_dir: str = "data", consult=None) -> int` — one freshness pass (returns settled rows created by the gate):
    1. returns 0 when `config.daily_enabled` is False;
    2. `end_day = Bogota today − 1` (never the same day: series rows for today are incomplete, and the per-date blobs for D are published during D-1);
    3. per series, `pull_start = min(today − DATA_REFRESH_WINDOW_DAYS, last_local_day + 1)` when the local year CSV exists, else `today − window` — this is the plan's resolution of spec §5.1: a fixed 7-day window can never capture a month that publishes as one block ~1st of the next month (spec §1 evidence for PrecOferDesp), while `last_local + 1` reaches back to the day after the last merged row, so the whole block arrives on the first pull after publication. Documented in Notes for orchestrator;
    4. splits the range per calendar year and calls the matching `xm_bulk.refresh_*` (crosswalk fetched once when any per-resource series is pulled), then `clear_loader_caches()` once;
    5. monthly gate: `next_settlement_month` → when a complete month appeared, `create_settled_rows_for_month(..., due_at=now)` and return its row count.
  - `consult` is injectable for tests (default `ReadDB()`).
- Pull cadence is the worker's business (Task 19, `DATA_REFRESH_INTERVAL_MINUTES`); this function does one pass.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler_refresh.py
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.data import loaders as loaders_mod
from app.db import queries
from app.db.models import Base, RunPlan
from app.scheduler import refresh as refresh_mod
from app.scheduler.config import SchedulerConfig

UTC = timezone.utc
CONFIG = SchedulerConfig()
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


class _FakeConsult:
    """ReadDB stand-in that answers whatever range it is asked for.

    Shape per collection matches what the real pydataxm payloads look like:
    system hourly series get one code per day, per-resource series get two
    (both codes resolve through the crosswalk), PrecOferDesp is daily.
    """

    def __init__(self, start: date, end: date):
        self.start = start
        self.end = end
        self.asked = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.asked.append((coleccion, start_date, end_date))
        if coleccion == "ListadoRecursos":
            return pd.DataFrame(
                {
                    "Values_Code": ["2QEK", "3ENA"],
                    "Values_Name": ["SALTO II", "TERMO NORTE"],
                    "Values_Type": ["HIDRAULICA", "TERMICA"],
                }
            )
        days = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]
        if coleccion == "PrecBolsNaci" or coleccion == "DemaCome":
            codes = ["2QEK"]  # Sistema series: single code, dedupe by datetime
        else:
            codes = ["2QEK", "3ENA"]  # Recurso series: both crosswalk codes
        df = pd.DataFrame(
            [{"Values_code": code, "Date": d} for d in days for code in codes]
        )
        for h in range(1, 25):
            df[f"Values_Hour{h:02d}"] = 300.0
        return df


def _write_year_csv(tmp_path, rel_subdir, filename, df):
    sub = tmp_path / rel_subdir
    sub.mkdir(parents=True, exist_ok=True)
    df.to_csv(sub / filename, index=False, date_format="%Y-%m-%d %H:%M:%S")


def test_refresh_tick_merges_window_and_clears_loader_cache(tmp_path):
    session = _session()
    # local precio_bolsa ends 04-17; now = 04-20 12:00 UTC -> Bogota 04-20 -> end 04-19
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    # cache the stale frame first (must be invalidated by the tick)
    stale_max = loaders_mod.load_precio_bolsa(str(tmp_path), 2024)["datetime"].dt.date.max()
    assert stale_max == date(2024, 4, 17)

    now = datetime(2024, 4, 20, 12, 0, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 12), date(2024, 4, 19))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )

    fresh = loaders_mod.load_precio_bolsa(str(tmp_path), 2024)
    assert fresh["datetime"].dt.date.max() == date(2024, 4, 19)
    assert len(fresh) == 192  # 8 requested days x 24h, no duplicates

    # the pull must have started at min(window edge, last_local+1) = min(04-12, 04-18)
    asked = [a for a in consult.asked if a[0] == "PrecBolsNaci"]
    assert asked and asked[0][1] == date(2024, 4, 12)
    assert asked[0][2] == date(2024, 4, 19)


def test_refresh_tick_gate_creates_settled_rows_when_month_completes(tmp_path):
    session = _session()
    # local ofertas already covers a complete March 2024; fake serves April 1-30
    march_days = [date(2024, 3, 1) + timedelta(days=i) for i in range(31)]
    local = pd.DataFrame(
        [
            {"Date": pd.Timestamp(d), "resource_name": "SALTO II", "Value": 150.0}
            for d in march_days
        ]
    )
    _write_year_csv(tmp_path, "ofertas", "ofertas_2024.csv", local)

    now = datetime(2024, 5, 2, 12, 0, tzinfo=UTC)  # Bogota 05-02 -> end 05-01
    # pull range for ofertas: min(05-01-7=04-24, last_local+1=04-01) = 04-01..05-01
    consult = _FakeConsult(date(2024, 4, 1), date(2024, 5, 1))
    created = refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert created == 60  # 30 days x 2 kinds for April
    kinds = {
        (p.kind, p.target_date)
        for p in session.scalars(select(RunPlan)).all()
    }
    assert ("preideal_settled", date(2024, 4, 30)) in kinds
    assert ("ideal_settled", date(2024, 4, 30)) in kinds
    # gate is one-shot: a second tick creates nothing new
    again = refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert again == 0
```

Why this works: the fake emits one `(code, Date)` row per day of its range, so after the pull the merged April CSV has at least one row per April day → `month_complete("ofertas", April)` is true → `next_settlement_month` (walking back from May) returns April. The pull start for `ofertas` is 04-01 (local March ends 03-31 → `last_local + 1`), so the requested range covers the whole month.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler_refresh.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler.refresh'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/scheduler/refresh.py
"""Freshness tick: windowed incremental pull of the five real XM series,
keyed merge into the year CSVs, loader-cache invalidation, then the monthly
settled gate.

Pull-range policy (plan Notes, resolving spec section 5.1): a fixed 7-day
window can never capture a month that XM publishes as a single block ~1st
of the next month (spec section 1: PrecOferDesp). The request therefore
starts at min(today - DATA_REFRESH_WINDOW_DAYS, last_local_day + 1), i.e.
always at least the window back AND reaching back to the day after the last
locally merged row — the closed month arrives whole on the first pull after
publication, with no separate monthly job.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.data import loaders, xm_bulk
from app.data.xm_bulk import (
    refresh_dema_come,
    refresh_dispo_come,
    refresh_dispo_declarada,
    refresh_ofertas,
    refresh_precio_bolsa,
)
from app.scheduler import inputs, plans, timeutil

_SERIES = (
    ("dispo_declarada", refresh_dispo_declarada, True),
    ("ofertas", refresh_ofertas, True),
    ("demaCome", refresh_dema_come, False),
    ("dispo_come", refresh_dispo_come, True),
    ("precio_bolsa", refresh_precio_bolsa, False),
)


def _pull_start(name: str, end_day: date, config, data_dir: str) -> date:
    window_edge = end_day - timedelta(days=config.data_refresh_window_days)
    last = inputs.series_max_date(name, end_day.year, data_dir)
    if last is None:
        return window_edge
    return min(window_edge, last + timedelta(days=1))


def _year_segments(start: date, end: date) -> list[tuple[date, date]]:
    segments = []
    cursor = start
    while cursor <= end:
        seg_end = min(end, date(cursor.year, 12, 31))
        segments.append((cursor, seg_end))
        cursor = date(cursor.year + 1, 1, 1)
    return segments


def refresh_tick(
    session, *, now, config, data_dir: str = "data", consult=None
) -> int:
    """One freshness pass. Returns settled rows created by the monthly gate."""
    if not config.daily_enabled:
        return 0
    from pydataxm.pydataxm import ReadDB

    consult_obj = consult if consult is not None else ReadDB()
    end_day = timeutil.tz_date(now, config.scheduler_tz) - timedelta(days=1)

    needs_crosswalk = any(needs for _, _, needs in _SERIES)
    crosswalk = (
        xm_bulk.fetch_resource_crosswalk(consult_obj) if needs_crosswalk else None
    )

    for name, refresh_fn, uses_crosswalk in _SERIES:
        start = _pull_start(name, end_day, config, data_dir)
        for seg_start, seg_end in _year_segments(start, end_day):
            refresh_fn(
                seg_start,
                seg_end,
                data_dir,
                consult_obj,
                crosswalk if uses_crosswalk else None,
                session=session,
            )
    loaders.clear_loader_caches()

    month = plans.next_settlement_month(
        session, now=now, config=config, data_dir=data_dir
    )
    if month is None:
        return 0
    return plans.create_settled_rows_for_month(
        session, month_start=month, config=config, due_at=now
    )
```

Note: `refresh_tick` imports `ReadDB` lazily so test imports of the module never touch pydataxm network code.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler_refresh.py -q`
Expected: PASS. If the fake's `Date` column arrives as strings, parse it in `_FakeConsult.request_data` (`df["Date"] = pd.to_datetime(df["Date"])`) — `_melt_hourly` and `refresh_ofertas` expect datetimes.

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/refresh.py tests/test_scheduler_refresh.py
git commit -m "feat(scheduler): freshness tick with keyed pull and monthly settled gate"
```

---

### Task 15: `biddings.py` — rolling `ultimo_precio` over real ∪ estimated

**Files:**
- Modify: `app/data/heuristic/biddings.py`
- Modify: `tests/test_ofertas_heuristic.py`

**Interfaces:**
- Consumes: existing `ensure_ofertas_estimado` cache file (`ofertas_estimado/ofertas_estimado_{year}.csv`, columns `Date,resource_name,Value,is_estimated`).
- Produces:
  - `_rolling_ultimo_precio(oferta_full: pd.DataFrame, cached: pd.DataFrame) -> dict[str, float]` — private helper: most recent `Value` per resource over real ∪ estimated (spec §5.2); on an equal-date tie the REAL value wins. Implementation: concat `[estimated rows, real rows]` (real last), stable-sort by `Date`, `groupby("resource_name")["Value"].last()`. Real rows get `is_estimated=False` locally.
  - `ensure_ofertas_estimado` uses the helper instead of computing `ultimo_precio` from `oferta_full` alone — MPO resolutions of previous days carry forward to the following days until the real monthly extraction replaces them.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ofertas_heuristic.py — append

def test_rolling_ultimo_precio_real_wins_on_same_date_tie():
    from app.data.heuristic.biddings import _rolling_ultimo_precio

    real = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-08-11"), pd.Timestamp("2026-08-11")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [150.0, 180.0],
        }
    )
    cached = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-08-11")],
            "resource_name": ["TERMO1"],
            "Value": [990.0],
            "is_estimated": [True],
        }
    )
    out = _rolling_ultimo_precio(real, cached)
    assert out == {"TERMO1": 150.0, "TERMO2": 180.0}  # tie -> real wins


def test_rolling_ultimo_precio_estimate_carries_forward_when_newer():
    from app.data.heuristic.biddings import _rolling_ultimo_precio

    real = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-30"), pd.Timestamp("2026-07-30")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [100.0, 180.0],
        }
    )
    cached = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-08-11")],
            "resource_name": ["TERMO1"],
            "Value": [990.0],
            "is_estimated": [True],
        }
    )
    out = _rolling_ultimo_precio(real, cached)
    assert out == {"TERMO1": 990.0, "TERMO2": 180.0}


def test_ensure_ofertas_estimado_rolls_previous_mpo_resolution_forward(tmp_path):
    fecha1 = _date(2026, 8, 11)
    fecha2 = _date(2026, 8, 12)
    _write_prid_imar(tmp_path, "2026-08-11", "0811")  # resolves TERMO1 at hour 5

    # day 2: nobody is at part-load -> nothing resolves; only the union roll works
    day2 = tmp_path / "2026-08-12"
    day2.mkdir()
    (day2 / "PrId0812_NAL.txt").write_text(
        "TERMO1," + ",".join(["300"] * 24) + "\n"
        "TERMO2," + ",".join(["200"] * 24) + "\n",
        encoding="latin1",
    )
    mpo_row = ",".join(["1000"] * 24)
    (day2 / "iMAR0812.txt").write_text(
        f'"Costo Marginal",{mpo_row}\n"Delta",' + ",".join(["0"] * 24)
        + f'\n"MPO",{mpo_row}\n',
        encoding="latin1",
    )

    hours1 = [pd.Timestamp(fecha1) + pd.Timedelta(hours=h) for h in range(24)]
    hours2 = [pd.Timestamp(fecha2) + pd.Timedelta(hours=h) for h in range(24)]
    dispo1 = pd.DataFrame(
        [{"resource_name": "TERMO1", "datetime": h, "dispo": 300_000.0, "gen_type": "TERMICA"} for h in hours1]
        + [{"resource_name": "TERMO2", "datetime": h, "dispo": 200_000.0, "gen_type": "TERMICA"} for h in hours1]
    )
    dispo2 = pd.DataFrame(
        [{"resource_name": "TERMO1", "datetime": h, "dispo": 300_000.0, "gen_type": "TERMICA"} for h in hours2]
        + [{"resource_name": "TERMO2", "datetime": h, "dispo": 200_000.0, "gen_type": "TERMICA"} for h in hours2]
    )
    oferta_full = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-30"), pd.Timestamp("2026-07-30")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [100.0, 180.0],
        }
    )

    day1 = ensure_ofertas_estimado(fecha1, str(tmp_path), dispo1, oferta_full)
    assert day1.set_index("resource_name")["Value"].to_dict()["TERMO1"] == 990.0

    # day 2 with NO marginal resolution: TERMO1 must roll the day-1 MPO estimate
    # (990.0), not fall back to the stale real 100.0 — this is the regression
    # this task fixes
    day2_result = ensure_ofertas_estimado(fecha2, str(tmp_path), dispo2, oferta_full)
    values = day2_result.set_index("resource_name")["Value"].to_dict()
    assert values["TERMO1"] == 990.0
    assert values["TERMO2"] == 180.0
```

Note: `_write_prid_imar` (already in the test file) writes day files for 2026-08-11 with content that resolves TERMO1 at hour 5; the second date's files are written inline above.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ofertas_heuristic.py -q`
Expected: FAIL — `ImportError: cannot import name '_rolling_ultimo_precio'` and the roll-forward test returns `TERMO1 == 100.0` (old behavior: real only).

- [ ] **Step 3: Write minimal implementation**

```python
# app/data/heuristic/biddings.py — add the helper and use it in ensure_ofertas_estimado

def _rolling_ultimo_precio(
    oferta_full: pd.DataFrame, cached: pd.DataFrame
) -> dict[str, float]:
    """Most recent Value per resource over real ∪ estimated.

    The real monthly extraction is the source of truth; until it covers a
    resource/date, MPO resolutions of previous days (estimated rows cached in
    ofertas_estimado) roll forward. On an equal-date tie the real value wins:
    rows are concatenated estimated-first then real, and the stable sort by
    Date keeps real rows after estimates of the same day.
    """
    real = oferta_full[["Date", "resource_name", "Value"]].copy()
    real["is_estimated"] = False
    if cached.empty:
        combined = real
    else:
        combined = pd.concat(
            [cached[["Date", "resource_name", "Value", "is_estimated"]], real],
            ignore_index=True,
        )
    combined = combined.sort_values("Date", kind="stable")
    return combined.groupby("resource_name")["Value"].last().to_dict()
```

```python
# app/data/heuristic/biddings.py — in ensure_ofertas_estimado, replace this block:

    ultimo_precio = (
        oferta_full.sort_values("Date").groupby("resource_name")["Value"].last().to_dict()
    )

# with:

    ultimo_precio = _rolling_ultimo_precio(oferta_full, cached)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ofertas_heuristic.py -q`
Expected: PASS — the pre-existing tests still pass (`cached` is empty on their first calls, so the union degenerates to the old real-only behavior; the caching test's second call is a cache hit that never recomputes).

- [ ] **Step 5: Run the case-builder smoke tests**

Run: `uv run pytest tests/test_case_builder_ideal_recent.py tests/test_xm_smoke_build_case.py tests/test_xm_smoke_run.py -q`
Expected: PASS — no fixture has estimated rows cached before these tests run.

- [ ] **Step 6: Commit**

```bash
git add app/data/heuristic/biddings.py tests/test_ofertas_heuristic.py
git commit -m "feat(data): roll offer-price estimates over the real/estimated union"
```

---

### Task 16: `xm_smoke` fixture — closed synthetic month (2024-03) + settled-day blob set

**Files:**
- Modify: `tests/fixtures/xm_smoke/generate_fixture.py` (full rewrite, parameterized over days)
- Modify (regenerated outputs): `tests/fixtures/xm_smoke/dispo_declarada/dispo_declarada_2024.csv`, `ofertas/ofertas_2024.csv`, `demaCome/demaCome_2024.csv`, `dispo_come/dispo_come_2024.csv`, `precio_bolsa/precio_bolsa_2024.csv`
- Create (regenerated outputs): `tests/fixtures/xm_smoke/2024-03-15/*`, `tests/fixtures/xm_smoke/condicion_inicial/2024-03-15/*`
- Create: `tests/test_xm_smoke_settled.py`

**Interfaces:**
- Consumes: fixture conventions of Fase 2B (year CSVs + flat `{date}/` blobs + `condicion_inicial/{date}/`), the `.gitignore` exception `tests/fixtures/**/*.csv`.
- Produces: a fixture where the year CSVs additionally cover every day of 2024-03 (a closed month: `ofertas` has rows for all 31 March days) and where 2024-03-15 has the full blob set (OFEI/PrId/iMAR/dCondIniU/dCondIniP/dAGCUNIDAD + `agc_asignado.csv`, both in `2024-03-15/` and `condicion_inicial/2024-03-15/`), so the settled path (spec §10 fixtures bullet) can run offline. April-18 content is unchanged, so every existing smoke test keeps its assertions.
- Run the generator (`uv run python tests/fixtures/xm_smoke/generate_fixture.py` from repo root) and commit its outputs; do NOT hand-edit the CSVs.

- [ ] **Step 1: Rewrite the generator**

```python
# tests/fixtures/xm_smoke/generate_fixture.py
"""Generator for the Fase 2B smoke fixture + Fase 7A closed-month extension.

Run once (`uv run python tests/fixtures/xm_smoke/generate_fixture.py` from
repo root) and commit the output alongside this script. Not run at test
time — the fixture files it produces are the actual test input.

Content: year CSVs with rows for 2024-03-01..2024-03-31 (a closed synthetic
month for the settled lane) AND 2024-04-18 (the original smoke day), plus
full per-date blob sets for both 2024-03-15 and 2024-04-18.
"""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent

GENERATORS = [
    {
        "name": "TERMO1",
        "dispo_kw": 300_000,
        "bid_cop_kwh": 150,
        "pap_cop": 1_500_000,
        "mo": 10,
        "gpini": 150,
        "conf": 1,
        "tl": 5,
        "tfl": 0,
    },
    {
        "name": "TERMO2",
        "dispo_kw": 200_000,
        "bid_cop_kwh": 180,
        "pap_cop": 1_500_000,
        "mo": 5,
        "gpini": 0,
        "conf": 0,
        "tl": 0,
        "tfl": 10,
    },
]

MARCH_DAYS = [date(2024, 3, 1) + timedelta(days=i) for i in range(31)]
FECHA = date(2024, 4, 18)
SETTLED = date(2024, 3, 15)
DAY_ROWS = {**{d: 350_000 for d in MARCH_DAYS}, FECHA: 350_000}


def _hours(day: date):
    return [datetime(day.year, day.month, day.day) + timedelta(hours=h) for h in range(24)]


def _write_csv(rel_dir: str, filename: str, header: list[str], rows: list[list]):
    out_dir = BASE / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / filename, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


days = MARCH_DAYS + [FECHA]
dispo_rows = []
for day in days:
    for g in GENERATORS:
        for h in _hours(day):
            dispo_rows.append([h.isoformat(sep=" "), g["name"], g["dispo_kw"], "TERMICA"])
_write_csv("dispo_declarada", "dispo_declarada_2024.csv",
           ["datetime", "resource_name", "dispo", "gen_type"], dispo_rows)

oferta_rows = []
for day in days:
    for g in GENERATORS:
        oferta_rows.append([day.isoformat(), g["name"], g["bid_cop_kwh"]])
_write_csv("ofertas", "ofertas_2024.csv", ["Date", "resource_name", "Value"], oferta_rows)

dema_rows = []
for day in days:
    for h in _hours(day):
        dema_rows.append([h.isoformat(sep=" "), 350_000])
_write_csv("demaCome", "demaCome_2024.csv", ["datetime", "dema"], dema_rows)

dispo_come_rows = []
for day in days:
    for g in GENERATORS:
        for h in _hours(day):
            dispo_come_rows.append([h.isoformat(sep=" "), g["name"], g["dispo_kw"]])
_write_csv("dispo_come", "dispo_come_2024.csv",
           ["datetime", "resource_name", "dispo"], dispo_come_rows)

bolsa_rows = []
for day in days:
    for h in _hours(day):
        bolsa_rows.append([h.isoformat(sep=" "), 200])
_write_csv("precio_bolsa", "precio_bolsa_2024.csv", ["datetime", "precio_bolsa"], bolsa_rows)

_write_csv(".", "parametros_plantas.csv", ["generador", "TMG"],
           [[g["name"], 1] for g in GENERATORS])
(BASE / "ramps.json").write_text("{}")
(BASE / "preideal_dispatch_map.json").write_text("{}")

DCONDINIP_HEADER = (
    "Planta ,AGC, BLOQUESPINI1, CONFENTRADA, CONFPINI1, CONFSALIDA, DISPPINI1, "
    "ESTADOPINI1, GPPINI_1, GPPINI_2, NARRANQUESPINI1, PRUEBAS, TAPUBLICAR, "
    "TCEPENDIENTE, TDISPPINI1, TFL, TL, TULT\n"
)


def dcondinip_row(g: dict) -> str:
    return (
        f"{g['name']}, 0, 0, 0, {g['conf']}, 0, {g['gpini']},  - , "
        f"{g['gpini']:.4f}, {g['gpini']:.4f}, 0, 0, 10, 0, {g['tl']}, {g['tfl']}, {g['tl']}, 0\n"
    )


def _write_blob_day(day: date):
    mmdd = f"{day.month:0>2}{day.day:0>2}"
    flat_dir = BASE / str(day)
    flat_dir.mkdir(parents=True, exist_ok=True)
    ci_dir = BASE / "condicion_inicial" / str(day)
    ci_dir.mkdir(parents=True, exist_ok=True)

    ofei_lines = []
    for g in GENERATORS:
        ofei_lines.append(f"{g['name']}, PAPF02,{g['pap_cop']}")
        ofei_lines.append(f"{g['name']}, PAPT02,{int(g['pap_cop'] * 0.8)}")
        ofei_lines.append(f"{g['name']}, PAPC02,{int(g['pap_cop'] * 0.6)}")
    for g in GENERATORS:
        mo_vals = ",".join(str(g["mo"]) for _ in range(24))
        ofei_lines.append(f"{g['name']}, MO,{mo_vals}")
    (flat_dir / f"OFEI{mmdd}.txt").write_text("\n".join(ofei_lines) + "\n")

    (flat_dir / f"PrId{mmdd}_NAL.txt").write_text(
        ",".join(["TOTAL"] + ["350"] * 24) + "\n", encoding="latin1"
    )
    with open(flat_dir / f"dCondIniP{mmdd}.txt", "w") as f:
        f.write(DCONDINIP_HEADER)
        for g in GENERATORS:
            f.write(dcondinip_row(g))
    (flat_dir / f"dCondIniU{mmdd}.txt").write_text("Recurso,Tipo,Gini-1,Cini-1\n")
    mpo_row = ",".join(["150000.00"] * 24)
    delta_row = ",".join(["0.00"] * 24)
    imar_lines = [f'"Costo Marginal",{mpo_row}', f'"Delta",{delta_row}', f'"MPO",{mpo_row}']
    (flat_dir / f"iMAR{mmdd}.txt").write_text("\n".join(imar_lines) + "\n")
    agcu_lines = []
    for g in GENERATORS:
        agcu_lines.append(f'"{g["name"]}",' + ",".join(["0"] * 23))
    (flat_dir / f"dAGCUNIDAD{mmdd}.txt").write_text("\n".join(agcu_lines) + "\n")

    # AGC file per date (load_agc reads {date}/agc_asignado.csv)
    with open(flat_dir / "agc_asignado.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datetime", "recurso", "agc"])
        for h in _hours(day):
            w.writerow([h.isoformat(sep=" "), "TERMO1", 0])

    with open(ci_dir / f"dCondIniP{mmdd}.txt", "w") as f:
        f.write(DCONDINIP_HEADER)
        for g in GENERATORS:
            f.write(dcondinip_row(g))
    (ci_dir / f"dCondIniU{mmdd}.txt").write_text("Recurso,Tipo,Gini-1,Cini-1\n")


_write_blob_day(SETTLED)
_write_blob_day(FECHA)

print("fixture written to", BASE)
```

Careful check against the original: the original `dAGCUNIDAD` row is `"NAME",0,...` with 23 more zeros (24 fields) — the row above writes the quoted name plus 23 zeros, which matches. The original PrId row wrote `["TOTAL"] + ["350"]*24`; keep it. The OFEI/AGCU/PrId content is byte-identical to the original for 2024-04-18, so existing tests (`test_xm_smoke_*`, `test_ofei` via fixture) keep passing.

- [ ] **Step 2: Regenerate the fixture and verify the diff scope**

Run:
```bash
uv run python tests/fixtures/xm_smoke/generate_fixture.py
git status --short tests/fixtures/xm_smoke/
```
Expected: modified — the five year CSVs, `generate_fixture.py`; untracked — `2024-03-15/` files and `condicion_inicial/2024-03-15/` files. No other fixture file changes (parametros/ramps/preideal_dispatch_map are rewritten byte-identical).

- [ ] **Step 3: Run the existing smoke suite**

Run: `uv run pytest tests/test_xm_smoke_loaders.py tests/test_xm_smoke_build_case.py tests/test_xm_smoke_run.py tests/test_xm_smoke_cli.py tests/test_ofei.py -q`
Expected: PASS — all existing assertions are date-filtered or date-specific and April-18 content is unchanged. If any test asserted whole-file row counts, fix that test in this task instead of shrinking the fixture.

- [ ] **Step 4: Write the closed-month + settled-run tests**

```python
# tests/test_xm_smoke_settled.py
"""Fase 7A fixture checks: the closed synthetic month (2024-03) powers the
settled lane — month completeness predicates and a real settled-path solve
on 2024-03-15 that must NOT touch the offer heuristic."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data import loaders
from app.pipeline.runner import run_case
from app.scheduler import inputs
from app.schemas.case import DispatchCase, DispatchLevel

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
MARCH = date(2024, 3, 1)
SETTLED = date(2024, 3, 15)


def test_year_series_cover_the_whole_closed_month():
    assert loaders.load_dispo(DD, 2024)["datetime"].dt.date.max() == date(2024, 3, 31)
    assert loaders.load_ofertas(DD, 2024)["Date"].dt.date.max() == date(2024, 3, 31)
    assert loaders.load_demanda(DD, 2024)["datetime"].dt.date.max() == date(2024, 3, 31)
    assert loaders.load_dispo_come(DD, 2024)["datetime"].dt.date.max() == date(2024, 3, 31)
    assert loaders.load_precio_bolsa(DD, 2024)["datetime"].dt.date.max() == date(2024, 3, 31)
    # March is a complete month for the series the settled gate checks
    assert inputs.month_complete("ofertas", MARCH, DD) is True
    assert inputs.month_complete("demaCome", MARCH, DD) is True
    assert inputs.month_complete("dispo_come", MARCH, DD) is True
    # April 18 still present for the legacy smoke tests
    assert inputs.series_has_day("dispo_declarada", date(2024, 4, 18), DD) is True


def test_settled_day_inputs_are_ready():
    assert inputs.blobs_ready(SETTLED, DD) is True
    assert inputs.series_has_day("ofertas", SETTLED, DD) is True
    assert inputs.series_has_day("precio_bolsa", SETTLED, DD) is True


def test_settled_run_solves_without_the_offer_heuristic(tmp_path, monkeypatch):
    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    def _no_heuristic(*a, **kw):
        raise AssertionError("settled run must use real ofertas, not the heuristic")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)
    monkeypatch.setattr(
        "app.pipeline.case_builder.ensure_ofertas_estimado", _no_heuristic
    )

    case = DispatchCase(dispatch_date=SETTLED, level=DispatchLevel.preideal, solver="cbc")
    out = str(tmp_path / "results")
    result = run_case(case, evaluate=True, out=out, data_dir=DD)

    assert result.ok, result.error
    assert result.metrics is not None
    assert result.metrics["mae"] == 30000.0  # 180000 model vs 150000 iMAR fixture
    price = pd.read_csv(result.price_path)
    assert len(price) == 24
    assert (price["ideal_marginal_price"] == 180000.0).all()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_xm_smoke_settled.py -q`
Expected: PASS (cbc solve of the 2-generator March fixture takes a few seconds).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/xm_smoke/generate_fixture.py tests/fixtures/xm_smoke/ tests/test_xm_smoke_settled.py
git commit -m "test(fixtures): add closed synthetic month for the settled lane"
```

Check in `git status` that the CSVs under `tests/fixtures/xm_smoke/` are staged (the `.gitignore` exception `tests/fixtures/**/*.csv` covers them).

---

### Task 17: API visibility — list/detail/artifacts/log gates + payload fields

**Files:**
- Modify: `services/api/main.py`
- Create: `tests/test_api_visibility.py`

**Interfaces:**
- Consumes: `list_visible_runs` (Task 3), `Run.visibility`/`Run.input_grade` columns (Task 1).
- Produces (spec §7):
  - `GET /runs` returns runs where `user_id == me OR visibility == public`, ordered `created_at` desc; each payload item (and detail) gains `"visibility"` and `"input_grade"`.
  - `GET /runs/{run_id}` plus artifact/download/log/nodal endpoints: allowed to the owner OR to any logged-in user when the run is `public`; uniform 404 otherwise. `_get_owned_run` is renamed `_get_authorized_run` with the new condition.
  - `POST /runs` (manual) behavior unchanged — manual runs stay `private`/`input_grade=None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_visibility.py
from datetime import date

from app.db import queries


def _public_run(api_client, level="ideal", grade="provisional", user=None):
    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level=level,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=user,
        visibility="public",
        input_grade=grade,
    )
    session.close()
    return run.id


def test_manual_run_stays_private_with_null_grade(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]
    body = api_client.get(f"/runs/{run_id}").json()
    assert body["visibility"] == "private"
    assert body["input_grade"] is None


def test_list_shows_own_private_and_others_public_runs(api_client):
    own = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    other_public = _public_run(api_client)

    resp = api_client.get("/runs")
    assert resp.status_code == 200
    rows = {r["run_id"]: r for r in resp.json()}
    assert own.json()["run_id"] in rows
    assert rows[other_public]["visibility"] == "public"
    assert rows[other_public]["input_grade"] == "provisional"


def test_other_users_private_run_is_invisible_and_404(api_client):
    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
        visibility="private",
    )
    run_id = run.id
    session.close()

    listed = {r["run_id"] for r in api_client.get("/runs").json()}
    assert run_id not in listed
    assert api_client.get(f"/runs/{run_id}").status_code == 404


def test_public_run_detail_log_and_artifact_available_to_any_user(api_client, tmp_path):
    run_id = _public_run(api_client)
    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)

    out_dir = tmp_path / "results" / run_id
    out_dir.mkdir(parents=True)
    price = out_dir / "price.csv"
    price.write_text("datetime,ideal_marginal_price\n2024-04-18 00:00:00,180000.0\n")
    log = out_dir / "run.log"
    log.write_text("solver log line\n")
    run.log_path = str(log)
    run.price_path = str(price)
    run.status = "done"
    session.commit()
    session.close()

    assert api_client.get(f"/runs/{run_id}").status_code == 200
    assert api_client.get(f"/runs/{run_id}/log").status_code == 200
    assert api_client.get(f"/runs/{run_id}/prices").status_code == 200
```

Note: the manual `POST /runs` runs as `user-1` (the `api_client` fixture overrides `get_current_user_id`). The visibility fixture above creates runs with `user_id=None` (system) — the strongest test of the public gate. Artifact reads go through `_artifact_path` which uses `get_storage(".")`, and absolute `tmp_path` paths resolve correctly (`Path(root) / abs` → abs).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_visibility.py -q`
Expected: FAIL — other users' public runs 404 (`_get_owned_run` requires ownership), list hides them, payload lacks `visibility`/`input_grade`.

- [ ] **Step 3: Write minimal implementation**

```python
# services/api/main.py — import line: replace list_runs_for_user with list_visible_runs
from app.db import queries  # unchanged import; queries.list_visible_runs now used

# _run_summary: add the two keys
def _run_summary(run, case) -> dict:
    return {
        "run_id": run.id,
        "status": run.status,
        "dispatch_date": case.dispatch_date,
        "level": case.level,
        "scenario_id": case.scenario_id,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error": run.error,
        "visibility": run.visibility,
        "input_grade": run.input_grade,
    }
```

```python
# services/api/main.py — authorization helper: replace _get_owned_run entirely

def _get_authorized_run(session, run_id: str, user_id: str):
    """Owner or any logged-in user when the run is public (spec section 7)."""
    run = queries.get_run(session, run_id)
    if run is None or (run.user_id != user_id and run.visibility != "public"):
        raise HTTPException(status_code=404, detail="run not found")
    return run
```

```python
# services/api/main.py — GET /runs endpoint body
@app.get("/runs")
def list_runs(user_id: str = Depends(get_current_user_id), session=Depends(get_session)):
    runs = queries.list_visible_runs(session, user_id)
    return [
        {
            **_run_summary(r, queries.get_case(session, r.case_id)),
            "nodal": _nodal_summary(session, r.id),
        }
        for r in runs
    ]
```

```python
# services/api/main.py — rename every remaining call site:
# replace `_get_owned_run(` with `_get_authorized_run(` (7 occurrences: the
# detail endpoint, get_run_log, get_run_artifact, download_price_comparison,
# download_run_artifact, get_nodal_artifact, download_nodal_artifact).
# The function bodies of those endpoints are unchanged.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_visibility.py tests/test_api_runs.py tests/test_api_results.py tests/test_api_log.py tests/test_api_nodal.py -q`
Expected: PASS — pre-existing API tests exercise own-run access only, which the new helper keeps allowed.

- [ ] **Step 5: Commit**

```bash
git add services/api/main.py tests/test_api_visibility.py
git commit -m "feat(api): public-run visibility gates and payload fields"
```

---

### Task 18: `GET /chart/series` — daily series + run precedence

**Files:**
- Create: `services/api/chart.py`
- Modify: `services/api/main.py` (endpoint)
- Modify: `tests/test_api_chart.py` (create)

**Interfaces:**
- Consumes: runs/cases rows, `run.price_path` CSVs (columns `datetime`, `ideal_marginal_price`), `load_actual_bolsa`/`load_actual_price` (`app/data/actuals.py`), `get_storage`.
- Produces (spec §7.1 contract, verbatim):
  - `build_chart_series(session, *, days: int, today: date, data_dir: str = "data") -> list[dict]` — one row per Bogota calendar day from `today - days + 1` to `today`, ascending:
    ```
    {"date": "YYYY-MM-DD", "bolsa_tx1": float|null, "mpo_xm": float|null,
     "ideal_settled": float|null, "ideal_settled_run_id": str|null,
     "ideal_provisional": float|null, "ideal_provisional_run_id": str|null,
     "preideal": float|null, "preideal_run_id": str|null}
    ```
  - Series resolution (server-side, from public done runs):
    - `bolsa_tx1`: daily mean of the year `precio_bolsa` CSV (`load_actual_bolsa`; loader already scales ×1e3 to COP/MWh).
    - `mpo_xm`: daily mean of iMAR(D) final (`load_actual_price` → `parse_mpo`).
    - `ideal_settled`/`ideal_provisional`/`preideal`: daily mean of `ideal_marginal_price` over the `price_path` rows of that day. Precedence per date: `preideal` = `preideal_settled` run if present, else the `preideal_daily` (provisional) run; `ideal_settled` and `ideal_provisional` are reported separately. When several candidate runs share (level, input_grade, date), the most recently created wins. `*_run_id` accompanies every simulated series (deep-link target for #90).
    - No data → `null` (a missing day is visible, spec §9).
  - `list_done_public_dispatch_runs(session) -> list[tuple[Run, Case]]` — public + done runs joined with their case, `Case.level in ("preideal", "ideal")`, ordered `Run.created_at` desc (added to `app/db/queries.py` in this task).
  - Endpoint `GET /chart/series?days=30` — `days: int = Query(30, ge=1, le=90)` (default 30, cap 90), any logged-in user, `today` = Bogota date of now.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_chart.py
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.db import queries
from app.schemas import DispatchCase, DispatchLevel, RunResult
from services.api import chart

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _finish_public_run(api_client, tmp_path, *, level, grade, price):
    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level=level,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
        input_grade=grade,
    )
    out = tmp_path / "results" / run.id
    out.mkdir(parents=True)
    hours = pd.date_range("2024-04-18", periods=24, freq="h")
    pd.DataFrame(
        {"datetime": hours, "ideal_marginal_price": [price] * 24}
    ).to_csv(out / "price.csv", index=False)
    result = RunResult(
        case=DispatchCase(dispatch_date=FECHA, level=DispatchLevel(level)),
        ok=True,
        price_path=str(out / "price.csv"),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out))
    session.close()
    return run.id


def _rows(api_client, tmp_path, *, days=30):
    session = api_client.SessionLocal()
    rows = chart.build_chart_series(
        session, days=days, today=FECHA, data_dir=DD
    )
    session.close()
    return {r["date"]: r for r in rows}


def test_preideal_falls_back_to_provisional_when_no_settled(api_client, tmp_path):
    prov_run = _finish_public_run(api_client, tmp_path, level="preideal",
                                  grade="provisional", price=3000.0)
    by_day = _rows(api_client, tmp_path, days=30)
    row = by_day["2024-04-18"]
    assert row["preideal"] == 3000.0
    assert row["preideal_run_id"] == prov_run
    assert row["ideal_settled"] is None
    assert row["ideal_provisional"] is None


def test_preideal_settled_wins_over_provisional(api_client, tmp_path):
    _finish_public_run(api_client, tmp_path, level="preideal",
                       grade="provisional", price=3000.0)
    settled_run = _finish_public_run(api_client, tmp_path, level="preideal",
                                     grade="settled", price=1000.0)
    row = _rows(api_client, tmp_path, days=30)["2024-04-18"]
    assert row["preideal"] == 1000.0
    assert row["preideal_run_id"] == settled_run


def test_ideal_lanes_are_reported_separately(api_client, tmp_path):
    settled = _finish_public_run(api_client, tmp_path, level="ideal",
                                 grade="settled", price=1000.0)
    prov = _finish_public_run(api_client, tmp_path, level="ideal",
                              grade="provisional", price=2000.0)
    row = _rows(api_client, tmp_path, days=30)["2024-04-18"]
    assert row["ideal_settled"] == 1000.0
    assert row["ideal_settled_run_id"] == settled
    assert row["ideal_provisional"] == 2000.0
    assert row["ideal_provisional_run_id"] == prov


def test_external_series_from_fixture_actuals(api_client, tmp_path):
    # no simulated runs needed: bolsa_tx1 (raw 200 * 1e3) and mpo_xm (iMAR 150000)
    row = _rows(api_client, tmp_path, days=30)["2024-04-18"]
    assert row["bolsa_tx1"] == 200000.0
    assert row["mpo_xm"] == 150000.0
    assert row["preideal"] is None


def test_series_endpoint_shape_and_days_bounds(api_client, tmp_path):
    resp = api_client.get("/chart/series?days=30")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert set(rows[0]) == {
        "date", "bolsa_tx1", "mpo_xm",
        "ideal_settled", "ideal_settled_run_id",
        "ideal_provisional", "ideal_provisional_run_id",
        "preideal", "preideal_run_id",
    }
    assert len(rows) <= 30
    assert api_client.get("/chart/series?days=0").status_code == 422
    assert api_client.get("/chart/series?days=91").status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_chart.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.api.chart'` (and 404 on the endpoint).

- [ ] **Step 3: Write minimal implementation**

```python
# app/db/queries.py — append (imports Case already imported)

def list_done_public_dispatch_runs(session: Session) -> list[tuple[Run, Case]]:
    """Public done runs of the dispatch levels the chart series consumes."""
    stmt = (
        select(Run, Case)
        .join(Case, Run.case_id == Case.id)
        .where(
            Run.visibility == "public",
            Run.status == "done",
            Case.level.in_(["preideal", "ideal"]),
        )
        .order_by(Run.created_at.desc())
    )
    return list(session.execute(stmt))
```

```python
# services/api/chart.py
"""GET /chart/series builder (spec section 7.1): one row per Bogota calendar
day with the daily mean (COP/MWh) of five series. Simulated series come from
public done runs; externals come from the year CSVs / per-date iMAR."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.data.actuals import load_actual_bolsa, load_actual_price
from app.db import queries
from app.storage import get_storage

_LEVEL_KEYS = {
    ("ideal", "settled"): "ideal_settled",
    ("ideal", "provisional"): "ideal_provisional",
    ("preideal", "settled"): "preideal_settled",
    ("preideal", "provisional"): "preideal_daily",
}
# per simulated chart key: (level, input_grade) candidate list, best first
_SERIES_KEYS = {
    "ideal_settled": [("ideal", "settled")],
    "ideal_provisional": [("ideal", "provisional")],
    "preideal": [("preideal", "settled"), ("preideal", "provisional")],
}


def _mean_price(run, day: date) -> float | None:
    if run.price_path is None:
        return None
    try:
        with get_storage(".").open(run.price_path) as f:
            df = pd.read_csv(f, parse_dates=["datetime"])
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return None
    sub = df[df["datetime"].dt.date == day]["ideal_marginal_price"]
    if sub.empty:
        return None
    return float(sub.astype(float).mean())


def _mean_actual(fn, day: date, data_dir: str) -> float | None:
    try:
        values = fn(day, data_dir=data_dir)
    except (FileNotFoundError, ValueError):
        return None
    if len(values) == 0:
        return None
    return float(sum(values) / len(values))


def build_chart_series(session, *, days: int, today: date, data_dir: str = "data") -> list[dict]:
    """Rows for the last `days` calendar days ending at `today` (inclusive)."""
    candidates: dict[tuple[date, str], tuple] = {}
    for run, case in queries.list_done_public_dispatch_runs(session):
        key = (case.level, run.input_grade)
        slot = _LEVEL_KEYS.get(key)
        if slot is None:
            continue
        # query orders created_at desc -> first hit per (date, slot) is newest
        candidates.setdefault((case.dispatch_date, slot), (run, case))

    rows = []
    start = today - timedelta(days=days - 1)
    for offset in range(days):
        day = start + timedelta(days=offset)
        row: dict = {"date": day.isoformat()}
        row["bolsa_tx1"] = _mean_actual(load_actual_bolsa, day, data_dir)
        row["mpo_xm"] = _mean_actual(load_actual_price, day, data_dir)
        for chart_key, slot_keys in _SERIES_KEYS.items():
            value = None
            run_id = None
            for slot in slot_keys:
                hit = candidates.get((day, slot))
                if hit is not None:
                    run, _case = hit
                    value = _mean_price(run, day)
                    run_id = run.id
                    break
            row[chart_key] = value
            row[f"{chart_key}_run_id"] = run_id
        rows.append(row)
    return rows
```

```python
# services/api/main.py — endpoint (append near the runs endpoints).
# Module-top import changes: add `Query` to the existing
# `from fastapi import Depends, FastAPI, HTTPException` line, and add
# `from services.api.chart import build_chart_series`.

@app.get("/chart/series")
def get_chart_series(
    days: int = Query(30, ge=1, le=90),
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    """Daily COP/MWh series for the Home chart (spec section 7.1)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("America/Bogota")).date()
    return build_chart_series(session, days=days, today=today, data_dir="data")
```

Note: the endpoint test asserts `422` for `days=0`/`days=91` — FastAPI `Query(ge=1, le=90)` produces 422 validation errors. The `data_dir="data"` default means the endpoint returns `null` externals when the repo `data/` dir is absent; the builder tests inject `DD`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_chart.py -q`
Expected: PASS.

- [ ] **Step 5: Run the API suite**

Run: `uv run pytest tests/test_api_runs.py tests/test_api_visibility.py tests/test_api_results.py tests/test_api_log.py tests/test_api_nodal.py tests/test_api_chart.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/chart.py services/api/main.py tests/test_api_chart.py
git commit -m "feat(api): add GET /chart/series with daily means and run precedence"
```

---

### Task 19: Worker wiring (`main_iteration`, sweep/freshness cadence) + README env vars

**Files:**
- Modify: `services/worker/main.py`
- Modify: `tests/test_worker_main.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `plan_tick` (Task 11), `refresh_tick` (Task 14), `sweep_create_rows` (Task 8), `timeutil.sweep_due` (Task 6), `SchedulerConfig.from_env`, `execute_run` (Task 10).
- Produces:
  - `WorkerState` dataclass — `plan_next: float = 0.0`, `fresh_next: float = 0.0`, `last_sweep_date: date | None = None` (monotonic deadlines).
  - `main_iteration(session, state=None, *, now=None, config=None, data_dir="data", results_root="data/results") -> WorkerState` — one pass of the loop body: when `config.daily_enabled`: plan tick at most every `PLAN_TICK_SECONDS`, freshness tick at most every `DATA_REFRESH_INTERVAL_MINUTES`, sweep once per Bogota day at/after `SWEEP_TIME`; then one manual-lane `process_once`. Every tick is exception-isolated (never crashes the loop). `now`/`config` injectable for tests; `now` defaults to `datetime.now(timezone.utc)`, `config` to `SchedulerConfig.from_env()`.
  - `main()` — `while True`: one `main_iteration` per session, `time.sleep(POLL_INTERVAL_SECONDS)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_worker_main.py — append. The file already imports
# `from datetime import date`, `create_engine`, `Session`, `Base`; add
# `datetime` and `timezone` to the datetime import line, then:

from app.scheduler.config import SchedulerConfig
from services.worker.main import WorkerState, main_iteration

NOW = datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc)


def test_main_iteration_disabled_runs_only_manual_lane(monkeypatch):
    session = _session()
    calls = []
    monkeypatch.setattr(
        "app.scheduler.tick.plan_tick", lambda *a, **kw: calls.append("plan")
    )
    monkeypatch.setattr(
        "app.scheduler.refresh.refresh_tick", lambda *a, **kw: calls.append("refresh")
    )
    monkeypatch.setattr(
        "app.scheduler.plans.sweep_create_rows", lambda *a, **kw: calls.append("sweep")
    )
    monkeypatch.setattr(
        "services.worker.main.process_once", lambda *a, **kw: calls.append("manual")
    )

    config = SchedulerConfig(daily_enabled=False)
    main_iteration(session, now=NOW, config=config)
    assert calls == ["manual"]


def test_main_iteration_runs_plan_tick_and_manual_lane(monkeypatch):
    session = _session()
    calls = []
    monkeypatch.setattr(
        "app.scheduler.tick.plan_tick", lambda *a, **kw: calls.append("plan")
    )
    monkeypatch.setattr(
        "app.scheduler.refresh.refresh_tick", lambda *a, **kw: calls.append("refresh")
    )
    monkeypatch.setattr(
        "app.scheduler.plans.sweep_create_rows", lambda *a, **kw: calls.append("sweep")
    )
    monkeypatch.setattr(
        "services.worker.main.process_once", lambda *a, **kw: calls.append("manual")
    )

    config = SchedulerConfig(daily_enabled=True)
    state = main_iteration(session, now=NOW, config=config)
    # first pass: every tick deadline starts at 0.0 -> plan + refresh fire;
    # sweep: 21:00 UTC == 16:00 Bogota >= 05:30 -> fires; manual lane runs once
    assert calls == ["plan", "refresh", "sweep", "manual"]
    assert state.last_sweep_date == date(2026, 9, 8)
    assert state.plan_next > 0

    # second immediate pass: plan tick not due again (60 s), refresh not due
    # (3600 s), sweep already done today -> manual lane only
    calls.clear()
    main_iteration(session, state=state, now=NOW, config=config)
    assert calls == ["manual"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker_main.py -q`
Expected: FAIL — `ImportError: cannot import name 'WorkerState' from 'services.worker.main'`.

- [ ] **Step 3: Write minimal implementation**

```python
# services/worker/main.py — full replacement

import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.db.claim import claim_next_pending_run
from app.db.session import get_engine, get_sessionmaker
from app.scheduler import plans, refresh, timeutil
from app.scheduler.config import SchedulerConfig
from app.scheduler.executor import execute_run
from app.scheduler.tick import plan_tick

POLL_INTERVAL_SECONDS = 5


@dataclass
class WorkerState:
    plan_next: float = 0.0  # time.monotonic() deadlines
    fresh_next: float = 0.0
    last_sweep_date: date | None = None


def process_once(
    session, *, data_dir: str = "data", results_root: str = "data/results"
) -> bool:
    run = claim_next_pending_run(session)
    if run is None:
        return False
    execute_run(session, run, data_dir=data_dir, results_root=results_root)
    return True


def main_iteration(
    session,
    state: WorkerState | None = None,
    *,
    now: datetime | None = None,
    config: SchedulerConfig | None = None,
    data_dir: str = "data",
    results_root: str = "data/results",
) -> WorkerState:
    """One pass of the worker loop body. Scheduled ticks first (each isolated),
    then one manual-lane run. Never raises."""
    if state is None:
        state = WorkerState()
    now = now or datetime.now(timezone.utc)
    config = config or SchedulerConfig.from_env()

    if config.daily_enabled:
        if time.monotonic() >= state.plan_next:
            state.plan_next = time.monotonic() + config.plan_tick_seconds
            try:
                plan_tick(
                    session, now=now, config=config,
                    data_dir=data_dir, results_root=results_root,
                )
            except Exception:
                traceback.print_exc()
        if time.monotonic() >= state.fresh_next:
            state.fresh_next = time.monotonic() + 60 * config.data_refresh_interval_minutes
            try:
                refresh.refresh_tick(session, now=now, config=config, data_dir=data_dir)
            except Exception:
                traceback.print_exc()
        fire, day = timeutil.sweep_due(now, config, state.last_sweep_date)
        if fire:
            state.last_sweep_date = day
            try:
                plans.sweep_create_rows(session, now=now, config=config, data_dir=data_dir)
            except Exception:
                traceback.print_exc()

    try:
        process_once(session, data_dir=data_dir, results_root=results_root)
    except Exception:
        traceback.print_exc()
    return state


def main() -> None:
    engine = get_engine()
    session_factory = get_sessionmaker(engine)
    state = WorkerState()
    while True:
        with session_factory() as session:
            try:
                state = main_iteration(session, state)
            except Exception:
                traceback.print_exc()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
```

Note the behavior change vs the old loop: the worker sleeps `POLL_INTERVAL_SECONDS` unconditionally instead of only when nothing was processed; ticks gate themselves, so this is safe and simpler (documented in Notes).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_worker_main.py tests/test_scheduler_tick.py -q`
Expected: PASS — pre-existing `process_once` tests unchanged; `main_iteration` tests pass with the corrected call order.

- [ ] **Step 5: Update the README (worker env vars + daily runs)**

```markdown
<!-- README.md — append at the end of section 8.3 (after the worker paragraph,
     right before "### Frontend (Fase 4)"); if that heading moved, place it at
     the end of the backend section. -->

#### Scheduler de corridas diarias (automatico)

Desde Fase 7A el worker (ademas de la cola manual de `POST /runs`) ejecuta
planes diarios: por cada fecha corre una version *provisional* (D-1, insumos
pronosticados) y despues una *settled* (cuando XM publica los reales), re-evalua
metricas contra la referencia final (iMAR / bolsa TX1) sin re-resolver, refresca
los year CSVs incrementalmente y expone las corridas de sistema como publicas.
El estado vive en la tabla `run_plans` (no expuesta por API; auditable por
status + logs del worker).

Variables de entorno del worker (todas con default, ver `app/scheduler/config.py`):

| var | default | significado |
|---|---|---|
| `DAILY_ENABLED` | `true` | kill switch del scheduler |
| `SCHEDULER_TZ` | `America/Bogota` | zona de ventanas |
| `PLAN_TICK_SECONDS` | `60` | periodo del plan tick |
| `PLAN_MAX_ATTEMPTS` | `3` | reintentos por ventana |
| `PLAN_RETRY_MINUTES` | `15` | separacion minima entre reintentos |
| `DATA_REFRESH_INTERVAL_MINUTES` | `60` | periodo del freshness tick |
| `DATA_REFRESH_WINDOW_DAYS` | `7` | ventana minima del pull incremental |
| `SWEEP_TIME` | `05:30` | hora diaria de sweeps TX1 |
| `REEVAL_PREIDEAL_TIME` | `18:00` | earliest de reeval_preideal |
| `DAILY_EARLIEST` / `DAILY_DEADLINE` | `15:00` / `23:59` | ventana de corridas frescas (D-1) |

Desplegar con `DAILY_ENABLED=false` deja el worker exactamente como antes.
```

- [ ] **Step 6: Run the full offline suite**

Run: `uv run pytest -q -m "not live"`
Expected: PASS — full suite green with no network calls (live-marked PARATEC/XM tests excluded; the fixture-based scheduler tests never touch the network).

- [ ] **Step 7: Commit**

```bash
git add services/worker/main.py tests/test_worker_main.py README.md
git commit -m "feat(worker): wire scheduler ticks into the polling loop and document env vars"
```

---

## Notes for orchestrator

Spec gaps / ambiguities found while drafting this plan, and how each task resolves them — confirm before implementation if any policy feels wrong:

1. **Spec §5.1 window vs monthly-block series (real gap).** A fixed `DATA_REFRESH_WINDOW_DAYS=7` pull can never capture a month that XM publishes as one block ~1st of the next month (spec §1 evidence: PrecOferDesp). Rows for M.1..M.23 would be outside any 7-day window forever. Resolution (Task 14, documented in `refresh.py`): the request starts at `min(today − window, last_local_day + 1)` — always ≥ the window back AND reaching to the day after the last locally merged row, so the whole closed month arrives on the first pull after publication. Needs spec-owner confirmation.
2. **`metric_set.reference` stamping for settled runs.** Spec §3.3 defines `reference` for re-evals, and §4 says settled evaluation uses `bolsa_tx1`. Inline metrics at finish time have no stamp; this plan stamps at finish only when the executor passes `reference` (settled: `iMAR` for preideal — its metrics always compare vs iMAR — `bolsa_tx1` for ideal; provisional stays NULL until its reeval row runs). `lmp` metrics live in `nodal_results.metrics` (JSON), which has no `reference` column — untouched.
3. **Open-ended kinds never expire on time.** `reeval_ideal`, `lmp_settled`, `preideal_settled`, `ideal_settled` have `(None, None)` windows (input-driven, spec §12) and only skip via the `permanent` failure path (source failed / inputs can never arrive). A date whose TX1 never publishes leaves a visible `pending` row forever — accepted v1 audit behavior; flag if a horizon is wanted.
4. **`attempts` increments at claim, not at failure.** Net semantics match spec §6.2 (one claim = one attempt; retries gated by `attempts < PLAN_MAX_ATTEMPTS`; `PLAN_RETRY_MINUTES` spacing via `due_at` bumps); `mark_plan_failed(retry_at=...)` keeps `finished_at` NULL until the terminal failure.
5. **`plan_tick` executes at most one plan per pass** (the solve blocks the loop; re-entered every `PLAN_TICK_SECONDS`). A 62-row settled-month batch drains at ~1 plan/minute — acceptable for the default config, but if the batch must drain faster, execute N plans per tick instead.
6. **Worker sleeps unconditionally** (`POLL_INTERVAL_SECONDS`) after Task 19 — old loop slept only when idle. Ticks gate themselves; small behavior change for a simpler loop.
7. **"Rewrite atómico vía Storage"** (spec §5.1) is bounded by the Storage protocol, which has no rename/`move` primitive (GCS deliberately deferred). "Atomic" here = complete in-memory keyed merge + one full write through `storage.open(path, "w")`, single writer, then `clear_loader_caches()`; a crash mid-write can truncate the CSV exactly like today's `ensure_*`/`ensure_ofertas_estimado` writers. Adding a `replace` primitive to Storage is a separate change.
8. **Sweep/backfill horizon.** `sweep_create_rows` only considers TX1 dates within the last 7 Bogota days (`_SWEEP_LOOKBACK_DAYS`, code constant, not env), and the monthly gate only settles the single most recent complete month. Older history is deliberately not auto-settled on first deploy (no stampede; spec §12's per-date lanes apply from the deploy date forward).
9. **`list_runs_for_user` is kept** (Task 17 stops importing it in the API) because `tests/test_db_queries.py` may still reference it; remove it in a later cleanup once confirmed unused.
10. **`refresh_tick` never pulls "today"** (`end = Bogota today − 1`): per-date blobs for D publish during D-1 and series rows for today are incomplete. If a same-day partial pull is ever wanted, that is a separate feature.
11. **Pricing/reference details in tests** rely on fixture conventions already verified: iMAR MPO = 150000.0, raw bolsa = 200 COP/kWh (loaders ×1e3 → 200000.0), model MPO 180000.0 → mae 30000.0 vs iMAR and 20000.0 vs bolsa.
12. **Small spec literals kept as code text, not config**: skip reasons `"insumos no publicados"`, `"plan fuente fallido"`, `"ventana vencida"` (spec §9's closed list plus the window-expiry reason) and the `visibility="public"`/`input_grade` values are plain strings throughout, matching the repo's string-typed columns.
