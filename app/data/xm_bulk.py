"""Mecanismo 2 (pydataxm bulk) of the XM ingesta design:
docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md sections 3-6.

Fetches DispoDeclarada/PrecOferDesp/DemaCome/PrecBolsNaci/DispoCome from XM's
public bulk API and reshapes them into the same CSV shapes app/data/loaders.py
already reads. Values are written unscaled (see plan Global Constraints for the
verified unit conventions) -- existing loaders/case_builder.py scaling is
untouched.
"""

from datetime import date

import pandas as pd
from pydataxm.pydataxm import ReadDB

from app.db.queries import upsert_input_dataset
from app.storage import get_storage

HOUR_PREFIX = "Values_Hour"


def _melt_hourly(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    hour_cols = [c for c in df.columns if c.startswith(HOUR_PREFIX)]
    long = df.melt(
        id_vars=["Values_code", "Date"], value_vars=hour_cols, var_name="hour", value_name=value_col
    )
    hour_num = long["hour"].str.removeprefix(HOUR_PREFIX).astype(int) - 1
    long["datetime"] = pd.to_datetime(long["Date"]) + pd.to_timedelta(hour_num, unit="h")
    return long.rename(columns={"Values_code": "code"})[["code", "datetime", value_col]]


def fetch_resource_crosswalk(consult) -> pd.DataFrame:
    """code <-> resource_name <-> gen_type, from XM's ListadoRecursos list metric.

    start/end are required by pydataxm's request_data even for list-type
    metrics (it computes a date range unconditionally before branching on
    entity type) but are otherwise unused -- any single date works.
    """
    today = date.today()
    raw = consult.request_data("ListadoRecursos", "Sistema", today, today)
    return raw.rename(
        columns={"Values_Code": "code", "Values_Name": "resource_name", "Values_Type": "gen_type"}
    )[["code", "resource_name", "gen_type"]]


def ensure_dispo_declarada(
    year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None
) -> None:
    storage = get_storage(data_dir)
    path = f"dispo_declarada/dispo_declarada_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("DispoDeclarada", "Recurso", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "dispo")
    merged = long.merge(crosswalk, on="code", how="inner")[
        ["datetime", "resource_name", "dispo", "gen_type"]
    ]
    with storage.open(path, "w") as f:
        merged.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_declarada",
            partition_key=str(year),
            source="pydataxm:DispoDeclarada",
            row_count=len(merged),
        )


def ensure_dispo_come(
    year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None
) -> None:
    storage = get_storage(data_dir)
    path = f"dispo_come/dispo_come_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("DispoCome", "Recurso", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "dispo")
    merged = long.merge(crosswalk, on="code", how="inner")[["datetime", "resource_name", "dispo"]]
    with storage.open(path, "w") as f:
        merged.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_come",
            partition_key=str(year),
            source="pydataxm:DispoCome",
            row_count=len(merged),
        )


def ensure_ofertas(
    year: int, data_dir: str, consult, crosswalk: pd.DataFrame, session=None
) -> None:
    storage = get_storage(data_dir)
    path = f"ofertas/ofertas_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("PrecOferDesp", "Recurso", date(year, 1, 1), date(year, 12, 31))
    daily = raw.rename(columns={"Values_code": "code", "Values_Hour01": "Value"})
    daily = daily[["code", "Date", "Value"]]
    merged = daily.merge(crosswalk, on="code", how="inner")[["Date", "resource_name", "Value"]]
    with storage.open(path, "w") as f:
        merged.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="ofertas",
            partition_key=str(year),
            source="pydataxm:PrecOferDesp",
            row_count=len(merged),
        )


def ensure_dema_come(year: int, data_dir: str, consult, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"demaCome/demaCome_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("DemaCome", "Sistema", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "dema")[["datetime", "dema"]]
    with storage.open(path, "w") as f:
        long.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="demaCome",
            partition_key=str(year),
            source="pydataxm:DemaCome",
            row_count=len(long),
        )


def ensure_precio_bolsa(year: int, data_dir: str, consult, session=None) -> None:
    storage = get_storage(data_dir)
    path = f"precio_bolsa/precio_bolsa_{year}.csv"
    if storage.exists(path):
        return
    raw = consult.request_data("PrecBolsNaci", "Sistema", date(year, 1, 1), date(year, 12, 31))
    long = _melt_hourly(raw, "precio_bolsa")[["datetime", "precio_bolsa"]]
    with storage.open(path, "w") as f:
        long.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="precio_bolsa",
            partition_key=str(year),
            source="pydataxm:PrecBolsNaci",
            row_count=len(long),
        )


_PARTITION_PATHS = {
    "dispo_declarada": "dispo_declarada/dispo_declarada_{year}.csv",
    "ofertas": "ofertas/ofertas_{year}.csv",
    "demaCome": "demaCome/demaCome_{year}.csv",
    "precio_bolsa": "precio_bolsa/precio_bolsa_{year}.csv",
    "dispo_come": "dispo_come/dispo_come_{year}.csv",
}
_NEEDS_CROSSWALK = {"dispo_declarada", "ofertas", "dispo_come"}


def ensure_bulk_data_for_year(year: int, data_dir: str, session=None) -> None:
    storage = get_storage(data_dir)
    missing = {
        name
        for name, template in _PARTITION_PATHS.items()
        if not storage.exists(template.format(year=year))
    }
    if not missing:
        return

    consult = ReadDB()
    crosswalk = fetch_resource_crosswalk(consult) if missing & _NEEDS_CROSSWALK else None

    if "dispo_declarada" in missing:
        ensure_dispo_declarada(year, data_dir, consult, crosswalk, session)
    if "ofertas" in missing:
        ensure_ofertas(year, data_dir, consult, crosswalk, session)
    if "demaCome" in missing:
        ensure_dema_come(year, data_dir, consult, session)
    if "precio_bolsa" in missing:
        ensure_precio_bolsa(year, data_dir, consult, session)
    if "dispo_come" in missing:
        ensure_dispo_come(year, data_dir, consult, crosswalk, session)
