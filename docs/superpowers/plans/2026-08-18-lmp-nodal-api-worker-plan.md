# Plan — Fase 2: API/worker de persistencia para corridas LMP nodales

**Fecha:** 2026-08-18
**Spec:** `docs/superpowers/specs/2026-08-18-lmp-nodal-api-worker-design.md`
**Fase previa (Fase 1):** `docs/superpowers/plans/2026-08-18-lmp-nodal-market.md`
**Rama base:** `develop` (contiene Fase 1 vía PR #64). Rama de trabajo:
`feat/lmp-nodal-api-worker`. NO commitear a `develop`.

## Convenciones que aplican a todas las tareas

- **Gates antes de cada commit:** `uv run ruff check`, `uv run ruff format --check`,
  `uv run pytest -q`.
- **GIT:** todo comando git con prefijo `PYENV_VERSION=system` (hook de pyenv
  falla en el shell y aborta git en silencio).
- **Tests:** fixtures bajo `tests/fixtures/`, anclados con `Path(__file__).parent`.
  Nunca depender de `data/`.
- Sin líneas de co-autoría con modelos/IA en commits/PR.
- No tocar `app/model/` ni `app/pipeline/case_builder.py`.
- No añadir dependencias nuevas (no hace falta en esta fase; ninguna tarea toca
  `uv.lock`).
- Test-first: escribir el test rojo → correr → implementar → test verde → commit.

## Glosario (dualidad de `nodal_network`)

- `Case.nodal_network` (DB) → dict JSON serializado de la red enviada por el usuario.
- `DispatchCase.nodal_network` (schema) → **path** a un JSON en disco.
- `NodalResult.network` (DB) → snapshot de la red **post-inyección de cargas**
  (con `loads` de 24h si `demand_shares` está seteado).

## Convención de paths (`-lmp`)

`run.out_dir` = `{results_root}/{run.id}` (raíz del run). Los artefactos viven
un nivel más abajo en `{run.id}/{dispatch_date}-lmp/`. Las columnas de path del
`NodalResult` guardan la ruta completa `{out}/{dispatch_date}-lmp/<file>`, que la
API ubica con `get_storage(".").exists(path)`. `save_nodal_artifacts` devuelve
claves: `lmp, dispatch, branch_flows, settlement_status_quo, settlement_lmp,
comparison, summary.json`.

## Olas

| Ola | Tareas | Modo | Depende de | Archivos |
|---|---|---|---|---|
| 1 | T1 (DB: models + migración 0005 + tests), T2 (Schema: NodalRunResult + RunResult + `__init__`) | paralelo | — | T1: `app/db/models.py`, `alembic/versions/0005_nodal_results.py`, `tests/test_db_migrations.py`, `tests/test_db_models.py`; T2: `app/schemas/nodal_run_result.py`, `app/schemas/run_result.py`, `app/schemas/__init__.py` |
| 2 | T3 (run_nodal llena NodalRunResult con paths completos), T4 (queries: create_case_and_run/get_nodal_result/finish_nodal_run_ok) | paralelo | T3←T2; T4←T1,T2 | T3: `app/nodal/runner.py`, `tests/test_nodal_runner.py`; T4: `app/db/queries.py`, `tests/test_db_queries.py` |
| 3 | T5 (worker: network.json + finish_nodal_run_ok), T6 (API: endpoints) | paralelo | T5←T1,T3,T4; T6←T1,T2,T4 | T5: `services/worker/main.py`, `tests/test_worker_main.py`; T6: `services/api/main.py`, `tests/test_api_nodal.py`, `tests/test_api_runs.py` |

Total: 3 olas; olas 1, 2 y 3 paralelas (máx 2 subagentes en paralelo).
Camino crítico: `T2→T3→T5` (3 olas seriales).

---

## Task 1 — DB: modelo `NodalResult` + columna `cases.nodal_network` + migración 0005

**Test rojo.** En `tests/test_db_migrations.py`, agregar:

```python
def test_alembic_upgrade_head_adds_nodal_results_table_and_case_column(tmp_path):
    db_path = tmp_path / "migration_smoke_nodal.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "nodal_results" in tables

    columns = {c["name"] for c in inspect(engine).get_columns("nodal_results")}
    assert {
        "id", "run_id", "metrics", "redistribution", "gen_revenue_by_zone",
        "network", "lmp_path", "dispatch_path", "branch_flows_path",
        "settlement_status_quo_path", "settlement_lmp_path", "comparison_path",
        "summary_path",
    }.issubset(columns)

    unique_constraints = inspect(engine).get_unique_constraints("nodal_results")
    assert {c["name"] for c in unique_constraints} == {"uq_nodal_results_run_id"}

    case_columns = {c["name"] for c in inspect(engine).get_columns("cases")}
    assert "nodal_network" in case_columns
```

En `tests/test_db_models.py`, agregar un round-trip del modelo (sigue el helper
`_session()` ya existente en ese archivo):

```python
def test_nodal_result_round_trip():
    from app.db.models import NodalResult
    session = _session()
    run = queries.create_case_and_run(
        session, dispatch_date=date(2024, 4, 18), level="lmp", solver="cbc",
        compute_prices=True, scenario_id=None, user_id="user-1",
    )
    row = NodalResult(
        run_id=run.id,
        metrics={"total_cost": 100.0},
        redistribution=[{"zone": "norte", "delta": 5.0}],
        gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
        network={"name": "three_zone"},
        lmp_path="data/results/x/lmp.csv",
        dispatch_path="data/results/x/dispatch.csv",
        branch_flows_path="data/results/x/branch_flows.csv",
        settlement_status_quo_path="data/results/x/settlement_status_quo.csv",
        settlement_lmp_path="data/results/x/settlement_lmp.csv",
        comparison_path="data/results/x/comparison.csv",
        summary_path="data/results/x/summary.json",
    )
    session.add(row)
    session.commit()
    fetched = session.get(NodalResult, row.id)
    assert fetched.run_id == run.id
    assert fetched.metrics["total_cost"] == 100.0
    assert fetched.network["name"] == "three_zone"
    assert fetched.summary_path == "data/results/x/summary.json"
```

**Implementación.**

`app/db/models.py` — agregar `nodal_network` a `Case` (tras `scenario_id`):

```python
    scenario_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("scenarios.id"), nullable=True
    )
    nodal_network: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Y agregar el modelo `NodalResult` (tras `MetricSet`):

```python
class NodalResult(Base):
    __tablename__ = "nodal_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id"), unique=True, nullable=False
    )
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    redistribution: Mapped[list | None] = mapped_column(JSON, nullable=True)
    gen_revenue_by_zone: Mapped[list | None] = mapped_column(JSON, nullable=True)
    network: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lmp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    dispatch_path: Mapped[str | None] = mapped_column(String, nullable=True)
    branch_flows_path: Mapped[str | None] = mapped_column(String, nullable=True)
    settlement_status_quo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    settlement_lmp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    comparison_path: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_path: Mapped[str | None] = mapped_column(String, nullable=True)
