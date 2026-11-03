"""Generacion real horaria por recurso (metrica XM ``Gene``), cache por dia.

Se usa en el nivel ideal (ex post) para fijar las termicas a lo que realmente
generaron (inflexibilidades que el precio ideal no remunera). A diferencia de los
CSV anuales, se cachea un archivo por dia (``gene/gene_YYYY-MM-DD.csv``): bajar un
ano completo con pydataxm es lento y aqui solo se necesita la fecha del caso.
Unidades: ``gen`` en kWh por hora (igual que el resto de metricas XM crudas).
"""

from datetime import date

import pandas as pd

from app.data.crosswalk import fetch_resource_crosswalk
from app.storage import get_storage


def _rel_path(day: date) -> str:
    return f"gene/gene_{day.isoformat()}.csv"


def ensure_gene_for_date(day: date, data_dir: str, consult=None) -> None:
    """Descarga ``Gene`` por recurso para ``day`` si no esta en cache."""
    from app.data.xm_bulk import _melt_hourly  # evita import circular en carga del modulo

    storage = get_storage(data_dir)
    if storage.exists(_rel_path(day)):
        return
    if consult is None:
        from pydataxm.pydataxm import ReadDB

        consult = ReadDB()
    raw = consult.request_data("Gene", "Recurso", day, day)
    if raw is None or raw.empty:
        raise FileNotFoundError(
            f"XM no publica la generacion real (Gene) para {day} todavia -- la opcion "
            "thermal_real_generation requiere una fecha ya consolidada."
        )
    crosswalk = fetch_resource_crosswalk(consult)
    fresh = _melt_hourly(raw, "gen").merge(crosswalk, on="code", how="inner")[
        ["datetime", "resource_name", "gen"]
    ]
    with storage.open(_rel_path(day), "w") as f:
        fresh.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")


def load_gene_day(data_dir: str, day: date) -> pd.DataFrame:
    """DataFrame ``datetime, resource_name, gen`` (kWh) del dia."""
    storage = get_storage(data_dir)
    with storage.open(_rel_path(day), "rb") as f:
        return pd.read_csv(f, parse_dates=["datetime"])
