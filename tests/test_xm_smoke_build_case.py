"""Layer-2 check: build_case's own data-assembly logic (name mapping, unit
scaling, CC-empty path, initial-condition parsing) against the fixture,
independent of whether the model actually solves."""

from datetime import date
from pathlib import Path

import pytest

from app.pipeline.case_builder import build_case
from app.schemas.case import DispatchCase, DispatchLevel
from app.schemas.input_pack import InputPack, InputSource

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


@pytest.fixture
def built():
    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.preideal, solver="cbc")
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=DD)
    return build_case(case, inputs, ders=None)


def test_sets(built):
    set_data, _, _ = built
    assert sorted(set_data["G"]) == ["TERMO1", "TERMO2"]
    assert sorted(set_data["I"]) == ["TERMO1", "TERMO2"]
    assert list(set_data["gen_on"]) == ["TERMO1"]
    assert list(set_data["gen_off"]) == ["TERMO2"]
    assert set_data["combined_cycle"] == []
    assert len(list(set_data["T"])) == 24


def test_params_scaled_correctly(built):
    _, param_data, _ = built
    ts = date(2024, 4, 18)
    # dispo x1e-3 (kW -> MW): 300_000 kW -> 300 MW, 200_000 kW -> 200 MW
    pmax = param_data["Pmax"]
    for hour in range(24):
        import pandas as pd

        t = pd.Timestamp(ts) + pd.Timedelta(hours=hour)
        assert pmax[("TERMO1", t)] == 300.0
        assert pmax[("TERMO2", t)] == 200.0
    # PrId used raw (MW, no scaling): 350 every hour
    assert set(param_data["demand"].values()) == {350}
    # ofertas x1e3 (COP/kWh -> COP/MWh)
    beta = dict(param_data["beta"])
    assert beta == {"TERMO1": 150000.0, "TERMO2": 180000.0}


def test_cold_start_and_commitment_state(built):
    _, param_data, _ = built
    # Cold start selecciona el tipo PAPF (fria) del esquema real (issue #38);
    # el valor es el PAP en COP, sin escalar (el Param es costo fijo por arranque
    # en la funcion objetivo). PAPT02/PAPC02 del fixture valen distinto, asi que
    # un regreso a seleccionar "C" (caliente) falle aqui con 900000.
    assert param_data["cold_start"] == {"TERMO1": 1500000.0, "TERMO2": 1500000.0}
    assert dict(param_data["TMG"]) == {"TERMO1": 1, "TERMO2": 1}
    assert dict(param_data["Ton"]) == {"TERMO1": 5}
    assert param_data["z_on_t0_minus_1"] == {"TERMO1": 1}
    assert param_data["ramp_up"] == {}  # ramps.json={}, RU/RD fall to model default=10000


def test_build_case_raises_clear_error_when_ofertas_empty_for_date(tmp_path, monkeypatch):
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # Write a fixture with header + one row outside the dispatch date so dtypes parse correctly
    # (a header-only CSV makes pandas parse Date as `object`, not datetime64,
    # and crash on `.dt` later -- unrelated to the heuristic, keep a row).
    (tmp_path / "ofertas" / "ofertas_2024.csv").write_text(
        "Date,resource_name,Value\n2024-04-15,TERMO1,150\n"
    )
    # iMAR presente pero sin fila "MPO" parseable -> la heuristica tampoco
    # puede estimar, debe terminar en el mismo raise de siempre. (No lo
    # borramos: ensure_data_for_date reintentaria descargarlo y pisaria el
    # monkeypatch de "no network" de abajo.)
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text("sin fila MPO valida\n")
    # Create the missing dispo_come partition so ensure_bulk_data_for_year doesn't try to fetch it
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text("datetime,resource_name,dispo\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    fecha = date(2024, 4, 18)
    case = DispatchCase(dispatch_date=fecha, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=fecha, source=InputSource.historical, data_dir=str(tmp_path))

    with pytest.raises(ValueError, match="ofertas"):
        build_case(case, inputs)


def test_build_case_uses_heuristic_when_ofertas_missing_but_historical_data_exists(
    tmp_path, monkeypatch
):
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # Sin fila para la fecha del dispatch, pero SI hay precio historico para
    # ambos generadores -> la heuristica puede al menos usar el fallback.
    (tmp_path / "ofertas" / "ofertas_2024.csv").write_text(
        "Date,resource_name,Value\n2024-04-15,TERMO1,150\n2024-04-15,TERMO2,180\n"
    )
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text("datetime,resource_name,dispo\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    fecha = date(2024, 4, 18)
    case = DispatchCase(dispatch_date=fecha, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=fecha, source=InputSource.historical, data_dir=str(tmp_path))

    # No debe lanzar -- la heuristica cubre el hueco.
    _, param_data, _ = build_case(case, inputs)
    beta = dict(param_data["beta"])
    # PrId del fixture usa el nombre "TOTAL" (no matchea TERMO1/TERMO2), asi
    # que ningun recurso se resuelve como marginal -- ambos caen al fallback
    # de ultimo precio publicado, escalado x1e3 (COP/kWh -> COP/MWh).
    assert beta == {"TERMO1": 150000.0, "TERMO2": 180000.0}


def test_build_case_cold_start_empty_when_ofei_has_no_pap(tmp_path, monkeypatch):
    import shutil

    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # Patron real de mes en curso (issue #38): OFEI sin registros PAP (mismo
    # rezago de mes calendario que PrecOferDesp) -- cold_start queda vacio
    # (Param default 0) y el modelo corre de todos modos.
    mo1 = ",".join(["10"] * 24)
    mo2 = ",".join(["5"] * 24)
    (tmp_path / "2024-04-18" / "OFEI0418.txt").write_text(f"TERMO1, MO,{mo1}\nTERMO2, MO,{mo2}\n")
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text("datetime,resource_name,dispo\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    fecha = date(2024, 4, 18)
    case = DispatchCase(dispatch_date=fecha, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=fecha, source=InputSource.historical, data_dir=str(tmp_path))

    _, param_data, _ = build_case(case, inputs)
    assert param_data["cold_start"] == {}
    assert dict(param_data["beta"]) == {"TERMO1": 150000.0, "TERMO2": 180000.0}
