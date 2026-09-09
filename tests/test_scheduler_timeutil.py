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


def test_window_edges_reeval_preideal_is_open_ended_from_reeval_time():
    config = SchedulerConfig()
    open_at, close_at = window_edges("reeval_preideal", date(2026, 9, 10), config)
    # opens D-1 18:00 Bogota (23:00 UTC) and NEVER closes (post-final-review
    # amendment): the reeval evaluates against the FINAL iMAR whenever it
    # runs, so a later day yields the same result — this makes sweep-healed
    # rows functional and covers source runs that finished after D-1 23:59.
    assert open_at == datetime(2026, 9, 9, 23, 0, tzinfo=UTC)  # 18:00 Bogota
    assert close_at is None


def test_window_edges_open_ended_kinds_have_no_bounds():
    config = SchedulerConfig()
    for kind in (
        "reeval_preideal",
        "reeval_ideal",
        "lmp_settled",
        "preideal_settled",
        "ideal_settled",
    ):
        assert window_edges(kind, date(2026, 9, 10), config) is not None
        open_at, close_at = window_edges(kind, date(2026, 9, 10), config)
        if kind == "reeval_preideal":
            assert open_at is not None and close_at is None
        else:
            assert open_at is None and close_at is None


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
