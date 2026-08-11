from datetime import date

import pandas as pd

from app.data.agc import ensure_agc_asignado, parse_dagcunidad
from app.storage import LocalStorage

RAW = '"CHIVOR 2",52.5000, 50.5000\n"CHIVOR 3",10.0000, 8.6667\n"CALIMA 1",0.0000, 8.5000\n'


def test_parse_dagcunidad_long_format():
    out = parse_dagcunidad(RAW)
    assert list(out.columns) == ["unit_name", "hour", "agc_mw"]
    assert len(out) == 6  # 3 units x 2 hours
    row = out[(out["unit_name"] == "CHIVOR 2") & (out["hour"] == 0)]
    assert row["agc_mw"].iloc[0] == 52.5


def test_ensure_agc_asignado_aggregates_units_to_resources(tmp_path):
    storage = LocalStorage(str(tmp_path))
    fecha = date(2024, 4, 18)
    raw = '"CHIVOR 2",52.5000, 50.5000\n"CHIVOR 3",10.0000, 8.6667\n"ALTO ANCHICAYA 1",0.0,0.0\n'
    with storage.open(f"{fecha}/dAGCUNIDAD0418.txt", "w") as f:
        f.write(raw)

    ensure_agc_asignado(fecha, str(tmp_path), resource_names=["CHIVOR"])

    out = pd.read_csv(tmp_path / str(fecha) / "agc_asignado.csv", parse_dates=["datetime"])
    assert list(out.columns) == ["datetime", "recurso", "agc"]
    assert set(out["recurso"]) == {"CHIVOR"}
    hour0 = out[out["datetime"] == pd.Timestamp("2024-04-18 00:00")]
    assert hour0["agc"].iloc[0] == (52.5 + 10.0) * 1000  # CHIVOR 2 + CHIVOR 3, MW->kW


def test_ensure_agc_asignado_is_noop_when_file_exists(tmp_path):
    storage = LocalStorage(str(tmp_path))
    fecha = date(2024, 4, 18)
    with storage.open(f"{fecha}/agc_asignado.csv", "w") as f:
        f.write("datetime,recurso,agc\n")

    ensure_agc_asignado(fecha, str(tmp_path), resource_names=["CHIVOR"])
