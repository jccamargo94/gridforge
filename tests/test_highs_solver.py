"""HiGHS (highspy, pure pip) must produce the same dispatch and prices as cbc.

Regression for the `appsi_highs` failure documented in
docs/superpowers/specs/2026-08-05-fase2-docker-design.md: the legacy wrapper
tries to load duals from the *MILP* solve whenever a dual Suffix is importing,
and raises "Solver does not currently have valid duals". The model now keeps the
dual Suffix local during the MILP and only imports it in the pricing LP.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.pipeline.runner import run_case
from app.schemas.case import DispatchCase, DispatchLevel

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


def _run(solver, level, tmp_path):
    case = DispatchCase(dispatch_date=FECHA, level=level, solver=solver)
    result = run_case(case, evaluate=False, out=str(tmp_path / solver), data_dir=DD)
    assert result.ok, result.error
    return (
        pd.read_csv(result.price_path),
        pd.read_csv(result.dispatch_path),
    )


@pytest.mark.parametrize("level", [DispatchLevel.preideal, DispatchLevel.ideal])
def test_appsi_highs_matches_cbc(level, tmp_path):
    price_cbc, disp_cbc = _run("cbc", level, tmp_path)
    price_hi, disp_hi = _run("appsi_highs", level, tmp_path)

    col = "ideal_marginal_price"
    assert len(price_hi) == 24
    pd.testing.assert_series_equal(price_hi[col], price_cbc[col], check_exact=False, rtol=1e-6)
    key = ["generador", "datetime"] if "datetime" in disp_cbc else ["generador"]
    a = disp_cbc.sort_values(key).reset_index(drop=True)
    b = disp_hi.sort_values(key).reset_index(drop=True)
    pd.testing.assert_series_equal(b["dispatch"], a["dispatch"], check_exact=False, atol=1e-6)


def test_cbc_without_pricing_keeps_dual_suffix_importing(tmp_path):
    """compute_prices=False must not change cbc behaviour (price file not empty)."""
    case = DispatchCase(
        dispatch_date=FECHA, level=DispatchLevel.preideal, solver="cbc", compute_prices=False
    )
    result = run_case(case, evaluate=False, out=str(tmp_path / "np"), data_dir=DD)
    assert result.ok, result.error
    assert len(pd.read_csv(result.price_path)) == 24


def _capture_options(monkeypatch):
    """Spy on SolverFactory: record the `options` of every solve, then delegate."""
    import pyomo.environ as pyo

    seen = []
    real = pyo.SolverFactory

    def factory(name, **kw):
        solver = real(name, **kw)
        orig = solver.solve

        def solve(*a, **k):
            seen.append(dict(k.get("options") or {}))
            return orig(*a, **k)

        solver.solve = solve
        return solver

    monkeypatch.setattr("app.model.model.pyo.SolverFactory", factory)
    return seen


def _model(solver):
    from app.model.model import UnitCommitmentModel
    from app.pipeline.case_builder import build_case
    from app.schemas import InputPack, InputSource

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.preideal, solver=solver)
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=DD)
    set_data, param_data, _ = build_case(case, inputs)
    model = UnitCommitmentModel(case=case)
    model.create_model(set_data=set_data, param_data=param_data)
    return model


def test_highs_defaults_to_exact_mip_gap(monkeypatch):
    seen = _capture_options(monkeypatch)
    _model("appsi_highs").solve(solver="appsi_highs")
    assert seen and all(o.get("mip_rel_gap") == 0.0 for o in seen)


def test_explicit_mip_gap_is_respected(monkeypatch):
    seen = _capture_options(monkeypatch)
    _model("appsi_highs").solve(solver="appsi_highs", solver_params={"mip_rel_gap": 0.01})
    assert seen and all(o["mip_rel_gap"] == 0.01 for o in seen)


def test_cbc_options_are_untouched(monkeypatch):
    seen = _capture_options(monkeypatch)
    _model("cbc").solve(solver="cbc")
    assert seen and all("mip_rel_gap" not in o for o in seen)
