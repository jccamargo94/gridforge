"""Regression tests: IDEAL mode must enforce real OFEI MO as the Pyomo Pmin param.

PREIDEAL must keep Pmin empty so model.py's ``max_min_op`` default (1 MW) still
applies.  These exercise the real build_case against the xm_smoke fixture.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.pipeline.case_builder import build_case
from app.schemas.case import DispatchCase, DispatchLevel
from app.schemas.input_pack import InputPack, InputSource

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


def _build(level, *, data_dir=DD, **case_kwargs):
    case = DispatchCase(dispatch_date=FECHA, level=level, **case_kwargs)
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=data_dir)
    return build_case(case, inputs)


def _hour(day, hour):
    return pd.Timestamp(day) + pd.Timedelta(hours=hour)


def test_ideal_mode_populates_pmin_from_ofei_mo():
    """IDEAL: Pmin carries real OFEI MO (10/5 MW), one entry per model (i, t)."""
    set_data, param_data, _ = _build(DispatchLevel.ideal)
    pmin = param_data["Pmin"]

    # Hand-derived from the xm_smoke OFEI: TERMO1 MO=10, TERMO2 MO=5 each hour.
    assert pmin[("TERMO1", _hour(FECHA, 0))] == pytest.approx(10.0)
    assert pmin[("TERMO2", _hour(FECHA, 0))] == pytest.approx(5.0)

    # Only (i, t) present in the model sets I x T; extra keys make Pyomo raise.
    expected_keys = {
        (gen, _hour(FECHA, hour)) for gen in ("TERMO1", "TERMO2") for hour in range(24)
    }
    assert set_data["I"] is not None  # sanity: I exists, filter uses it
    assert set(pmin) == expected_keys


def test_ideal_pmin_clamped_to_pmax(tmp_path, monkeypatch):
    """A MO above Pmax must be clamped so pout >= Pmin * z stays feasible."""
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # TERMO1 MO=400 MW but its Pmax is 300 MW; TERMO2 keeps its normal MO=5.
    mo1 = ",".join(["400"] * 24)
    mo2 = ",".join(["5"] * 24)
    (tmp_path / "2024-04-18" / "OFEI0418.txt").write_text(f"TERMO1, MO,{mo1}\nTERMO2, MO,{mo2}\n")
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    # One row outside the dispatch date keeps pandas' datetime dtype valid
    # (a header-only CSV parses datetime as object and breaks `.dt`).
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text(
        "datetime,resource_name,dispo\n2024-04-17 00:00:00,TERMO1,1\n"
    )
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    _, param_data, _ = _build(DispatchLevel.ideal, data_dir=str(tmp_path))
    assert param_data["Pmin"][("TERMO1", _hour(FECHA, 0))] == pytest.approx(300.0)
    assert param_data["Pmin"][("TERMO2", _hour(FECHA, 0))] == pytest.approx(5.0)


def test_ideal_pmin_clamped_to_effective_pmax_after_thermal_fix(monkeypatch):
    """Pmin must be clamped to the Pmax left by thermal_real_generation."""
    import app.pipeline.case_builder as cb

    hours = [_hour(FECHA, h) for h in range(24)]
    # 300000 kWh -> 300 MW, wipes out TERMO1's 300 MW Pmax entirely.
    gene = pd.DataFrame(
        {
            "datetime": hours,
            "resource_name": ["TERMO1"] * 24,
            "gen": [300_000.0] * 24,
        }
    )
    # Real spot must be below TERMO1's 150_000 COP/MWh offer for it to be out
    # of merit; raw CSV is COP/kWh and the loader scales it by 1e3.
    spot_df = pd.DataFrame({"datetime": hours, "precio_bolsa": [50.0] * 24})
    monkeypatch.setattr(cb.loaders, "load_precio_bolsa", lambda *a, **k: spot_df)
    monkeypatch.setattr(cb, "ensure_gene_for_date", lambda *a, **k: None)
    monkeypatch.setattr(cb, "load_gene_day", lambda *a, **k: gene)

    _, param_data, _ = _build(DispatchLevel.ideal, thermal_real_generation=True)
    # TERMO1 effective Pmax is 0 -> Pmin clamped to 0, not the raw MO=10.
    assert param_data["Pmin"][("TERMO1", _hour(FECHA, 0))] == pytest.approx(0.0)
    # TERMO2 untouched: MO=5, Pmax=200 -> stays 5.
    assert param_data["Pmin"][("TERMO2", _hour(FECHA, 0))] == pytest.approx(5.0)


def test_preideal_mode_keeps_pmin_empty():
    """PREIDEAL keeps Pmin={} so the max_min_op=1 default still applies."""
    _, param_data, _ = _build(DispatchLevel.preideal)
    assert param_data["Pmin"] == {}
    assert param_data["max_min_op"] == 1
