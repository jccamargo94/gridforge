"""Regression test: preideal cases must not depend on demaCome (actual commercial
demand), which is published with a several-day lag. For a recent date demaCome has
0 rows, but the PrId forecast and dispo_declarada are available -- build_case must
still derive a 24-hour time set and Pmax from the canonical day range."""

import shutil
from datetime import date
from pathlib import Path

from app.pipeline.case_builder import build_case
from app.schemas.case import DispatchCase, DispatchLevel
from app.schemas.input_pack import InputPack, InputSource

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


def test_preideal_builds_without_dema_come_rows(tmp_path, monkeypatch):
    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    # demaCome sin filas para la fecha del dispatch (rezago de publicacion), pero
    # con una fila de OTRA fecha para que pandas parsee datetime como datetime64.
    (tmp_path / "demaCome" / "demaCome_2024.csv").write_text(
        "datetime,dema\n2024-04-15 00:00:00,1000\n"
    )
    # Particion dispo_come presente (header only) para que ensure_bulk_data_for_year
    # no intente descargarla.
    (tmp_path / "dispo_come").mkdir(exist_ok=True)
    (tmp_path / "dispo_come" / "dispo_come_2024.csv").write_text("datetime,resource_name,dispo\n")
    monkeypatch.setattr(
        "app.data.xm_bulk.ReadDB", lambda: (_ for _ in ()).throw(AssertionError("no network"))
    )
    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")),
    )

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.preideal)
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=str(tmp_path))

    set_data, param_data, _ = build_case(case, inputs)

    T = list(set_data["T"])
    assert len(T) == 24
    assert len(param_data["demand"]) == 24
    gens = set(set_data["I"])
    for (gen, t), _ in param_data["Pmax"].items():
        assert gen in gens
        assert t in T
