from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import queries
from app.db.claim import _locked, claim_next_pending_run, claim_run_by_id, claim_run_plan_by_id
from app.db.models import Base, RunPlan


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_pending_run(session, user_id="user-1"):
    return queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=user_id,
    )


def test_claim_returns_none_when_no_pending_runs():
    session = _session()
    assert claim_next_pending_run(session) is None


def test_claim_marks_run_running_and_sets_started_at():
    session = _session()
    run = _make_pending_run(session)

    claimed = claim_next_pending_run(session)

    assert claimed.id == run.id
    assert claimed.status == "running"
    assert claimed.started_at is not None


def test_claim_does_not_reclaim_an_already_running_run():
    session = _session()
    _make_pending_run(session)

    first = claim_next_pending_run(session)
    second = claim_next_pending_run(session)

    assert first is not None
    assert second is None


def test_claim_picks_oldest_pending_run_first():
    session = _session()
    older = _make_pending_run(session)
    _make_pending_run(session)

    claimed = claim_next_pending_run(session)

    assert claimed.id == older.id


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
