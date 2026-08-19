from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base, Case, InputDataset, MetricSet, Run, Scenario


def _memory_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _session():
    engine = _memory_engine()
    return Session(engine)


def test_scenario_round_trip():
    engine = _memory_engine()
    with Session(engine) as session:
        scenario = Scenario(
            mode="arbitrage",
            penetration_level="low",
            units=[{"name": "B1", "mwh_nom": 10.0}],
        )
        session.add(scenario)
        session.commit()
        session.refresh(scenario)
        assert scenario.id
        fetched = session.get(Scenario, scenario.id)
        assert fetched.units == [{"name": "B1", "mwh_nom": 10.0}]


def test_case_run_metric_set_round_trip():
    engine = _memory_engine()
    with Session(engine) as session:
        case = Case(dispatch_date=date(2024, 4, 18), level="preideal")
        session.add(case)
        session.flush()

        run = Run(case_id=case.id, user_id="user-1", status="pending")
        session.add(run)
        session.flush()

        metric_set = MetricSet(run_id=run.id, mae=1.0, rmse=2.0)
        session.add(metric_set)
        session.commit()

        fetched_run = session.get(Run, run.id)
        assert fetched_run.case_id == case.id
        assert fetched_run.status == "pending"

        fetched_metrics = session.get(MetricSet, metric_set.id)
        assert fetched_metrics.run_id == run.id
        assert fetched_metrics.mae == 1.0


def test_case_scenario_id_defaults_to_none():
    engine = _memory_engine()
    with Session(engine) as session:
        case = Case(dispatch_date=date(2024, 4, 18), level="ideal")
        session.add(case)
        session.commit()
        session.refresh(case)
        assert case.scenario_id is None


def test_dispatch_metrics_and_marginal_plants_round_trip():
    engine = _memory_engine()
    with Session(engine) as session:
        case = Case(dispatch_date=date(2024, 4, 18), level="preideal")
        session.add(case)
        session.flush()

        run = Run(
            case_id=case.id,
            user_id="user-1",
            status="pending",
            marginal_plants_path="data/results/mp.csv",
        )
        session.add(run)
        session.flush()

        metric_set = MetricSet(run_id=run.id, dispatch_mae_mw=1.5, dispatch_rmse_mw=2.5)
        session.add(metric_set)
        session.commit()

        assert session.get(Run, run.id).marginal_plants_path == "data/results/mp.csv"
        fetched = session.get(MetricSet, metric_set.id)
        assert fetched.dispatch_mae_mw == 1.5
        assert fetched.dispatch_rmse_mw == 2.5


def test_input_dataset_round_trip():
    engine = _memory_engine()
    with Session(engine) as session:
        row = InputDataset(
            dataset="precio_bolsa",
            partition_key="2024",
            source="pydataxm:PrecBolsNaci",
            checksum="abc123",
            row_count=8784,
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        assert row.id
        assert row.fetched_at is not None

        fetched = session.get(InputDataset, row.id)
        assert fetched.dataset == "precio_bolsa"
        assert fetched.partition_key == "2024"
        assert fetched.row_count == 8784


def test_input_dataset_unique_dataset_partition_key():
    engine = _memory_engine()
    with Session(engine) as session:
        session.add(
            InputDataset(dataset="ofertas", partition_key="2024", source="pydataxm:PrecOferDesp")
        )
        session.commit()

        session.add(
            InputDataset(dataset="ofertas", partition_key="2024", source="pydataxm:PrecOferDesp")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_nodal_result_round_trip():
    from app.db.models import NodalResult

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
    row = NodalResult(
        run_id=run.id,
        metrics={"total_cost": 100.0},
        redistribution=[{"zone": "norte", "delta": 5.0}],
        gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
        network={"name": "three_zone"},
        lmp_path="data/results/x/lmp.csv",
        dispatch_path="data/results/x/dispatch.csv",
        branch_flows_path="data/results/x/branch_flows.csv",
        settlement_status_quo_path="data/results/x/settlement_status_quo.csv",
        settlement_lmp_path="data/results/x/settlement_lmp.csv",
        comparison_path="data/results/x/comparison.csv",
        summary_path="data/results/x/summary.json",
    )
    session.add(row)
    session.commit()
    fetched = session.get(NodalResult, row.id)
    assert fetched.run_id == run.id
    assert fetched.metrics["total_cost"] == 100.0
    assert fetched.network["name"] == "three_zone"
    assert fetched.summary_path == "data/results/x/summary.json"
