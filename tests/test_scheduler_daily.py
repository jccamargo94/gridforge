from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base
from app.scheduler.daily import (
    SYSTEM_USER_ID,
    SchedulerConfig,
    enqueue_daily_runs,
    target_date,
)
from app.schemas import BessScenario

CFG = SchedulerConfig(enabled=True)
# 2026-11-03 12:00 UTC == 07:00 Colombia -> target date 2026-11-02
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
DAY = date(2026, 11, 2)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _fail(session, run, at):
    run.status = "failed"
    run.finished_at = at
    session.commit()


def test_target_date_uses_colombia_time_and_lag():
    just_after_midnight_utc = datetime(2026, 11, 3, 3, 0, tzinfo=timezone.utc)  # 22:00 CO, Nov 2
    assert target_date(just_after_midnight_utc, CFG) == date(2026, 11, 1)
    assert target_date(NOW, CFG) == DAY


def test_enqueues_both_levels_as_scheduled_system_runs():
    session = _session()
    created = enqueue_daily_runs(session, NOW, CFG)
    assert sorted(queries.get_case(session, r.case_id).level for r in created) == [
        "ideal",
        "preideal",
    ]
    assert all(r.source == "scheduled" and r.user_id == SYSTEM_USER_ID for r in created)
    assert all(queries.get_case(session, r.case_id).dispatch_date == DAY for r in created)


def test_idempotent_when_called_again():
    session = _session()
    enqueue_daily_runs(session, NOW, CFG)
    assert enqueue_daily_runs(session, NOW + timedelta(minutes=1), CFG) == []


def test_does_nothing_before_configured_hour():
    session = _session()
    early = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)  # 05:00 CO < 06
    assert enqueue_daily_runs(session, early, CFG) == []


def test_skips_level_already_done_manually_but_creates_the_other():
    session = _session()
    manual = queries.create_case_and_run(
        session,
        dispatch_date=DAY,
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    manual.status = "done"
    session.commit()
    created = enqueue_daily_runs(session, NOW, CFG)
    assert [queries.get_case(session, r.case_id).level for r in created] == ["preideal"]


def test_bess_scenario_runs_do_not_block_baseline():
    session = _session()
    scenario_id = queries.create_scenario(
        session,
        BessScenario(mode="arbitrage", penetration_level="low", units=[]),
        created_by="u",
    ).id
    queries.create_case_and_run(
        session,
        dispatch_date=DAY,
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=scenario_id,
        user_id="user-1",
    )
    assert len(enqueue_daily_runs(session, NOW, CFG)) == 2


def test_retries_failed_scheduled_run_only_after_backoff():
    session = _session()
    first = enqueue_daily_runs(session, NOW, CFG)
    for r in first:
        _fail(session, r, NOW)
    assert enqueue_daily_runs(session, NOW + timedelta(minutes=30), CFG) == []
    retried = enqueue_daily_runs(session, NOW + timedelta(minutes=61), CFG)
    assert len(retried) == 2


def test_gives_up_after_max_attempts():
    session = _session()
    t = NOW
    for _ in range(CFG.max_attempts):
        for r in enqueue_daily_runs(session, t, CFG):
            _fail(session, r, t)
        t += timedelta(minutes=61)
    assert enqueue_daily_runs(session, t, CFG) == []


def test_from_env_defaults_disabled_and_parses_overrides():
    assert SchedulerConfig.from_env({}).enabled is False
    cfg = SchedulerConfig.from_env(
        {"DAILY_SCHEDULER_ENABLED": "true", "DAILY_RUN_LEVELS": "ideal", "DAILY_RUN_HOUR": "8"}
    )
    assert cfg.enabled and cfg.levels == ("ideal",) and cfg.hour == 8
