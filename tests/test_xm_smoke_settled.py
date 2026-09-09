"""Fase 7A fixture checks: the closed synthetic month (2024-03) powers the
settled lane — month completeness predicates and real settled-path solves
(preideal and ideal) on 2024-03-15 that must NOT touch the offer heuristic.

Fixture price conventions (plan notes #11): iMAR MPO = 150000.0 COP/MWh;
precio_bolsa raw 200 COP/kWh (x1e3 -> 200000.0 COP/MWh once loaded); the
2-generator model prices the marginal TERMO2 at 180000.0 COP/MWh.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from app.data import loaders
from app.pipeline.runner import run_case
from app.scheduler import inputs
from app.schemas.case import DispatchCase, DispatchLevel

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
MARCH = date(2024, 3, 1)
SETTLED = date(2024, 3, 15)
FECHA = date(2024, 4, 18)


def test_year_series_cover_the_whole_closed_month():
    # March is a complete calendar month for every year series the settled
    # gates read (ofertas/demaCome/dispo_come for month_complete; the others
    # are covered by the same regeneration).
    for series in ("ofertas", "demaCome", "dispo_come", "dispo_declarada", "precio_bolsa"):
        assert inputs.month_complete(series, MARCH, DD) is True
    # April-18 rows must be untouched: the legacy smoke day is still present
    # and still the max published date of the year CSVs.
    assert inputs.series_has_day("dispo_declarada", FECHA, DD) is True
    assert inputs.series_max_date("ofertas", 2024, DD) == FECHA
    assert loaders.load_precio_bolsa(DD, 2024)["datetime"].dt.date.max() == FECHA


def test_settled_day_inputs_are_ready():
    # preideal_settled gate: blobs + closed-month ofertas (test above).
    assert inputs.blobs_ready(SETTLED, DD) is True
    # ideal_settled/lmp_settled additionally need real series rows for the day.
    for series in ("ofertas", "demaCome", "dispo_come", "dispo_declarada", "precio_bolsa"):
        assert inputs.series_has_day(series, SETTLED, DD) is True


def test_settled_preideal_run_solves_without_the_offer_heuristic(tmp_path, monkeypatch):
    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    def _no_heuristic(*a, **kw):
        raise AssertionError("settled run must use real ofertas, not the heuristic")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)
    monkeypatch.setattr("app.pipeline.case_builder.ensure_ofertas_estimado", _no_heuristic)

    case = DispatchCase(dispatch_date=SETTLED, level=DispatchLevel.preideal, solver="cbc")
    out = str(tmp_path / "results")
    result = run_case(case, evaluate=True, out=out, data_dir=DD)

    assert result.ok, result.error
    assert result.metrics is not None
    # preideal reference is iMAR MPO (150000) vs model 180000 -> mae 30000
    assert result.metrics["mae"] == 30000.0
    price = pd.read_csv(result.price_path)
    assert len(price) == 24
    assert (price["ideal_marginal_price"] == 180000.0).all()


def test_settled_ideal_run_uses_real_inputs(tmp_path, monkeypatch, capsys):
    """ideal_settled path: real ofertas + real demaCome/dispo_come for the day,
    so neither the offer heuristic nor the forecast fallbacks may run."""

    def _no_network(*a, **kw):
        raise AssertionError(f"unexpected network call: {a} {kw}")

    def _no_heuristic(*a, **kw):
        raise AssertionError("settled run must use real ofertas, not the heuristic")

    monkeypatch.setattr("app.data.download.requests.get", _no_network)
    monkeypatch.setattr("app.pipeline.case_builder.ensure_ofertas_estimado", _no_heuristic)

    case = DispatchCase(dispatch_date=SETTLED, level=DispatchLevel.ideal, solver="cbc")
    out = str(tmp_path / "results")
    result = run_case(case, evaluate=True, out=out, data_dir=DD)

    assert result.ok, result.error
    # demaCome/dispo_come reales publicadas para 2024-03-15 -> sin fallbacks
    assert "WARNING" not in capsys.readouterr().out
    assert result.metrics is not None
    # ideal reference is the bolsa price (raw 200 x1e3 = 200000) -> mae 20000
    assert result.metrics["mae"] == 20000.0
    price = pd.read_csv(result.price_path)
    assert len(price) == 24
    assert (price["ideal_marginal_price"] == 180000.0).all()
