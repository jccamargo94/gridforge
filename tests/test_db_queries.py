from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base, Run
from app.schemas import (
    BessMode,
    BessScenario,
    BessUnit,
    DispatchCase,
    DispatchLevel,
    RunResult,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_scenario_persists_units_as_dicts():
    session = _session()
    scenario = BessScenario(
        mode=BessMode.generator,
        penetration_level="low",
        units=[
            BessUnit(
                name="B1",
                mwh_nom=10,
                hours_to_deplete=2,
                initial_soc=5,
                min_soc=0,
                max_soc=10,
                efficiency=0.9,
                discharge_bid=100.0,
            )
        ],
    )
    row = queries.create_scenario(session, scenario, created_by="user-1")
    assert row.id
    fetched = queries.get_scenario(session, row.id)
    assert fetched.units[0]["name"] == "B1"
    assert fetched.mode == "generator"


def test_create_case_and_run_defaults_to_pending():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    assert run.status == "pending"
    case = queries.get_case(session, run.case_id)
    assert case.level == "preideal"
    assert case.dispatch_date == date(2024, 4, 18)


def test_list_runs_for_user_orders_newest_first():
    session = _session()
    r1 = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    r2 = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 19),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    runs = queries.list_runs_for_user(session, "user-1")
    assert [r.id for r in runs] == [r2.id, r1.id]


def test_list_runs_for_user_excludes_other_users():
    session = _session()
    queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
    )
    runs = queries.list_runs_for_user(session, "user-1")
    assert len(runs) == 1


def test_finish_run_ok_writes_metric_set():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    case = queries.get_case(session, run.case_id)
    dispatch_case = DispatchCase(dispatch_date=case.dispatch_date, level=DispatchLevel.preideal)
    result = RunResult(
        case=dispatch_case,
        ok=True,
        dispatch_path="data/results/x/d.csv",
        price_path="data/results/x/p.csv",
        metrics={"mae": 1.0, "rmse": 2.0, "bias": 0.1, "wape": 0.2, "smape": 0.3, "r2": 0.9},
    )
    queries.finish_run_ok(session, run, result, out_dir="data/results/x")

    updated = queries.get_run(session, run.id)
    assert updated.status == "done"
    assert updated.dispatch_path == "data/results/x/d.csv"

    metric_set = queries.get_metric_set(session, run.id)
    assert metric_set.mae == 1.0
    assert metric_set.rmse == 2.0


def test_finish_run_ok_without_metrics_skips_metric_set():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    case = queries.get_case(session, run.case_id)
    dispatch_case = DispatchCase(dispatch_date=case.dispatch_date, level=DispatchLevel.preideal)
    result = RunResult(case=dispatch_case, ok=True, dispatch_path="d.csv", price_path="p.csv")
    queries.finish_run_ok(session, run, result, out_dir="data/results/x")

    assert queries.get_metric_set(session, run.id) is None


def test_finish_run_failed_sets_error():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    queries.finish_run_failed(session, run, "boom")
    updated = queries.get_run(session, run.id)
    assert updated.status == "failed"
    assert updated.error == "boom"


def test_finish_run_failed_recovers_aborted_transaction():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    # Leave the session in a broken, rollback-required state -- the SQLAlchemy
    # analogue of Postgres's "current transaction is aborted"
    # (InFailedSqlTransaction) that a DB error inside run_case produces. A plain
    # `session.execute(text("SELECT * FROM no_such_table"))` does NOT reproduce
    # this on SQLite: its driver keeps the transaction usable after a statement
    # error, so such a test would pass even without the rollback fix. A failed
    # flush does reproduce it, raising PendingRollbackError on any later commit.
    session.add(Run())
    with pytest.raises(IntegrityError):
        session.flush()

    queries.finish_run_failed(session, run, "boom")

    updated = queries.get_run(session, run.id)
    assert updated.status == "failed"
    assert updated.error == "boom"


def test_upsert_input_dataset_creates_new_row():
    session = _session()
    row = queries.upsert_input_dataset(
        session,
        dataset="precio_bolsa",
        partition_key="2024",
        source="pydataxm:PrecBolsNaci",
        row_count=8784,
    )
    assert row.id
    assert row.fetched_at is not None
    assert row.row_count == 8784


def test_upsert_input_dataset_updates_existing_row_in_place():
    session = _session()
    first = queries.upsert_input_dataset(
        session,
        dataset="precio_bolsa",
        partition_key="2024",
        source="pydataxm:PrecBolsNaci",
        row_count=8784,
    )
    second = queries.upsert_input_dataset(
        session,
        dataset="precio_bolsa",
        partition_key="2024",
        source="pydataxm:PrecBolsNaci",
        row_count=8785,
    )
    assert second.id == first.id
    assert second.row_count == 8785


def test_get_input_dataset_returns_none_when_missing():
    session = _session()
    assert queries.get_input_dataset(session, "precio_bolsa", "2024") is None


def test_get_input_dataset_returns_row_when_present():
    session = _session()
    queries.upsert_input_dataset(
        session, dataset="demaCome", partition_key="2024", source="pydataxm:DemaCome"
    )
    found = queries.get_input_dataset(session, "demaCome", "2024")
    assert found is not None
    assert found.source == "pydataxm:DemaCome"


