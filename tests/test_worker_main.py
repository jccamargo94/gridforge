import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base, Run
from app.scheduler.config import SchedulerConfig
from app.schemas import DispatchCase, DispatchLevel, RunResult
from services.worker.main import main_iteration, process_once

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_process_once_returns_false_when_no_pending_runs():
    session = _session()
    assert process_once(session, data_dir=DD, results_root="data/results") is False
    assert session.scalars(select(Run)).first() is None


def test_process_once_solves_pending_run_end_to_end(tmp_path, monkeypatch):
    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)

    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )

    results_root = str(tmp_path / "results")
    processed = process_once(session, data_dir=DD, results_root=results_root)
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "done", updated.error
    assert updated.price_path is not None
    assert Path(updated.price_path).exists()
    assert Path(updated.out_dir) == Path(results_root) / run.id

    # xm_smoke fixture has an iMAR actuals file (MPO=150000.00) -> metrics compute
    assert queries.get_metric_set(session, run.id) is not None

    # new assertions
    assert updated.log_path is not None
    log_file = Path(updated.log_path)
    assert log_file.exists()
    # Proof the log actually captured run_case's stdout (not an empty file):
    # ensure_data_for_date prints this line when the fixture files already
    # exist, so it deterministically flows through the captured stream. The
    # cbc dual-suffix warning does NOT reach the log (it goes through pyomo's
    # logging handler, not stdout), so it can't be used as the marker here.
    assert "Skipping download" in log_file.read_text()


def test_process_once_marks_run_failed_when_run_case_reports_failure(tmp_path, monkeypatch):
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.preideal, solver="cbc")
    fake_result = RunResult(case=case, ok=False, error="boom")
    monkeypatch.setattr("app.scheduler.executor.run_case", lambda *a, **kw: fake_result)

    processed = process_once(session, data_dir=DD, results_root=str(tmp_path / "results"))
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "failed"
    assert updated.error == "boom"
    assert updated.log_path is not None


def test_process_once_marks_run_failed_when_run_case_raises(tmp_path, monkeypatch):
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )

    def _raise(*a, **kw):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr("app.scheduler.executor.run_case", _raise)

    processed = process_once(session, data_dir=DD, results_root=str(tmp_path / "results"))
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "failed"
    assert updated.error is not None
    assert "solver exploded" in updated.error


def test_process_once_solves_nodal_run_and_persists_nodal_result(tmp_path, monkeypatch):
    from tests.fixtures.nodal import make_three_zone_network

    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)

    session = _session()
    net = make_three_zone_network(congested=True)
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
        nodal_network=net.model_dump(),
    )

    results_root = str(tmp_path / "results")
    processed = process_once(session, data_dir=DD, results_root=results_root)
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "done", updated.error

    nodal = queries.get_nodal_result(session, run.id)
    assert nodal is not None
    assert nodal.metrics["congestion_rent_total"] > 0
    assert nodal.network["name"] == "three_zone"
    for attr in (
        "lmp_path",
        "dispatch_path",
        "branch_flows_path",
        "settlement_status_quo_path",
        "settlement_lmp_path",
        "comparison_path",
        "summary_path",
    ):
        path = getattr(nodal, attr)
        assert path and Path(path).exists()

    # no se escribe MetricSet clásico para corridas nodales
    assert queries.get_metric_set(session, run.id) is None
    # network.json escrito en out_dir
    network_file = Path(results_root) / run.id / "network.json"
    assert network_file.exists()


def test_process_once_nodal_without_network_uses_example(tmp_path, monkeypatch):
    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)

    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
        nodal_network=None,
    )

    results_root = str(tmp_path / "results")
    processed = process_once(session, data_dir=DD, results_root=results_root)
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "done", updated.error
    nodal = queries.get_nodal_result(session, run.id)
    assert nodal is not None
    assert nodal.network["name"] == "example_zonal_network"
    # kW->MW contract (demaCome dema is kW; case_builder applies *1e-3): the
    # example network's demand_shares must produce scaled loads (350 MW total).
    scaled_by_zone = {load["zone"]: load["p_load"] for load in nodal.network["loads"]}
    assert scaled_by_zone["norte"] == pytest.approx([140.0] * 24)
    assert scaled_by_zone["centro"] == pytest.approx([122.5] * 24)
    assert scaled_by_zone["sur"] == pytest.approx([87.5] * 24)


