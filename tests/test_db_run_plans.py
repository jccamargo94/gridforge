from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import queries
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
    session.add(
        RunPlan(
            kind="ideal_daily",
            target_date=date(2026, 9, 10),
            due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
        )
    )
    session.commit()
    session.add(
        RunPlan(
            kind="ideal_daily",
            target_date=date(2026, 9, 10),
            due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
        )
    )
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

    claimable = {p.id for p in queries.list_claimable_plans(session, now=now, max_attempts=3)}
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
