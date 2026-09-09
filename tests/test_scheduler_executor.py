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
    plan = queries.create_run_plan(session, kind="preideal_daily", target_date=FECHA, due_at=NOW)
    results_root = str(tmp_path / "results")
    execute_plan(
        session,
        plan,
        now=NOW,
        config=CONFIG,
        data_dir=DD,
        results_root=results_root,
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
    plan = queries.create_run_plan(session, kind="ideal_daily", target_date=FECHA, due_at=NOW)

    def _boom(session, run, *, data_dir="data", results_root="data/results"):
        run.status = "failed"
        run.error = "solve exploded"
        session.commit()

    monkeypatch.setattr("app.scheduler.executor.execute_run", _boom)
    execute_plan(
        session,
        plan,
        now=NOW,
        config=CONFIG,
        data_dir=DD,
        results_root=str(tmp_path / "results"),
    )
    assert plan.status == "failed"
    assert plan.error == "solve exploded"
    assert plan.run_id is not None
    # attempts (0) < PLAN_MAX_ATTEMPTS -> retry scheduled 15 minutes out
    assert plan.due_at == datetime(2024, 4, 17, 22, 15, tzinfo=timezone.utc)
    assert plan.finished_at is None
