"""Parse + aggregate the per-unit AGC blob (dAGCUNIDAD, mecanismo 1) down to
the per-resource shape case_builder.py expects (agc_asignado.csv).

Raw format, one line per unit, no header:
    "UNIT NAME",v1,v2,...,v24

Unit -> resource aggregation strips the trailing " <digits>" (e.g.
"CHIVOR 2" -> "CHIVOR") and fuzzy-matches against the run's known resource
names, same pattern case_builder.py already uses for OFEI name resolution.
Values are MW in the raw blob; case_builder.py's existing *1e-3 assumes kW
(same convention as dispo/demand), so this module converts *1000 on write --
see plan Global Constraints.
"""

import csv
import io
import re
from datetime import date

import pandas as pd
from thefuzz import fuzz, process

from app.db.queries import upsert_input_dataset
from app.storage import get_storage

_UNIT_SUFFIX = re.compile(r"\s+\d+$")


def parse_dagcunidad(raw_text: str) -> pd.DataFrame:
    rows = []
    for line in csv.reader(io.StringIO(raw_text)):
        if not line:
            continue
        unit_name = line[0]
        for hour, value in enumerate(line[1:25]):
            rows.append({"unit_name": unit_name, "hour": hour, "agc_mw": float(value)})
    return pd.DataFrame(rows, columns=["unit_name", "hour", "agc_mw"])


def _resource_name_for_unit(unit_name: str, resource_names: list[str]) -> str | None:
    candidate = _UNIT_SUFFIX.sub("", unit_name).strip()
    match = process.extractOne(
        query=candidate.lower(),
        choices=resource_names,
        scorer=fuzz.token_sort_ratio,
        processor=lambda x: x.lower().replace(" ", ""),
        score_cutoff=70,
    )
    return match[0] if match else None


def ensure_agc_asignado(
    dispatch_date: date, data_dir: str, resource_names: list[str], session=None
) -> None:
    storage = get_storage(data_dir)
    out_path = f"{dispatch_date}/agc_asignado.csv"
    if storage.exists(out_path):
        return

    filename = f"dAGCUNIDAD{dispatch_date.month:0>2}{dispatch_date.day:0>2}.txt"
    with storage.open(f"{dispatch_date}/{filename}", "r", encoding="latin1") as f:
        raw_text = f.read()

    long = parse_dagcunidad(raw_text)
    long["recurso"] = long["unit_name"].apply(lambda u: _resource_name_for_unit(u, resource_names))
    unmatched = long[long["recurso"].isnull()]["unit_name"].unique()
    for name in unmatched:
        print(f"...AGC: no se pudo mapear la unidad '{name}' a ningun recurso. Se ignora.")
    long = long.dropna(subset=["recurso"])

    agg = long.groupby(["recurso", "hour"], as_index=False)["agc_mw"].sum()
    agg["datetime"] = pd.to_datetime(dispatch_date) + pd.to_timedelta(agg["hour"], unit="h")
    agg["agc"] = agg["agc_mw"] * 1000  # MW -> kW, matches case_builder.py's *1e-3
    out = agg[["datetime", "recurso", "agc"]]

    with storage.open(out_path, "w") as f:
        out.to_csv(f, index=False)
    if session is not None:
        upsert_input_dataset(
            session,
            dataset="agc_asignado",
            partition_key=str(dispatch_date),
            source="xm_blob:dAGCUNIDAD",
            row_count=len(out),
        )
