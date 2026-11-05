"""Both min-up formulations must be equivalent on integer points (issue #58)."""

import pytest

from app.benchmarks.formulations import run_one
from app.model.model import UnitCommitmentModel


def test_formulations_reach_same_optimum():
    agg = run_one(6, "aggregated", n_periods=12, time_limit=30, mip_rel_gap=0.0)
    dis = run_one(6, "disaggregated", n_periods=12, time_limit=30, mip_rel_gap=0.0)
    assert agg.objective == pytest.approx(dis.objective, rel=1e-6)
    assert dis.n_constraints > agg.n_constraints


def test_invalid_formulation_rejected():
    from datetime import date

    from app.schemas.case import DispatchCase, DispatchLevel

    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.ideal)
    with pytest.raises(ValueError):
        UnitCommitmentModel(case=case, min_up_formulation="nope")
