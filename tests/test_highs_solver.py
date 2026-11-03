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
