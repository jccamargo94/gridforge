"""Generator for the Fase 2B smoke fixture + Fase 7A closed-month extension.

Run once (`uv run python tests/fixtures/xm_smoke/generate_fixture.py` from
repo root) and commit the output alongside this script. Not run at test
time — the fixture files it produces are the actual test input.

Content: year CSVs with rows for 2024-03-01..2024-03-31 (a closed synthetic
month for the settled lane) AND 2024-04-18 (the original smoke day), plus
full per-date blob sets for both 2024-03-15 and 2024-04-18.
"""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent

GENERATORS = [
    {
        "name": "TERMO1",
        "dispo_kw": 300_000,
        "bid_cop_kwh": 150,
        "pap_cop": 1_500_000,
        "mo": 10,
        "gpini": 150,
        "conf": 1,
        "tl": 5,
        "tfl": 0,
    },
    {
        "name": "TERMO2",
        "dispo_kw": 200_000,
        "bid_cop_kwh": 180,
        "pap_cop": 1_500_000,
        "mo": 5,
        "gpini": 0,
        "conf": 0,
        "tl": 0,
        "tfl": 10,
    },
]

MARCH_DAYS = [date(2024, 3, 1) + timedelta(days=i) for i in range(31)]
FECHA = date(2024, 4, 18)
SETTLED = date(2024, 3, 15)
DAY_ROWS = {**{d: 350_000 for d in MARCH_DAYS}, FECHA: 350_000}


def _hours(day: date):
    return [datetime(day.year, day.month, day.day) + timedelta(hours=h) for h in range(24)]


def _write_csv(rel_dir: str, filename: str, header: list[str], rows: list[list]):
    out_dir = BASE / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / filename, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


days = MARCH_DAYS + [FECHA]
dispo_rows = []
for day in days:
    for g in GENERATORS:
        for h in _hours(day):
            dispo_rows.append([h.isoformat(sep=" "), g["name"], g["dispo_kw"], "TERMICA"])
_write_csv(
    "dispo_declarada",
    "dispo_declarada_2024.csv",
    ["datetime", "resource_name", "dispo", "gen_type"],
    dispo_rows,
)

oferta_rows = []
for day in days:
    for g in GENERATORS:
        oferta_rows.append([day.isoformat(), g["name"], g["bid_cop_kwh"]])
_write_csv("ofertas", "ofertas_2024.csv", ["Date", "resource_name", "Value"], oferta_rows)

dema_rows = []
for day in days:
    for h in _hours(day):
        dema_rows.append([h.isoformat(sep=" "), 350_000])
_write_csv("demaCome", "demaCome_2024.csv", ["datetime", "dema"], dema_rows)

dispo_come_rows = []
for day in days:
    for g in GENERATORS:
        for h in _hours(day):
            dispo_come_rows.append([h.isoformat(sep=" "), g["name"], g["dispo_kw"]])
_write_csv(
    "dispo_come", "dispo_come_2024.csv", ["datetime", "resource_name", "dispo"], dispo_come_rows
)

bolsa_rows = []
for day in days:
    for h in _hours(day):
        bolsa_rows.append([h.isoformat(sep=" "), 200])
_write_csv("precio_bolsa", "precio_bolsa_2024.csv", ["datetime", "precio_bolsa"], bolsa_rows)

_write_csv(
    ".", "parametros_plantas.csv", ["generador", "TMG"], [[g["name"], 1] for g in GENERATORS]
)
(BASE / "ramps.json").write_text("{}")
(BASE / "preideal_dispatch_map.json").write_text("{}")

DCONDINIP_HEADER = (
    "Planta ,AGC, BLOQUESPINI1, CONFENTRADA, CONFPINI1, CONFSALIDA, DISPPINI1, "
    "ESTADOPINI1, GPPINI_1, GPPINI_2, NARRANQUESPINI1, PRUEBAS, TAPUBLICAR, "
    "TCEPENDIENTE, TDISPPINI1, TFL, TL, TULT\n"
)


def dcondinip_row(g: dict) -> str:
    return (
        f"{g['name']}, 0, 0, 0, {g['conf']}, 0, {g['gpini']},  - , "
        f"{g['gpini']:.4f}, {g['gpini']:.4f}, 0, 0, 10, 0, {g['tl']}, {g['tfl']}, {g['tl']}, 0\n"
    )


def _write_blob_day(day: date):
    mmdd = f"{day.month:0>2}{day.day:0>2}"
    flat_dir = BASE / str(day)
    flat_dir.mkdir(parents=True, exist_ok=True)
    ci_dir = BASE / "condicion_inicial" / str(day)
    ci_dir.mkdir(parents=True, exist_ok=True)

    ofei_lines = []
    for g in GENERATORS:
        ofei_lines.append(f"{g['name']}, PAPF02,{g['pap_cop']}")
        ofei_lines.append(f"{g['name']}, PAPT02,{int(g['pap_cop'] * 0.8)}")
        ofei_lines.append(f"{g['name']}, PAPC02,{int(g['pap_cop'] * 0.6)}")
    for g in GENERATORS:
        mo_vals = ",".join(str(g["mo"]) for _ in range(24))
        ofei_lines.append(f"{g['name']}, MO,{mo_vals}")
    (flat_dir / f"OFEI{mmdd}.txt").write_text("\n".join(ofei_lines) + "\n")

    (flat_dir / f"PrId{mmdd}_NAL.txt").write_text(
        ",".join(["TOTAL"] + ["350"] * 24) + "\n", encoding="latin1"
    )
    with open(flat_dir / f"dCondIniP{mmdd}.txt", "w") as f:
        f.write(DCONDINIP_HEADER)
        for g in GENERATORS:
            f.write(dcondinip_row(g))
    (flat_dir / f"dCondIniU{mmdd}.txt").write_text("Recurso,Tipo,Gini-1,Cini-1\n")
    mpo_row = ",".join(["150000.00"] * 24)
    delta_row = ",".join(["0.00"] * 24)
    imar_lines = [f'"Costo Marginal",{mpo_row}', f'"Delta",{delta_row}', f'"MPO",{mpo_row}']
    (flat_dir / f"iMAR{mmdd}.txt").write_text("\n".join(imar_lines) + "\n")
    agcu_lines = []
    for g in GENERATORS:
        agcu_lines.append(f'"{g["name"]}",' + ",".join(["0"] * 23))
    (flat_dir / f"dAGCUNIDAD{mmdd}.txt").write_text("\n".join(agcu_lines) + "\n")

    # AGC file per date (load_agc reads {date}/agc_asignado.csv)
    with open(flat_dir / "agc_asignado.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datetime", "recurso", "agc"])
        for h in _hours(day):
            w.writerow([h.isoformat(sep=" "), "TERMO1", 0])

    with open(ci_dir / f"dCondIniP{mmdd}.txt", "w") as f:
        f.write(DCONDINIP_HEADER)
        for g in GENERATORS:
            f.write(dcondinip_row(g))
    (ci_dir / f"dCondIniU{mmdd}.txt").write_text("Recurso,Tipo,Gini-1,Cini-1\n")


_write_blob_day(SETTLED)
_write_blob_day(FECHA)

print("fixture written to", BASE)
