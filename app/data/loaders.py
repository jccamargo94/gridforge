"""Readers for the root-level XM CSVs.

Unit conversions that were previously scattered across the scripts are applied
here, in exactly one place (e.g. precio_bolsa is scaled to COP/MWh).

Year-level loaders are cached (lru_cache).  A single process that builds many
dispatch dates within the same year will read each CSV at most once.
"""

import functools

import pandas as pd

from app.storage import get_storage


@functools.lru_cache(maxsize=16)
def load_dispo(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"dispo_declarada/dispo_declarada_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


@functools.lru_cache(maxsize=16)
def load_ofertas(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"ofertas/ofertas_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["Date"])


@functools.lru_cache(maxsize=16)
def load_demanda(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"demaCome/demaCome_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


def load_agc(data_dir: str, dispatch_date) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"{dispatch_date}/agc_asignado.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


def load_parametros_plantas(data_dir: str = "data") -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open("parametros_plantas.csv", "rb") as f:
        return pd.read_csv(f)


@functools.lru_cache(maxsize=16)
def load_precio_bolsa(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"precio_bolsa/precio_bolsa_{year}.csv", "rb") as f:
        df = pd.read_csv(f, parse_dates=["datetime"])
    df["precio_bolsa"] = df["precio_bolsa"] * 1e3
    return df


@functools.lru_cache(maxsize=16)
def load_dispo_come(data_dir: str, year: int) -> pd.DataFrame:
    storage = get_storage(data_dir)
    with storage.open(f"dispo_come/dispo_come_{year}.csv", "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])


def clear_loader_caches() -> None:
    """Invalidate the year-level CSV caches.

    The freshness tick rewrites the year CSVs in place; without clearing
    these caches the same worker process would keep reading the stale file
    (spec 2026-09-08-daily-runs, section 5.1).
    """
    for loader in (load_dispo, load_ofertas, load_demanda, load_precio_bolsa, load_dispo_come):
        loader.cache_clear()
