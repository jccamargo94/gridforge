"""code <-> resource_name crosswalk from XM's ListadoRecursos API.

This module provides the canonical mapping between XM short resource codes
(``Values_code``, e.g. ``2QEK``, ``3DDT``) returned by pydataxm's bulk metrics
(``DispoDeclarada``, ``PrecOferDesp``, ``DispoCome``) and the plant/resource
names (``resource_name``, e.g. ``SALTO II``, ``TERMO1``) used throughout the
rest of the pipeline.
"""

from datetime import date

import pandas as pd


def fetch_resource_crosswalk(consult) -> pd.DataFrame:
    """Return code <-> resource_name <-> gen_type crosswalk from XM's
    ``ListadoRecursos`` metric (Sistema scope).

    ``consult`` is a ``pydataxm.pydataxm.ReadDB`` instance or any object with a
    compatible ``request_data(collection, metric, start_date, end_date)``
    signature.

    The returned DataFrame has columns: ``code``, ``resource_name``, ``gen_type``.

    ``start_date`` / ``end_date`` are required by pydataxm's ``request_data``
    even for list-type metrics (it computes a date range unconditionally before
    branching on entity type) but are otherwise unused -- any single date works.
    """
    today = date.today()
    raw = consult.request_data("ListadoRecursos", "Sistema", today, today)
    return raw.rename(
        columns={
            "Values_Code": "code",
            "Values_Name": "resource_name",
            "Values_Type": "gen_type",
        }
    )[["code", "resource_name", "gen_type"]]
