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


def _plan_row(
    session, kind="preideal_daily", target=TARGET, status="pending", attempts=0, due=NOW_OPEN
):
    plan = RunPlan(
        kind=kind,
        target_date=target,
        status=status,
        attempts=attempts,
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
        tick.inputs,
        "kind_inputs_ready",
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
        tick.inputs,
        "kind_inputs_ready",
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
        tick.inputs,
        "kind_inputs_ready",
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
        tick.inputs,
        "kind_inputs_ready",
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
        tick.inputs,
        "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),
    )
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 1
    session.expire_all()
    assert plan.status == "failed"
    assert plan.error == "RuntimeError: solve exploded"
    # sqlite round-trips DateTime(timezone=True) naive (Wave-1 deviation B);
    # replace(tzinfo=UTC) keeps the assertion backend-neutral, repo pattern.
    retry_at = datetime(2026, 9, 8, 21, 15, tzinfo=UTC)  # retry +15 min
    assert plan.due_at.replace(tzinfo=UTC) == retry_at
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
        tick.inputs,
        "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),
    )
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 1
    session.expire_all()
    assert plan.status == "failed"
    assert plan.attempts == 3
    assert plan.finished_at is not None  # terminal: no retry


def test_plan_tick_skips_unknown_kind_with_reason(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    plan = _plan_row(session, kind="bogus_kind", due=NOW_OPEN)

    def _no_inputs(*a, **kw):
        raise AssertionError("inputs must not be consulted for an unknown kind")

    monkeypatch.setattr(tick.inputs, "kind_inputs_ready", _no_inputs)
    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)
    assert result == 0
    session.expire_all()
    assert plan.status == "skipped"
    assert plan.error == "kind desconocido"


def test_plan_tick_unknown_kind_does_not_block_other_plans(monkeypatch):
    # never let ensure_daily_plans create real rows for "tomorrow"
    monkeypatch.setattr(tick, "ensure_daily_plans", lambda *a, **kw: 0)
    session = _session()
    unknown = _plan_row(session, kind="bogus_kind", due=NOW_OPEN)
    executed = []

    def _fake_execute_plan(session, plan, *, now, config, data_dir, results_root):
        executed.append(plan.kind)
        queries.mark_plan_done(session, plan, run_id="run-1")

    monkeypatch.setattr(tick.executor, "execute_plan", _fake_execute_plan)
    monkeypatch.setattr(
        tick.inputs,
        "kind_inputs_ready",
        lambda *a, **kw: (True, "", False),
    )
    plan = _plan_row(session)  # created after `unknown`: same due, later created_at

    result = tick.plan_tick(session, now=NOW_OPEN, config=CONFIG, data_dir=DD)

    assert result == 1
    assert executed == ["preideal_daily"]
    session.expire_all()
    assert unknown.status == "skipped"
    assert unknown.error == "kind desconocido"
    assert plan.status == "done"
