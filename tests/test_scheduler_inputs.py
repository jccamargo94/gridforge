from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base
from app.scheduler import inputs

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_blobs_ready_true_on_smoke_fixture():
    assert inputs.blobs_ready(FECHA, DD) is True
    assert inputs.blobs_ready(date(2024, 4, 17), DD) is False


def test_series_has_day_and_max_date():
    assert inputs.series_has_day("dispo_declarada", FECHA, DD) is True
    assert inputs.series_has_day("dispo_declarada", date(2024, 4, 19), DD) is False
    assert inputs.series_max_date("ofertas", 2024, DD) == FECHA
    assert inputs.series_max_date("no_such_series", 2024, DD) is None


def test_month_complete_false_when_fixture_month_partial():
    # the fixture only has 2024-04-18 rows -> April is not complete
    assert inputs.month_complete("ofertas", date(2024, 4, 1), DD) is False


def test_source_run_done_and_terminal():
    session = _session()
    assert inputs.source_run_done(session, "preideal_daily", FECHA) is False
    assert inputs.source_plan_terminal(session, "preideal_daily", FECHA) is True

    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    plan = queries.create_run_plan(
        session,
        kind="preideal_daily",
        target_date=FECHA,
        due_at=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc),
    )
    queries.mark_plan_done(session, plan, run_id=run.id)
    assert inputs.source_run_done(session, "preideal_daily", FECHA) is False  # run pending
    run.status = "done"
    session.commit()
    assert inputs.source_run_done(session, "preideal_daily", FECHA) is True
    assert inputs.source_plan_terminal(session, "preideal_daily", FECHA) is False


def test_daily_kind_ready_on_fixture():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "preideal_daily", FECHA, data_dir=DD
    )
    assert ready is True
    assert reason == "" and permanent is False


def test_daily_kind_not_ready_without_blobs():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "ideal_daily", date(2024, 4, 17), data_dir=DD
    )
    assert ready is False
    assert reason == inputs.REASON_INPUTS
    assert permanent is False


def test_reeval_preideal_requires_source_done():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "reeval_preideal", FECHA, data_dir=DD
    )
    assert ready is False
    assert permanent is True  # no source plan row ever -> deterministic
    assert reason == inputs.REASON_SOURCE_FAILED


def test_settled_requires_real_month_rows_not_present_in_fixture():
    session = _session()
    ready, reason, permanent = inputs.kind_inputs_ready(
        session, "preideal_settled", FECHA, data_dir=DD
    )
    assert ready is False
    assert reason == inputs.REASON_INPUTS