def test_run_result_carries_nodal():
    from app.schemas import NodalRunResult

    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.lmp)
    result = RunResult(
        case=case,
        ok=True,
        nodal=NodalRunResult(
            lmp_path="data/results/x/lmp.csv",
            metrics={"total_cost": 100.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={"name": "three_zone"},
        ),
    )
    assert result.nodal is not None
    assert result.nodal.lmp_path == "data/results/x/lmp.csv"
    assert result.nodal.metrics["total_cost"] == 100.0


def test_create_case_and_run_stores_nodal_network():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
        nodal_network={"name": "three_zone"},
    )
    case = queries.get_case(session, run.case_id)
    assert case.nodal_network == {"name": "three_zone"}


def test_finish_nodal_run_ok_writes_nodal_result_without_metric_set():
    from app.schemas import NodalRunResult

    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    case = queries.get_case(session, run.case_id)
    dispatch_case = DispatchCase(
        dispatch_date=case.dispatch_date, level=DispatchLevel.lmp, nodal_network=None
    )
    result = RunResult(
        case=dispatch_case,
        ok=True,
        nodal=NodalRunResult(
            lmp_path="data/results/x/lmp.csv",
            dispatch_path="data/results/x/dispatch.csv",
            branch_flows_path="data/results/x/branch_flows.csv",
            settlement_status_quo_path="data/results/x/settlement_status_quo.csv",
            settlement_lmp_path="data/results/x/settlement_lmp.csv",
            comparison_path="data/results/x/comparison.csv",
            summary_path="data/results/x/summary.json",
            metrics={"total_cost": 100.0, "congestion_rent_total": 7200.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={"name": "three_zone"},
        ),
    )
    # el log_path seteado en memoria por el worker debe sobrevivir (sin rollback)
    run.log_path = "data/results/x/run.log"
    queries.finish_nodal_run_ok(session, run, result, out_dir="data/results/x")

    updated = queries.get_run(session, run.id)
    assert updated.status == "done"
    assert updated.log_path == "data/results/x/run.log"
    # clásicas quedan en None (el set nodal es el autoritativo)
    assert updated.dispatch_path is None
    assert updated.price_path is None
    assert queries.get_metric_set(session, run.id) is None

    nodal = queries.get_nodal_result(session, run.id)
    assert nodal is not None
    assert nodal.metrics["congestion_rent_total"] == 7200.0
    assert nodal.network["name"] == "three_zone"
    assert nodal.summary_path == "data/results/x/summary.json"


def test_get_nodal_result_returns_none_when_missing():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    assert queries.get_nodal_result(session, run.id) is None


def test_finish_nodal_run_ok_requires_nodal_result():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="lmp",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    case = queries.get_case(session, run.case_id)
    dispatch_case = DispatchCase(
        dispatch_date=case.dispatch_date, level=DispatchLevel.lmp, nodal_network=None
    )
    result = RunResult(case=dispatch_case, ok=True, nodal=None)
    with pytest.raises(AssertionError):
        queries.finish_nodal_run_ok(session, run, result, out_dir="data/results/x")


def test_create_case_and_run_defaults_to_private_no_grade():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    assert run.user_id is None
    assert run.visibility == "private"
    assert run.input_grade is None


def test_create_case_and_run_system_grade_and_visibility():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
        input_grade="provisional",
    )
    assert run.visibility == "public"
    assert run.input_grade == "provisional"


def test_finish_run_ok_stamps_reference_only_when_given():
    session = _session()
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal)

    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    queries.finish_run_ok(
        session, run, RunResult(case=case, ok=True, metrics={"mae": 1.0}), out_dir="out"
    )
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference is None
    assert ms.evaluated_at is None

    run2 = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    queries.finish_run_ok(
        session,
        run2,
        RunResult(case=case, ok=True, metrics={"mae": 2.0}),
        out_dir="out",
        reference="iMAR",
    )
    ms2 = queries.get_metric_set(session, run2.id)
    assert ms2.reference == "iMAR"
    assert ms2.evaluated_at is not None


def test_update_metric_set_overwrites_price_metrics_and_reference():
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.ideal)
    queries.finish_run_ok(
        session, run, RunResult(case=case, ok=True, metrics={"mae": 1.0}), out_dir="out"
    )
    ms = queries.update_metric_set(
        session, run.id, metrics={"mae": 9.0, "rmse": 3.0}, reference="bolsa_tx1"
    )
    assert ms.reference == "bolsa_tx1"
    assert ms.mae == 9.0
    assert ms.rmse == 3.0
    assert ms.evaluated_at is not None


def test_list_visible_runs_returns_own_and_public():
    session = _session()
    mine = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-1",
    )
    other_private = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 19),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
    )
    public_other = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 20),
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
        input_grade="provisional",
    )
    visible = queries.list_visible_runs(session, "user-1")
    ids = [r.id for r in visible]
    assert mine.id in ids
    assert other_private.id not in ids
    assert public_other.id in ids
