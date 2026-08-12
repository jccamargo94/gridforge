"""Regression test: ideal cases for recent dates must fall back to forecast
inputs when XM has not yet published the real commercial demand (demaCome) and
commercial availability (dispo_come) -- both carry a ~3-day calendar lag.

Before this fix, build_case built an empty model for those dates: demaCome
empty -> T = {} and demand = {}, and dispo_come empty -> every generator Pmax
set to 0 (infeasible). The ideal case must reuse the PrId forecast demand
(demand_pronos, the same the preideal case uses) and the declared availability
(dispo_declarada) as Pmax, and warn loudly that the run used forecast inputs."""

import shutil
from datetime import date
from pathlib import Path

from app.pipeline.case_builder import build_case
from app.schemas.case import DispatchCase, DispatchLevel
from app.schemas.input_pack import InputPack, InputSource

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


def test_ideal_builds_without_dema_come_and_dispo_come_rows(tmp_path, monkeypatch, capsys):
    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # demaCome sin filas para la fecha del dispatch (rezago de publicacion), pero
    # con una fila de OTRA fecha para que pandas parsee datetime como datetime64.
    (tmp_path / "demaCome" / "demaCome_2024.csv").write_text(
        "datetime,dema\n2024-04-15 00:00:00,1000\n"
    )
    # dispo_come sin filas para la fecha del dispatch: header + una fila de otra fecha.
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text(
        "datetime,resource_name,dispo\n2024-04-15 00:00:00,TERMO1,100000\n"
    )
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.ideal)
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=str(tmp_path))

    set_data, param_data, _ = build_case(case, inputs)

    T = list(set_data["T"])
    assert len(T) == 24
    assert len(param_data["demand"]) == 24
    gens = set(set_data["I"])
    for (gen, t), _ in param_data["Pmax"].items():
        assert gen in gens
        assert t in T

    # Pmax must keep declared availability values (nonzero), NOT the 0s that the
    # empty-dispo_come path used to assign (which made the ideal case infeasible).
    pmax_vals = list(param_data["Pmax"].values())
    assert any(p > 0 for p in pmax_vals)

    # Both fallbacks must be announced loudly.
    out = capsys.readouterr().out
    assert "WARNING: DemaCome" in out
    assert "WARNING: DispoCome" in out


def test_ideal_uses_real_demand_when_available(tmp_path, monkeypatch):
    """Cuando demaCome/dispo_come SI tienen datos para la fecha, no hay fallback."""
    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.ideal)
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=str(tmp_path))

    set_data, param_data, _ = build_case(case, inputs)

    assert len(set_data["T"]) == 24
    assert len(param_data["demand"]) == 24
