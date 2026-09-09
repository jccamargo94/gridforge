"""Env configuration for the daily scheduler.

Defaults are spec section 8 verbatim; every variable has a default so the
worker runs without any env setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True)
class SchedulerConfig:
    daily_enabled: bool = True
    scheduler_tz: str = "America/Bogota"
    plan_tick_seconds: int = 60
    plan_max_attempts: int = 3
    plan_retry_minutes: int = 15
    data_refresh_interval_minutes: int = 60
    data_refresh_window_days: int = 7
    sweep_time: str = "05:30"
    reeval_preideal_time: str = "18:00"
    daily_earliest: str = "15:00"
    daily_deadline: str = "23:59"

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        return cls(
            daily_enabled=_env_bool("DAILY_ENABLED", True),
            scheduler_tz=os.getenv("SCHEDULER_TZ", "America/Bogota"),
            plan_tick_seconds=_env_int("PLAN_TICK_SECONDS", 60),
            plan_max_attempts=_env_int("PLAN_MAX_ATTEMPTS", 3),
            plan_retry_minutes=_env_int("PLAN_RETRY_MINUTES", 15),
            data_refresh_interval_minutes=_env_int("DATA_REFRESH_INTERVAL_MINUTES", 60),
            data_refresh_window_days=_env_int("DATA_REFRESH_WINDOW_DAYS", 7),
            sweep_time=os.getenv("SWEEP_TIME", "05:30"),
            reeval_preideal_time=os.getenv("REEVAL_PREIDEAL_TIME", "18:00"),
            daily_earliest=os.getenv("DAILY_EARLIEST", "15:00"),
            daily_deadline=os.getenv("DAILY_DEADLINE", "23:59"),
        )
