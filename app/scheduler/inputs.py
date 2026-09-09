"""Input-availability predicates for plan kinds (spec section 4).

Every predicate answers: "can a run for (kind, target_date) produce a
meaningful result right now?" — blobs published, year CSVs with rows up to
the needed day, source plan done for reeval kinds. File checks go through
the real loaders (lru-cached; the freshness tick clears them after every
rewrite). Reasons use the closed vocabulary of spec section 9.

Note: `dispo_declarada` rows up to D is the only year-series requirement of
the fresh daily lanes — demaCome(D)/ofertas(D) do not exist on D-1 by
design (spec section 1: ideal falls back to the PrId forecast, offers are
estimated by the heuristic).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.data import loaders
from app.data.paths import resolve_input
from app.db import queries
from app.storage import get_storage

REASON_INPUTS = "insumos no publicados"
REASON_SOURCE_FAILED = "plan fuente fallido"

BLOB_KINDS = ("OFEI", "PrId", "iMAR", "dCondIniU", "dCondIniP", "dAGCUNIDAD")

_SERIES_LOADER = {
    "dispo_declarada": loaders.load_dispo,
    "ofertas": loaders.load_ofertas,
    "demaCome": loaders.load_demanda,
    "dispo_come": loaders.load_dispo_come,
    "precio_bolsa": loaders.load_precio_bolsa,
}


def _days(series: str, df) -> set[date]:
    """Distinct published calendar days in a loader frame."""
    col = df["Date"].dt.date if series == "ofertas" else df["datetime"].dt.date
    return set(col)


def blobs_ready(dispatch_date: date, data_dir: str) -> bool:
    for kind in BLOB_KINDS:
        try:
            resolve_input(kind, dispatch_date, data_dir)
        except FileNotFoundError:
            return False
    return True


def series_max_date(series: str, year: int, data_dir: str) -> date | None:
    """Max published day in the year CSV of `series` (explicit year: callers
    pull for the year of their end day; tests use fixture years)."""
    loader = _SERIES_LOADER.get(series)
    if loader is None:
        return None
    try:
        df = loader(data_dir, year)
    except FileNotFoundError:
        return None
    if df.empty:
        return None
    return max(_days(series, df))


def series_has_day(series: str, day: date, data_dir: str) -> bool:
    loader = _SERIES_LOADER.get(series)
    if loader is None:
        return False
    try:
        df = loader(data_dir, day.year)
    except FileNotFoundError:
        return False
    return day in _days(series, df)


def month_complete(series: str, month_start: date, data_dir: str) -> bool:
    """True when every calendar day of month_start's month has a row."""
    loader = _SERIES_LOADER.get(series)
    if loader is None:
        return False
    try:
        df = loader(data_dir, month_start.year)
    except FileNotFoundError:
        return False
    days = _days(series, df)
    if month_start.month == 12:
        end = date(month_start.year + 1, 1, 1)
    else:
        end = date(month_start.year, month_start.month + 1, 1)
    return all((month_start + timedelta(days=i)) in days for i in range((end - month_start).days))


def network_cached(data_dir: str) -> bool:
    return get_storage(data_dir).exists("topology/network.json")


def source_run_done(session, kind: str, target_date: date) -> bool:
    plan = queries.get_run_plan(session, kind, target_date)
    if plan is None or plan.run_id is None:
        return False
    run = queries.get_run(session, plan.run_id)
    return run is not None and run.status == "done"


def source_plan_terminal(session, kind: str, target_date: date) -> bool:
    """True when (kind, target) can never produce a done source run."""
    plan = queries.get_run_plan(session, kind, target_date)
    if plan is None or plan.status == "skipped":
        return True
    if plan.status == "failed":
        run = queries.get_run(session, plan.run_id) if plan.run_id else None
        return run is None or run.status in ("failed", "skipped")
    return False  # pending / running / done


def kind_inputs_ready(
    session, kind: str, target_date: date, *, data_dir: str
) -> tuple[bool, str, bool]:
    """(ready, reason, permanent) for (kind, target_date).

    permanent=True means the condition can never become true -> the caller
    skips the plan with `reason` instead of waiting for the window to close.
    """
    if kind in ("preideal_daily", "ideal_daily"):
        ok = blobs_ready(target_date, data_dir) and series_has_day(
            "dispo_declarada", target_date, data_dir
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    if kind == "reeval_preideal":
        if source_run_done(session, "preideal_daily", target_date):
            ok = blobs_ready(target_date, data_dir)
            return (ok, "" if ok else REASON_INPUTS, False)
        terminal = source_plan_terminal(session, "preideal_daily", target_date)
        return (False, REASON_SOURCE_FAILED, terminal)

    if kind == "reeval_ideal":
        if source_run_done(session, "ideal_daily", target_date):
            ok = series_has_day("precio_bolsa", target_date, data_dir)
            return (ok, "" if ok else REASON_INPUTS, False)
        terminal = source_plan_terminal(session, "ideal_daily", target_date)
        return (False, REASON_SOURCE_FAILED, terminal)

    if kind == "lmp_settled":
        ok = (
            series_has_day("precio_bolsa", target_date, data_dir)
            and series_has_day("demaCome", target_date, data_dir)
            and series_has_day("dispo_declarada", target_date, data_dir)
            and series_has_day("ofertas", target_date, data_dir)
            and network_cached(data_dir)
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    if kind == "preideal_settled":
        ok = month_complete("ofertas", target_date.replace(day=1), data_dir) and blobs_ready(
            target_date, data_dir
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    if kind == "ideal_settled":
        ok = (
            month_complete("ofertas", target_date.replace(day=1), data_dir)
            and month_complete("demaCome", target_date.replace(day=1), data_dir)
            and month_complete("dispo_come", target_date.replace(day=1), data_dir)
            and series_has_day("precio_bolsa", target_date, data_dir)
        )
        return (ok, "" if ok else REASON_INPUTS, False)

    raise ValueError(f"unknown plan kind: {kind}")
