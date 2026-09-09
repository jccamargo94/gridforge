from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import (
    Base,
    Case,
    HourlySeries,
    InputDataset,
    MetricSet,
    Run,
    Scenario,
    Tenant,
    TenantMember,
)


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


def test_tenant_round_trip():
    engine = _memory_engine()
    with Session(engine) as session:
        tenant = Tenant(name="acme-energia")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        assert tenant.id
        assert tenant.created_at is not None

        fetched = session.get(Tenant, tenant.id)
        assert fetched.name == "acme-energia"


def test_tenant_member_round_trip_and_user_lookup():
    engine = _memory_engine()
    with Session(engine) as session:
        tenant = Tenant(name="acme-energia")
        session.add(tenant)
        session.flush()
        member = TenantMember(tenant_id=tenant.id, user_id="user-1")
        session.add(member)
        session.commit()

        stmt = select(TenantMember).where(TenantMember.user_id == "user-1")
        rows = list(session.scalars(stmt))
        assert len(rows) == 1
        assert rows[0].tenant_id == tenant.id
        assert rows[0].user_id == "user-1"


def test_tenant_member_composite_pk_rejects_duplicate_user():
    engine = _memory_engine()
    with Session(engine) as session:
        tenant = Tenant(name="acme-energia")
        session.add(tenant)
        session.flush()
        session.add(TenantMember(tenant_id=tenant.id, user_id="user-1"))
        session.commit()

        session.add(TenantMember(tenant_id=tenant.id, user_id="user-1"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_hourly_series_round_trip_public_and_tenant():
    engine = _memory_engine()
    with Session(engine) as session:
        tenant = Tenant(name="acme-energia")
        session.add(tenant)
        session.flush()
        ts = datetime(2024, 4, 18, 5, 0, tzinfo=timezone.utc)
        public = HourlySeries(
            ts=ts, tenant_id=None, series_key="bolsa_tx1", value=200000.0, source="xm"
        )
        scoped = HourlySeries(
            ts=ts, tenant_id=tenant.id, series_key="bolsa_tx1", value=200000.0, source="xm"
        )
        session.add_all([public, scoped])
        session.commit()

        fetched_public = session.get(HourlySeries, public.id)
        assert fetched_public.tenant_id is None
        assert fetched_public.series_key == "bolsa_tx1"
        assert fetched_public.value == 200000.0
        assert fetched_public.source == "xm"

        fetched_scoped = session.get(HourlySeries, scoped.id)
        assert fetched_scoped.tenant_id == tenant.id


def test_hourly_series_partial_unique_indexes_dedupe_by_scope():
    """SCN-HS-01-02/REQ-HS-01: one unique key per scope — public (tenant NULL)
    and per tenant — over (series_key, ts, source)."""
    engine = _memory_engine()
    with Session(engine) as session:
        tenant = Tenant(name="acme-energia")
        session.add(tenant)
        session.flush()
        ts = datetime(2024, 4, 18, 5, 0, tzinfo=timezone.utc)

        session.add(
            HourlySeries(ts=ts, tenant_id=None, series_key="bolsa_tx1", value=1.0, source="xm")
        )
        session.commit()
        # duplicate public key: second insert must violate the partial unique
        session.add(
            HourlySeries(ts=ts, tenant_id=None, series_key="bolsa_tx1", value=2.0, source="xm")
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # same (series_key, ts, source) under a tenant coexists with the
        # public row (different partial index), but not twice under the tenant
        session.add(
            HourlySeries(ts=ts, tenant_id=tenant.id, series_key="bolsa_tx1", value=3.0, source="xm")
        )
        session.commit()
        session.add(
            HourlySeries(ts=ts, tenant_id=tenant.id, series_key="bolsa_tx1", value=4.0, source="xm")
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # different source under the same scope is a distinct key
        session.add(
            HourlySeries(ts=ts, tenant_id=None, series_key="bolsa_tx1", value=5.0, source="run-1")
        )
        session.commit()

    with Session(engine) as session:
        rows = list(session.scalars(select(HourlySeries)))
        assert len(rows) == 3
