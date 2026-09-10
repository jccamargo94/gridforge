"""Mecanismo 2 (pydataxm bulk) of the XM ingesta design:
docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md sections 3-6.

Fetches DispoDeclarada/PrecOferDesp/DemaCome/PrecBolsNaci/DispoCome from XM's
public bulk API and reshapes them into the same CSV shapes app/data/loaders.py
already reads. Values are written unscaled (see plan Global Constraints for the
verified unit conventions) -- existing loaders/case_builder.py scaling is
untouched.

Windowed incremental refresh (spec docs/superpowers/specs/2026-09-08-daily-runs-design.md
section 5.1): the five real series are pulled per window and keyed-merged into
the year CSVs (existing rows overwritten, new rows appended, full rewrite).
The one-shot ensure_* functions are the bootstrap/backfill path and delegate
to the refresh core over [Jan 1 .. Dec 31]. The caller (refresh_tick in
app/scheduler/refresh.py) clears the loader caches after each pass.
"""

from datetime import date

import pandas as pd
from pydataxm.pydataxm import ReadDB

from app.data.crosswalk import fetch_resource_crosswalk
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


def _read_year_csv(storage, rel_path: str) -> pd.DataFrame | None:
    if not storage.exists(rel_path):
        return None
    with storage.open(rel_path, "rb") as f:
        return pd.read_csv(f)


def _rewrite_year_csv(storage, rel_path: str, df: pd.DataFrame) -> None:
    """Full rewrite through Storage. Single writer: the caller (refresh_tick)
    invalidates the loader caches right after the rewrite."""
    with storage.open(rel_path, "w") as f:
        df.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")


def _merge_keyed(
    existing: pd.DataFrame | None, fresh: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    """Keyed merge: existing rows are overwritten by fresh rows with the same
    key, new rows are appended, the file content is rewritten complete."""
    if existing is None or existing.empty:
        merged = fresh
    else:
        merged = pd.concat([existing, fresh], ignore_index=True)
    time_col = keys[0]
    # Year CSVs read back without parse_dates have the time column as str;
    # normalize before deduping so a str row and a Timestamp row for the same
    # instant collide (spec §5.1 keyed overwrite) and the sort is chronological.
    merged[time_col] = pd.to_datetime(merged[time_col])
    merged = merged.drop_duplicates(subset=keys, keep="last")
    return merged.sort_values(time_col).reset_index(drop=True)


def _merge_into_year_csv(
    storage, rel_path: str, fresh: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    merged = _merge_keyed(_read_year_csv(storage, rel_path), fresh, keys)
    _rewrite_year_csv(storage, rel_path, merged)
    return merged


def _year_range(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def refresh_dispo_declarada(
    start: date, end: date, data_dir: str, consult, crosswalk: pd.DataFrame, session=None
) -> None:
    storage = get_storage(data_dir)
    rel_path = f"dispo_declarada/dispo_declarada_{start.year}.csv"
    raw = consult.request_data("DispoDeclarada", "Recurso", start, end)
    fresh = _melt_hourly(raw, "dispo").merge(crosswalk, on="code", how="inner")[
        ["datetime", "resource_name", "dispo", "gen_type"]
    ]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime", "resource_name"])
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_declarada",
            partition_key=str(start.year),
            source="pydataxm:DispoDeclarada",
            row_count=len(merged),
        )


def ensure_dispo_declarada(year, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"dispo_declarada/dispo_declarada_{year}.csv"):
        return
    refresh_dispo_declarada(*_year_range(year), data_dir, consult, crosswalk, session)


def refresh_dispo_come(start, end, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    rel_path = f"dispo_come/dispo_come_{start.year}.csv"
    raw = consult.request_data("DispoCome", "Recurso", start, end)
    fresh = _melt_hourly(raw, "dispo").merge(crosswalk, on="code", how="inner")[
        ["datetime", "resource_name", "dispo"]
    ]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime", "resource_name"])
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="dispo_come",
            partition_key=str(start.year),
            source="pydataxm:DispoCome",
            row_count=len(merged),
        )


def ensure_dispo_come(year, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"dispo_come/dispo_come_{year}.csv"):
        return
    refresh_dispo_come(*_year_range(year), data_dir, consult, crosswalk, session)


def refresh_dema_come(start, end, data_dir, consult, crosswalk=None, session=None) -> None:
    """crosswalk is accepted for interface uniformity; DemaCome is a system
    series and never needs it."""
    storage = get_storage(data_dir)
    rel_path = f"demaCome/demaCome_{start.year}.csv"
    raw = consult.request_data("DemaCome", "Sistema", start, end)
    fresh = _melt_hourly(raw, "dema")[["datetime", "dema"]]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime"])
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="demaCome",
            partition_key=str(start.year),
            source="pydataxm:DemaCome",
            row_count=len(merged),
        )


def ensure_dema_come(year, data_dir, consult, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"demaCome/demaCome_{year}.csv"):
        return
    refresh_dema_come(*_year_range(year), data_dir, consult, session=session)


def refresh_precio_bolsa(start, end, data_dir, consult, crosswalk=None, session=None) -> None:
    """crosswalk is accepted for interface uniformity; PrecBolsNaci is a
    system series and never needs it."""
    storage = get_storage(data_dir)
    rel_path = f"precio_bolsa/precio_bolsa_{start.year}.csv"
    raw = consult.request_data("PrecBolsNaci", "Sistema", start, end)
    fresh = _melt_hourly(raw, "precio_bolsa")[["datetime", "precio_bolsa"]]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["datetime"])
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="precio_bolsa",
            partition_key=str(start.year),
            source="pydataxm:PrecBolsNaci",
            row_count=len(merged),
        )


def ensure_precio_bolsa(year, data_dir, consult, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"precio_bolsa/precio_bolsa_{year}.csv"):
        return
    refresh_precio_bolsa(*_year_range(year), data_dir, consult, session=session)


def refresh_ofertas(start, end, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    rel_path = f"ofertas/ofertas_{start.year}.csv"
    raw = consult.request_data("PrecOferDesp", "Recurso", start, end)
    # XM publishes PrecOferDesp as a monthly block (~1st of the following
    # month): a window still inside the unpublished period comes back empty
    # (0,0). Nothing to merge; leave the local CSV untouched.
    if raw.empty:
        return
    daily = raw.rename(columns={"Values_code": "code", "Values_Hour01": "Value"})
    daily = daily[["code", "Date", "Value"]]
    fresh = daily.merge(crosswalk, on="code", how="inner")[["Date", "resource_name", "Value"]]
    merged = _merge_into_year_csv(storage, rel_path, fresh, keys=["Date", "resource_name"])
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="ofertas",
            partition_key=str(start.year),
            source="pydataxm:PrecOferDesp",
            row_count=len(merged),
        )


def ensure_ofertas(year, data_dir, consult, crosswalk, session=None) -> None:
    storage = get_storage(data_dir)
    if storage.exists(f"ofertas/ofertas_{year}.csv"):
        return
    refresh_ofertas(*_year_range(year), data_dir, consult, crosswalk, session)


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
