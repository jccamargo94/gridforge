"""SCN-HS-05-02 / SCN-HC-02-02: chart serving isolates hourly rows by tenant.

A member of tenant A sees public rows and tenant-A rows, never tenant-B
rows; a user with no membership sees public rows only. Each run lives on its
own dispatch day so the per-(day, key) winner ranking cannot shadow rows
across days.
"""

from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base, Tenant, TenantMember
from app.schemas import DispatchCase, DispatchLevel, RunResult
from services.api import chart

DAY_A = date(2024, 4, 16)
DAY_B = date(2024, 4, 17)
DAY_PUB = date(2024, 4, 18)


def _ctx():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_tenant(session, name, *members):
    tenant = Tenant(name=name)
    session.add(tenant)
    session.flush()
    for user in members:
        session.add(TenantMember(tenant_id=tenant.id, user_id=user))
    session.commit()
    return tenant


def _write_price_csv(tmp_path, day: date, price: float) -> str:
    path = tmp_path / f"price-{day.isoformat()}.csv"
    hours = pd.date_range(day.isoformat(), periods=24, freq="h")
    pd.DataFrame({"datetime": hours, "ideal_marginal_price": [price] * 24}).to_csv(
        path, index=False
    )
    return str(path)


def _finish_run(session, tmp_path, *, user_id, visibility, level, grade, day, price):
    run = queries.create_case_and_run(
        session,
        dispatch_date=day,
        level=level,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=user_id,
        visibility=visibility,
        input_grade=grade,
    )
    result = RunResult(
        case=DispatchCase(dispatch_date=day, level=DispatchLevel(level)),
        ok=True,
        price_path=_write_price_csv(tmp_path, day, price),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(tmp_path))
    return run.id


def _values_for_user(session, user_id, tmp_path):
    rows = chart.build_chart_series(session, days=3, today=DAY_PUB, user_id=user_id)
    return {r["date"]: r["ideal_settled"] for r in rows}


def _run_matrix(tmp_path):
    session = _ctx()
    _make_tenant(session, "tenant-a", "user-a", "owner-a")
    _make_tenant(session, "tenant-b", "user-b", "owner-b")
    # public ideal run -> tenant NULL rows (visible to everyone)
    _finish_run(
        session,
        tmp_path,
        user_id=None,
        visibility="public",
        level="ideal",
        grade="settled",
        day=DAY_PUB,
        price=300.0,
    )
    # private ideal run under tenant A (owner-a is member of A only)
    _finish_run(
        session,
        tmp_path,
        user_id="owner-a",
        visibility="private",
        level="ideal",
        grade="settled",
        day=DAY_A,
        price=100.0,
    )
    # private ideal run under tenant B (owner-b is member of B only)
    _finish_run(
        session,
        tmp_path,
        user_id="owner-b",
        visibility="private",
        level="ideal",
        grade="settled",
        day=DAY_B,
        price=200.0,
    )
    return session


def test_member_a_sees_public_and_own_tenant_never_b(tmp_path):
    session = _run_matrix(tmp_path)
    values = _values_for_user(session, "user-a", tmp_path)
    assert values == {
        "2024-04-16": 100.0,  # tenant-A run
        "2024-04-17": None,  # tenant-B run invisible
        "2024-04-18": 300.0,  # public run
    }


def test_member_b_sees_public_and_own_tenant_never_a(tmp_path):
    session = _run_matrix(tmp_path)
    values = _values_for_user(session, "user-b", tmp_path)
    assert values == {
        "2024-04-16": None,  # tenant-A run invisible
        "2024-04-17": 200.0,  # tenant-B run
        "2024-04-18": 300.0,  # public run
    }


def test_non_member_sees_public_only(tmp_path):
    session = _run_matrix(tmp_path)
    values = _values_for_user(session, "outsider", tmp_path)
    assert values == {
        "2024-04-16": None,
        "2024-04-17": None,
        "2024-04-18": 300.0,
    }


def test_hourly_rows_isolated_per_tenant(tmp_path):
    """The hourly arrays follow the same scope as the daily value."""
    session = _run_matrix(tmp_path)
    rows = chart.build_chart_series(session, days=3, today=DAY_PUB, user_id="user-a")
    by_day = {r["date"]: r for r in rows}
    assert by_day["2024-04-16"]["ideal_settled_hourly"] == [100.0] * 24
    assert by_day["2024-04-16"]["ideal_settled_run_id"]
    assert by_day["2024-04-17"]["ideal_settled_hourly"] == [None] * 24
    assert by_day["2024-04-17"]["ideal_settled_run_id"] is None
    assert by_day["2024-04-18"]["ideal_settled_hourly"] == [300.0] * 24