def test_process_once_captures_messages_emitted_via_logging_not_just_print(tmp_path, monkeypatch):
    # Egret/Pyomo warn via `logging`, not print() -- redirect_stdout/stderr alone miss those.
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.preideal, solver="cbc")

    def _fake_run_case(*a, **kw):
        logging.getLogger("egret.fake").warning("dual suffix warning via logging, not print")
        return RunResult(case=case, ok=True)

    monkeypatch.setattr("app.scheduler.executor.run_case", _fake_run_case)

    processed = process_once(session, data_dir=DD, results_root=str(tmp_path / "results"))
    assert processed is True

    updated = queries.get_run(session, run.id)
    log_file = Path(updated.log_path)
    assert "dual suffix warning via logging, not print" in log_file.read_text()


def test_process_once_marks_run_failed_when_run_case_raises_db_error(tmp_path, monkeypatch):
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )

    def _raise_db_error(*a, **kw):
        # Poison the session with a statement error, then surface a
        # SQLAlchemyError, mirroring a DB failure escaping from run_case.
        try:
            kw["session"].execute(text("SELECT * FROM no_such_table"))
        except SQLAlchemyError:
            pass
        raise SQLAlchemyError("db exploded")

    monkeypatch.setattr("app.scheduler.executor.run_case", _raise_db_error)

    processed = process_once(session, data_dir=DD, results_root=str(tmp_path / "results"))
    assert processed is True

    updated = queries.get_run(session, run.id)
    assert updated.status == "failed"
    assert updated.error is not None


NOW = datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc)


def test_main_iteration_disabled_runs_only_manual_lane(monkeypatch):
    session = _session()
    calls = []
    monkeypatch.setattr("app.scheduler.tick.plan_tick", lambda *a, **kw: calls.append("plan"))
    monkeypatch.setattr(
        "app.scheduler.refresh.refresh_tick", lambda *a, **kw: calls.append("refresh")
    )
    monkeypatch.setattr(
        "app.scheduler.plans.sweep_create_rows", lambda *a, **kw: calls.append("sweep")
    )
    monkeypatch.setattr(
        "services.worker.main.process_once", lambda *a, **kw: calls.append("manual")
    )

    config = SchedulerConfig(daily_enabled=False)
    main_iteration(session, now=NOW, config=config)
    assert calls == ["manual"]


def test_main_iteration_runs_plan_tick_and_manual_lane(monkeypatch):
    session = _session()
    calls = []
    monkeypatch.setattr("app.scheduler.tick.plan_tick", lambda *a, **kw: calls.append("plan"))
    monkeypatch.setattr(
        "app.scheduler.refresh.refresh_tick", lambda *a, **kw: calls.append("refresh")
    )
    monkeypatch.setattr(
        "app.scheduler.plans.sweep_create_rows", lambda *a, **kw: calls.append("sweep")
    )
    monkeypatch.setattr(
        "services.worker.main.process_once", lambda *a, **kw: calls.append("manual")
    )

    config = SchedulerConfig(daily_enabled=True)
    state = main_iteration(session, now=NOW, config=config)
    # first pass: every tick deadline starts at 0.0 -> plan + refresh fire;
    # sweep: 21:00 UTC == 16:00 Bogota >= 05:30 -> fires; manual lane runs once
    assert calls == ["plan", "refresh", "sweep", "manual"]
    assert state.last_sweep_date == date(2026, 9, 8)
    assert state.plan_next > 0

    # second immediate pass: plan tick not due again (60 s), refresh not due
    # (3600 s), sweep already done today -> manual lane only
    calls.clear()
    main_iteration(session, state=state, now=NOW, config=config)
    assert calls == ["manual"]
