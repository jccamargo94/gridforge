from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import queries
from app.db.claim import (
    _locked,
    claim_next_pending_run,
    claim_run_by_id,
    claim_run_plan_by_id,
    reconcile_stale_running,
)
from app.db.models import Base, RunPlan

UTC = timezone.utc
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
PLAN_ERROR = "worker reiniciado con plan en running (stale)"
RUN_ERROR = "run interrumpido por reinicio del worker (stale)"


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


def _stale_plan(session, attempts=1, due=NOW):
    plan = RunPlan(
        kind="preideal_daily",
        target_date=date(2026, 9, 10),
        status="running",
        attempts=attempts,
        due_at=due,
    )
    session.add(plan)
    session.commit()
    return plan


def test_reconcile_stale_running_marks_plan_failed_and_claimable_below_max():
    """F2: a plan the worker died with in 'running' becomes failed with the
    stale marker; attempts were already incremented at claim, so below-max
    rows must be claimable again on the next plan tick."""
    session = _session()
    plan = _stale_plan(session, attempts=1)

    plans, runs = reconcile_stale_running(session, now=NOW)

    assert (plans, runs) == (1, 0)
    session.expire_all()
    assert plan.status == "failed"
    assert plan.error == PLAN_ERROR
    assert plan.finished_at is None  # retry scheduled, not terminal
    # sqlite round-trips DateTime(timezone=True) naive; replace keeps it backend-neutral
    assert plan.due_at.replace(tzinfo=UTC) == NOW
    claimable = queries.list_claimable_plans(session, now=NOW, max_attempts=3)
    assert [p.id for p in claimable] == [plan.id]
    claimed = claim_run_plan_by_id(session, plan.id)
    assert claimed is not None and claimed.attempts == 2


def test_reconcile_stale_running_over_max_plan_stays_unclaimable():
    """attempts already at the cap: the failed row keeps the audit trail but is
    never listed again (terminal in effect)."""
    session = _session()
    plan = _stale_plan(session, attempts=3)

    plans, runs = reconcile_stale_running(session, now=NOW)

    assert (plans, runs) == (1, 0)
    session.expire_all()
    assert plan.status == "failed"
    assert plan.error == PLAN_ERROR
    claimable = queries.list_claimable_plans(session, now=NOW, max_attempts=3)
    assert claimable == []


def test_reconcile_stale_running_fails_manual_run_and_keeps_pending():
    session = _session()
    stale = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    stale.status = "running"
    session.commit()
    pending = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
    )

    plans, runs = reconcile_stale_running(session, now=NOW)

    assert (plans, runs) == (0, 1)
    session.expire_all()
    assert stale.status == "failed"
    assert stale.error == RUN_ERROR
    assert stale.finished_at.replace(tzinfo=UTC) == NOW
    assert pending.status == "pending"  # fresh rows untouched
    assert pending.started_at is None


def test_reconcile_stale_running_touches_nothing_when_clean():
    session = _session()
    pending = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    plan = RunPlan(
        kind="ideal_daily",
        target_date=date(2026, 9, 10),
        status="pending",
        due_at=NOW,
    )
    session.add(plan)
    session.commit()

    assert reconcile_stale_running(session, now=NOW) == (0, 0)
    session.expire_all()
    assert pending.status == "pending"
    assert plan.status == "pending"
