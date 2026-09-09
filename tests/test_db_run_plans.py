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
