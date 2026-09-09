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
    rows = session.scalars(select(RunPlan).where(RunPlan.target_date == target)).all()
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
        "preideal_daily",
        "ideal_daily",
        "reeval_preideal",
    }
    assert ensure_daily_plans(session, now=now, config=CONFIG) == 0


def test_ensure_daily_plans_due_at_is_window_open_when_before_open():
    session = _session()
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)  # 07:00 Bogota, before 15:00
    ensure_daily_plans(session, now=now, config=CONFIG)
    plan = queries.get_run_plan(session, "preideal_daily", date(2026, 9, 9))
    # SQLite stores DateTime(timezone=True) without the offset, so a reloaded
    # due_at comes back naive (repo-known artifact, see mark_plan_failed);
    # stored instants are UTC, so attach UTC before comparing.
    # 15:00 Bogota on 09-08 == 20:00 UTC
    assert plan.due_at.replace(tzinfo=UTC) == datetime(2026, 9, 8, 20, 0, tzinfo=UTC)


def test_ensure_daily_plans_due_at_now_when_late():
    session = _session()
    now = datetime(2026, 9, 8, 23, 0, tzinfo=UTC)  # 18:00 Bogota, after open
    ensure_daily_plans(session, now=now, config=CONFIG)
    plan = queries.get_run_plan(session, "ideal_daily", date(2026, 9, 9))
    assert plan.due_at.replace(tzinfo=UTC) == now


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
    assert created == 62  # 31 days x 2 kinds (March 2024)
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
