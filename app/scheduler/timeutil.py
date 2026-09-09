"""America/Bogota <-> UTC window math for plan kinds.

Window policy (documented for the orchestrator, see plan Notes):
- preideal_daily / ideal_daily: previous Bogota calendar day,
  DAILY_EARLIEST..DAILY_DEADLINE (spec section 4: D-1 15:00-23:59).
- reeval_preideal: same day, REEVAL_PREIDEAL_TIME..DAILY_DEADLINE (iMAR(D) is
  final by ~16:25 Bogota: published 09:00-13:40 with a ~165 min modification
  window, so 18:00 is safely past it).
- reeval_ideal / lmp_settled / preideal_settled / ideal_settled: open-ended —
  execution is input-driven, not wall-clock driven (spec section 12). They
  never auto-skip on time; deterministic input failures skip them with a
  closed reason from the inputs layer.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.scheduler.config import SchedulerConfig

UTC = timezone.utc

_WINDOWED_KINDS = ("preideal_daily", "ideal_daily", "reeval_preideal")


def bogota_tz(tz_name: str) -> tzinfo:
    return ZoneInfo(tz_name)


def in_tz(now: datetime, tz_name: str) -> datetime:
    """Convert an aware datetime into the scheduler zone (stays aware)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(bogota_tz(tz_name))


def tz_date(now: datetime, tz_name: str) -> date:
    return in_tz(now, tz_name).date()


def _parse_hhmm(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def wall_to_utc(d: date, hhmm: str, tz_name: str) -> datetime:
    """Interpret (d, hh:mm) as Bogota wall time and return UTC aware."""
    wall = datetime.combine(d, _parse_hhmm(hhmm), tzinfo=bogota_tz(tz_name))
    return wall.astimezone(UTC)


def window_edges(
    kind: str, target: date, config: SchedulerConfig
) -> tuple[datetime | None, datetime | None]:
    """UTC (open, close) for a plan (kind, target_date); None = unbounded.

    Daily kinds act on the day BEFORE target (the D-1 window of spec section
    4). The close instant is 23:59:00 Bogota — a 00:00 boundary would wrongly
    let the whole next day keep claiming.
    """
    if kind not in _WINDOWED_KINDS:
        return None, None
    prev = target - timedelta(days=1)
    earliest = config.reeval_preideal_time if kind == "reeval_preideal" else config.daily_earliest
    open_at = wall_to_utc(prev, earliest, config.scheduler_tz)
    close_at = wall_to_utc(prev, config.daily_deadline, config.scheduler_tz)
    return open_at, close_at


def retry_due(now: datetime, config: SchedulerConfig) -> datetime:
    return now + timedelta(minutes=config.plan_retry_minutes)


def sweep_due(
    now: datetime, config: SchedulerConfig, last_sweep_date: date | None
) -> tuple[bool, date]:
    """(fire, bogota_date) — fire once per Bogota day at/after sweep_time."""
    wall = in_tz(now, config.scheduler_tz)
    day = wall.date()
    if day == last_sweep_date:
        return False, day
    return wall.time() >= _parse_hhmm(config.sweep_time), day