```

`alembic/versions/0005_nodal_results.py` (nueva migración, `down_revision = "0004"`):

```python
"""add nodal_results and cases.nodal_network

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("nodal_network", sa.JSON(), nullable=True))
    op.create_table(
        "nodal_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("redistribution", sa.JSON(), nullable=True),
        sa.Column("gen_revenue_by_zone", sa.JSON(), nullable=True),
        sa.Column("network", sa.JSON(), nullable=True),
        sa.Column("lmp_path", sa.String(), nullable=True),
        sa.Column("dispatch_path", sa.String(), nullable=True),
        sa.Column("branch_flows_path", sa.String(), nullable=True),
        sa.Column("settlement_status_quo_path", sa.String(), nullable=True),
        sa.Column("settlement_lmp_path", sa.String(), nullable=True),
        sa.Column("comparison_path", sa.String(), nullable=True),
        sa.Column("summary_path", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_nodal_results_run_id"),
    )


def downgrade() -> None:
    op.drop_table("nodal_results")
    op.drop_column("cases", "nodal_network")
```

**Verde + commit.** `uv run pytest -q tests/test_db_migrations.py tests/test_db_models.py`
y luego la suite completa. Commit: `feat(nodal): nodal_results table and cases.nodal_network`.

---

## Task 2 — Schema `NodalRunResult` + `RunResult.nodal`

**Test rojo.** En `tests/test_db_queries.py` (o un pequeño test nuevo), verificar
que `RunResult` acepta `nodal`:

```python
def test_run_result_carries_nodal():
    from app.schemas import NodalRunResult
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.lmp)
    result = RunResult(
        case=case, ok=True,
        nodal=NodalRunResult(
            lmp_path="data/results/x/lmp.csv",
            metrics={"total_cost": 100.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={"name": "three_zone"},
        ),
    )
    assert result.nodal is not None
    assert result.nodal.lmp_path == "data/results/x/lmp.csv"
    assert result.nodal.metrics["total_cost"] == 100.0
```

**Implementación.**

`app/schemas/nodal_run_result.py` (nuevo):

```python
from pydantic import BaseModel


class NodalRunResult(BaseModel):
    lmp_path: str | None = None
    dispatch_path: str | None = None
    branch_flows_path: str | None = None
    settlement_status_quo_path: str | None = None
    settlement_lmp_path: str | None = None
    comparison_path: str | None = None
    summary_path: str | None = None
    metrics: dict[str, float] | None = None
    redistribution: list[dict] | None = None
    gen_revenue_by_zone: list[dict] | None = None
    network: dict | None = None
```

`app/schemas/run_result.py`:

```python
from pydantic import BaseModel

from app.schemas.case import DispatchCase
from app.schemas.nodal_run_result import NodalRunResult


class RunResult(BaseModel):
    case: DispatchCase
    ok: bool
    dispatch_path: str | None = None
    price_path: str | None = None
    bess_path: str | None = None
    bess_summary: dict[str, float] | None = None
    metrics_path: str | None = None
    metrics: dict[str, float] | None = None
    marginal_plants_path: str | None = None
    error: str | None = None
    nodal: NodalRunResult | None = None
```

`app/schemas/__init__.py` — importar y exportar `NodalRunResult`.

**Verde + commit.** `uv run pytest -q` y gates. Commit:
`feat(nodal): NodalRunResult schema on RunResult`.

---

## Task 3 — `run_nodal` llena `NodalRunResult` con paths completos

**Test rojo.** Extender `tests/test_nodal_runner.py`:

```python
def test_run_nodal_populates_nodal_result_with_full_paths(tmp_path):
    net = make_three_zone_network(congested=True)
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(net.model_dump()))
    case = DispatchCase(
        dispatch_date="2024-04-18", level=DispatchLevel.lmp, nodal_network=str(net_path)
    )
    out_dir = str(tmp_path / "out")
    result = run_nodal(case, out=out_dir, data_dir=str(tmp_path))
    assert result.ok, result.error
    nodal = result.nodal
    assert nodal is not None
    # dispatch_path ya no es relativo (bug latente corregido)
    assert result.dispatch_path == f"{out_dir}/2024-04-18-lmp/dispatch.csv"
    assert nodal.lmp_path == f"{out_dir}/2024-04-18-lmp/lmp.csv"
    assert nodal.summary_path == f"{out_dir}/2024-04-18-lmp/summary.json"
    assert nodal.network["name"] == "three_zone"
    assert len(nodal.redistribution) == 3
    assert len(nodal.gen_revenue_by_zone) == 3
    for attr in (
        "lmp_path", "dispatch_path", "branch_flows_path",
        "settlement_status_quo_path", "settlement_lmp_path", "comparison_path",
        "summary_path",
    ):
        assert getattr(nodal, attr) is not None
```

**Implementación.** En `app/nodal/runner.py`, importar `NodalRunResult` y, en el
bloque de éxito de `run_nodal`, construir los paths completos y el `nodal`:

```python
        out_dir = f"{out}/{case.dispatch_date}-lmp"
        paths = save_nodal_artifacts(sol, a, b, comparison, out_dir=out_dir)
        nodal = NodalRunResult(
            lmp_path=f"{out_dir}/{paths['lmp']}",
            dispatch_path=f"{out_dir}/{paths['dispatch']}",
            branch_flows_path=f"{out_dir}/{paths['branch_flows']}",
            settlement_status_quo_path=f"{out_dir}/{paths['settlement_status_quo']}",
            settlement_lmp_path=f"{out_dir}/{paths['settlement_lmp']}",
            comparison_path=f"{out_dir}/{paths['comparison']}",
            summary_path=f"{out_dir}/{paths['summary.json']}",
            metrics=comparison.metrics,
            redistribution=comparison.redistribution.to_dict(orient="records"),
            gen_revenue_by_zone=comparison.gen_revenue_by_zone.to_dict(orient="records"),
            network=net.model_dump(),
        )
        return RunResult(
            case=case,
            ok=True,
            dispatch_path=nodal.dispatch_path,
            metrics=comparison.metrics,
            nodal=nodal,
        )
```

(Import: `from app.schemas import DispatchCase, NodalRunResult, RunResult`.)

**Verde + commit.** `uv run pytest -q tests/test_nodal_runner.py` y la suite.
Commit: `fix(nodal): return full artifact paths in NodalRunResult`.

---

## Task 4 — Queries: `create_case_and_run` nodal_network, `get_nodal_result`, `finish_nodal_run_ok`

**Test rojo.** En `tests/test_db_queries.py`:

```python
def test_create_case_and_run_stores_nodal_network():
    session = _session()
    run = queries.create_case_and_run(
        session, dispatch_date=date(2024, 4, 18), level="lmp", solver="cbc",
        compute_prices=True, scenario_id=None, user_id="user-1",
        nodal_network={"name": "three_zone"},
    )
    case = queries.get_case(session, run.case_id)
    assert case.nodal_network == {"name": "three_zone"}


def test_finish_nodal_run_ok_writes_nodal_result_without_metric_set():
    from app.schemas import NodalRunResult

    session = _session()
    run = queries.create_case_and_run(
        session, dispatch_date=date(2024, 4, 18), level="lmp", solver="cbc",
        compute_prices=True, scenario_id=None, user_id="user-1",
    )
    case = queries.get_case(session, run.case_id)
    dispatch_case = DispatchCase(
        dispatch_date=case.dispatch_date, level=DispatchLevel.lmp, nodal_network=None
    )
    result = RunResult(
        case=dispatch_case, ok=True,
        nodal=NodalRunResult(
            lmp_path="data/results/x/lmp.csv",
            dispatch_path="data/results/x/dispatch.csv",
            branch_flows_path="data/results/x/branch_flows.csv",
            settlement_status_quo_path="data/results/x/settlement_status_quo.csv",
            settlement_lmp_path="data/results/x/settlement_lmp.csv",
            comparison_path="data/results/x/comparison.csv",
            summary_path="data/results/x/summary.json",
            metrics={"total_cost": 100.0, "congestion_rent_total": 7200.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={"name": "three_zone"},
        ),
    )
    # el log_path seteado en memoria por el worker debe sobrevivir (sin rollback)
    run.log_path = "data/results/x/run.log"
    queries.finish_nodal_run_ok(session, run, result, out_dir="data/results/x")

    updated = queries.get_run(session, run.id)
    assert updated.status == "done"
    assert updated.log_path == "data/results/x/run.log"
    # clásicas quedan en None (el set nodal es el autoritativo)
    assert updated.dispatch_path is None
    assert updated.price_path is None
    assert queries.get_metric_set(session, run.id) is None

    nodal = queries.get_nodal_result(session, run.id)
    assert nodal is not None
    assert nodal.metrics["congestion_rent_total"] == 7200.0
    assert nodal.network["name"] == "three_zone"
    assert nodal.summary_path == "data/results/x/summary.json"


def test_get_nodal_result_returns_none_when_missing():
    session = _session()
    run = queries.create_case_and_run(
        session, dispatch_date=date(2024, 4, 18), level="lmp", solver="cbc",
        compute_prices=True, scenario_id=None, user_id="user-1",
    )
    assert queries.get_nodal_result(session, run.id) is None
```

**Implementación.** En `app/db/queries.py`:

- Importar `NodalResult` en el import de `app.db.models` y `NodalRunResult` en el
  import de `app.schemas`.
- `create_case_and_run`: añadir `nodal_network: dict | None = None` a la firma y
  `nodal_network=nodal_network` al `Case(...)`.
- Añadir:

```python
def get_nodal_result(session: Session, run_id: str) -> NodalResult | None:
    stmt = select(NodalResult).where(NodalResult.run_id == run_id)
    return session.scalars(stmt).first()


def finish_nodal_run_ok(session: Session, run: Run, result: RunResult, out_dir: str) -> None:
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc)
    run.out_dir = out_dir
    session.add(run)

    nodal = result.nodal
    session.add(
        NodalResult(
            run_id=run.id,
            metrics=nodal.metrics if nodal else None,
            redistribution=nodal.redistribution if nodal else None,
            gen_revenue_by_zone=nodal.gen_revenue_by_zone if nodal else None,
            network=nodal.network if nodal else None,
            lmp_path=nodal.lmp_path if nodal else None,
            dispatch_path=nodal.dispatch_path if nodal else None,
            branch_flows_path=nodal.branch_flows_path if nodal else None,
            settlement_status_quo_path=nodal.settlement_status_quo_path if nodal else None,
            settlement_lmp_path=nodal.settlement_lmp_path if nodal else None,
            comparison_path=nodal.comparison_path if nodal else None,
            summary_path=nodal.summary_path if nodal else None,
        )
    )
    session.commit()
```

**Nota:** `finish_nodal_run_ok` **NO** hace `session.rollback()` (a diferencia de
`finish_run_failed`); es intencional para que el `run.log_path` en memoria
sobreviva al commit. No agregar rollback.

**Verde + commit.** `uv run pytest -q tests/test_db_queries.py` y la suite.
Commit: `feat(db): nodal run queries (create/get/finish)`. `NodalRunResult` debe
exportarse desde `app.schemas`.

---

## Task 5 — Worker: escribir `network.json` + ramificar a `finish_nodal_run_ok`

**Test rojo.** En `tests/test_worker_main.py`, agregar (usa el fixture nodal de 3
zonas con `loads` directos de 24h → sin dependencia de `demaCome`):

```python
def test_process_once_solves_nodal_run_and_persists_nodal_result(tmp_path, monkeypatch):
    from app.db.models import NodalResult
    from tests.fixtures.nodal import make_three_zone_network

    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)

    session = _session()
    net = make_three_zone_network(congested=True)
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
        nodal_network=net.model_dump(),
    )

    results_root = str(tmp_path / "results")
    processed = process_once(session, data_dir=DD, results_root=results_root)
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "done", updated.error

    nodal = queries.get_nodal_result(session, run.id)
    assert nodal is not None
    assert nodal.metrics["congestion_rent_total"] > 0
    assert nodal.network["name"] == "three_zone"
    for attr in (
        "lmp_path", "dispatch_path", "branch_flows_path",
        "settlement_status_quo_path", "settlement_lmp_path", "comparison_path",
        "summary_path",
    ):
        path = getattr(nodal, attr)
        assert path and Path(path).exists()

    # no se escribe MetricSet clásico para corridas nodales
    assert queries.get_metric_set(session, run.id) is None
    # network.json escrito en out_dir
    network_file = Path(results_root) / run.id / "network.json"
    assert network_file.exists()


def test_process_once_nodal_without_network_uses_example(tmp_path, monkeypatch):
    from app.db.models import NodalResult

    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)

    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
        nodal_network=None,
    )

    results_root = str(tmp_path / "results")
    processed = process_once(session, data_dir=DD, results_root=results_root)
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "done", updated.error
    nodal = queries.get_nodal_result(session, run.id)
    assert nodal is not None
    assert nodal.network["name"] == "example_zonal_network"
```

> Nota sobre el test "uses example": la red de ejemplo tiene `demand_shares` →
> `build_zonal_loads` llama a `load_demanda(DD, 2024)`.
> `tests/fixtures/xm_smoke/demaCome/demaCome_2024.csv` tiene las 24 filas de
> 2024-04-18 (350000 MW/hr), así que resuelve offline. Si la suite es lenta por el MILP (24h×3 gens + DCOPF), darle
> a estos tests un timeout mayor; no achicar la red.

**Implementación.** En `services/worker/main.py`:

- Añadir `import json`.
- En `process_once`, tras `case = _build_case(session, case_row)` y antes del
  `session.commit()`:

```python
        if case_row.nodal_network:
            network_path = f"{out_dir}/network.json"
            with get_storage(".").open(network_path, "w") as f:
                json.dump(case_row.nodal_network, f)
            case.nodal_network = network_path
```

- Reemplazar el bloque de finalización:

```python
        if result.ok:
            if result.nodal is not None:
                queries.finish_nodal_run_ok(session, run, result, out_dir=out_dir)
            else:
                queries.finish_run_ok(session, run, result, out_dir=out_dir)
        else:
            queries.finish_run_failed(
                session, run, result.error or "unknown error", log_path=log_path
            )
```

**Verde + commit.** `uv run pytest -q tests/test_worker_main.py` y la suite.
Commit: `feat(worker): persist nodal runs (network.json + finish_nodal_run_ok)`.

---

## Task 6 — API: lanzar/consultar/descargar corridas nodales

**Test rojo.** Nuevo archivo `tests/test_api_nodal.py`:

```python
from datetime import date

import pandas as pd

from app.db import queries
from app.schemas import DispatchCase, DispatchLevel, NodalRunResult, RunResult
from tests.fixtures.nodal import make_three_zone_network

ZONES = ["norte", "centro", "sur"]


def _seed_done_nodal_run(api_client, tmp_path):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "lmp",
            "nodal_network": make_three_zone_network(congested=True).model_dump(),
        },
    )
    run_id = resp.json()["run_id"]

    run_out = tmp_path / "results" / run_id
    out_dir = run_out / "2024-04-18-lmp"
    out_dir.mkdir(parents=True)

    lmp_rows = [
        {"timestamp": f"2024-04-18 {h:02d}:00", "bus": z, "lmp": 20.0 + h}
        for h in range(24)
        for z in ZONES
    ]
    pd.DataFrame(lmp_rows).to_csv(out_dir / "lmp.csv", index=False)
    pd.DataFrame([{"generator": "G_N", "zone": "norte", "fuel": "hydro", "hour": 0, "dispatch_mw": 100.0}]).to_csv(out_dir / "dispatch.csv", index=False)
    pd.DataFrame([{"timestamp": "2024-04-18 00:00", "branch": "NC", "flow_mw": 10.0}]).to_csv(out_dir / "branch_flows.csv", index=False)
    pd.DataFrame([{"zone": "norte", "hour": 0, "load_payment": 1.0, "gen_revenue": 1.0, "uplift": 0.0}]).to_csv(out_dir / "settlement_status_quo.csv", index=False)
    pd.DataFrame([{"zone": "norte", "hour": 0, "load_payment": 1.0, "gen_revenue": 1.0}]).to_csv(out_dir / "settlement_lmp.csv", index=False)
    pd.DataFrame([{"zone": "norte", "load_payment_a": 1.0, "load_payment_b": 2.0, "delta": 1.0}]).to_csv(out_dir / "comparison.csv", index=False)
    (out_dir / "summary.json").write_text('{"metrics": {"total_cost": 100.0}}')

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.lmp)
    result = RunResult(
        case=case, ok=True,
        nodal=NodalRunResult(
            lmp_path=str(out_dir / "lmp.csv"),
            dispatch_path=str(out_dir / "dispatch.csv"),
            branch_flows_path=str(out_dir / "branch_flows.csv"),
            settlement_status_quo_path=str(out_dir / "settlement_status_quo.csv"),
            settlement_lmp_path=str(out_dir / "settlement_lmp.csv"),
            comparison_path=str(out_dir / "comparison.csv"),
            summary_path=str(out_dir / "summary.json"),
            metrics={"total_cost": 100.0, "congestion_rent_total": 7200.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={"name": "three_zone"},
        ),
    )
    queries.finish_nodal_run_ok(session, run, result, out_dir=str(run_out))
    session.close()
    return run_id


def test_create_nodal_run_with_network(api_client):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "lmp",
            "nodal_network": make_three_zone_network(congested=True).model_dump(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    run_id = body["run_id"]
    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    case = queries.get_case(session, run.case_id)
    assert case.nodal_network["name"] == "three_zone"
    session.close()


def test_create_run_rejects_nodal_network_for_non_lmp(api_client):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "preideal",
            "nodal_network": make_three_zone_network().model_dump(),
        },
    )
    assert resp.status_code == 400


def test_get_nodal_run_detail(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"] is None
    assert body["artifacts"] == {
        "dispatch": False, "prices": False, "bess": False, "marginal_plants": False,
    }
    nodal = body["nodal"]
    assert nodal["network"]["name"] == "three_zone"
    assert nodal["metrics"]["congestion_rent_total"] == 7200.0
    assert nodal["artifacts"] == {name: True for name in (
        "lmp", "dispatch", "branch_flows", "settlement_status_quo",
        "settlement_lmp", "comparison", "summary",
    )}


def test_get_nodal_artifact_lmp_returns_72_rows(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/nodal/lmp")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 72
    assert rows[0]["bus"] == "norte"


def test_get_nodal_artifact_summary_returns_parsed_json(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/nodal/summary")
    assert resp.status_code == 200
    assert resp.json()["metrics"]["total_cost"] == 100.0


def test_download_nodal_summary(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/download/nodal/summary.json")
    assert resp.status_code == 200


def test_get_nodal_artifact_404_for_unknown_artifact(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/nodal/not-a-real-artifact")
    assert resp.status_code == 404


def test_nodal_run_ownership_404(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    run.user_id = "user-2"
    session.commit()
    session.close()
    resp = api_client.get(f"/runs/{run_id}/nodal/lmp")
    assert resp.status_code == 404
```

**Implementación.** En `services/api/main.py`:

- Imports nuevos: `import json`, `from app.nodal.network.schemas import NodalNetwork`.
- `RunCreateRequest`: añadir `nodal_network: NodalNetwork | None = None`.
- En `create_run`, antes de `queries.create_case_and_run`:

```python
    if body.nodal_network is not None and body.level != DispatchLevel.lmp:
        raise HTTPException(status_code=400, detail="nodal_network is only valid for level lmp")
```

  y pasar `nodal_network=body.nodal_network.model_dump() if body.nodal_network else None`.

- Añadir (junto a `_ARTIFACT_PATHS`):

```python
_NODAL_ARTIFACT_PATHS = {
    "lmp": "lmp_path",
    "dispatch": "dispatch_path",
    "branch_flows": "branch_flows_path",
    "settlement_status_quo": "settlement_status_quo_path",
    "settlement_lmp": "settlement_lmp_path",
    "comparison": "comparison_path",
    "summary": "summary_path",
}


def _get_owned_nodal_result(session, run, artifact: str):
    nodal = queries.get_nodal_result(session, run.id)
    if nodal is None:
        raise HTTPException(status_code=404, detail="run has no nodal results yet")
    attr = _NODAL_ARTIFACT_PATHS.get(artifact)
    if attr is None:
        raise HTTPException(status_code=404, detail="unknown artifact")
    path = getattr(nodal, attr)
    if path is None:
        raise HTTPException(status_code=404, detail=f"run has no {artifact} artifact yet")
    if not get_storage(".").exists(path):
        raise HTTPException(status_code=404, detail="artifact file missing on disk")
    return nodal, path
```

- En `get_run_detail`, tras `out["price_series"] = ...`:

```python
    nodal_result = queries.get_nodal_result(session, run.id)
    out["nodal"] = (
        {
            "metrics": nodal_result.metrics,
            "redistribution": nodal_result.redistribution,
            "gen_revenue_by_zone": nodal_result.gen_revenue_by_zone,
            "network": nodal_result.network,
            "artifacts": {
                name: getattr(nodal_result, attr) is not None
                for name, attr in _NODAL_ARTIFACT_PATHS.items()
            },
        }
        if nodal_result
        else None
    )
```

- Nuevos endpoints. `_get_owned_nodal_result` resuelve por nombre **lógico**
  (`lmp`, `dispatch`, ..., `summary`). El endpoint JSON sirve solo nombres
  lógicos. El endpoint de descarga **normaliza** el nombre quitando el sufijo
  `.csv`/`.json` del archivo en disco, de modo que `summary.json` y `summary`
  (o `lmp` y `lmp.csv`) resuelven igual:

```python
def _normalize_nodal_artifact(artifact: str) -> str:
    if artifact.endswith(".csv") or artifact.endswith(".json"):
        return artifact[: -len(".csv")] if artifact.endswith(".csv") else artifact[: -len(".json")]
    return artifact


@app.get("/runs/{run_id}/nodal/{artifact}")
def get_nodal_artifact(
    run_id: str,
    artifact: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    nodal, path = _get_owned_nodal_result(session, run, artifact)
    if artifact == "summary":
        with get_storage(".").open(path) as f:
            return json.load(f)
    with get_storage(".").open(path) as f:
        df = pd.read_csv(f)
    return df.to_dict(orient="records")


@app.get("/runs/{run_id}/download/nodal/{artifact}")
def download_nodal_artifact(
    run_id: str,
    artifact: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    logical = _normalize_nodal_artifact(artifact)
    _, path = _get_owned_nodal_result(session, run, logical)
    return FileResponse(path)
```

> Ojo con el orden de rutas de FastAPI: `/runs/{run_id}/nodal/{artifact}` y
> `/runs/{run_id}/download/nodal/{artifact}` no colisionan con `/runs/{run_id}/{artifact}`
> ni con `/runs/{run_id}/download/{artifact}` porque las rutas existentes tienen
> un solo segmento tras `run_id`. Verificar con la suite.
>
> Formato: las líneas largas de los `pd.DataFrame(...)` de los tests de T6
> exceden `line-length=100`; `ruff format` las reenvuelve. El subagente debe
> correr `uv run ruff format` (y `--check`) para dejarlas formateadas.

**Verde + commit.** `uv run pytest -q tests/test_api_nodal.py tests/test_api_runs.py tests/test_api_results.py`
y la suite completa. Commit: `feat(api): launch/query/download nodal runs`.

---

## Definition of Done (verificación final del orquestador)

- [ ] `uv run pytest -q` verde (suite completa) + `uv run ruff check` y
      `uv run ruff format --check` limpios.
- [ ] Migración 0005: `alembic upgrade head` crea `nodal_results` (7 paths +
      `metrics`/`redistribution`/`gen_revenue_by_zone`/`network` + unique
      `uq_nodal_results_run_id`) y columna `cases.nodal_network`; `downgrade` los
      revierte. Verificado por `tests/test_db_migrations.py`.
- [ ] E2E worker: corrida nodal (`level="lmp"` + red) → `run.status=="done"`,
      `NodalResult` con 7 paths que existen en disco, sin `MetricSet`.
- [ ] Métricas de referencia: `NodalResult.metrics` contiene
      `total_cost, total_load_payment_a, total_load_payment_b, load_payment_delta,
      total_gen_revenue_a, total_gen_revenue_b, gen_revenue_delta,
      congestion_rent_total` + `price_avg_*`/`price_vol_*` para las 3 zonas;
      `redistribution` len 3, `gen_revenue_by_zone` len 3.
- [ ] API: `POST /runs` nodal → 200 + run_id (400 si `nodal_network` con
      `level != lmp`); `GET /runs/{id}` → `metrics: null` + `nodal` con flags
      true; `GET /runs/{id}/nodal/lmp` → 72 registros (24h × 3 zonas);
      `GET /runs/{id}/download/nodal/summary.json` → 200; ownership 404.
- [ ] Regresión: `level="lmp"` sin `nodal_network` corre contra la red de ejemplo
      (`nodal.network["name"] == "example_zonal_network"`).
- [ ] Ramas de tarea integradas a `feat/lmp-nodal-api-worker` y pusheadas.
- [ ] Sin cambios en `app/model/` ni `app/pipeline/case_builder.py`.

## Items diferidos (fuera de esta fase)

- Frontend consumiendo el objeto `nodal` (Fase 3). Hasta entonces, la UI actual
  muestra flags clásicos en false para corridas nodales (asimetría aceptada).
- Redes reutilizables en tabla `networks` + FK (vía de upgrade futura).
- Prescient (Fase 4).
