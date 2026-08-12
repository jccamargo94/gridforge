"""One-off generator for the Fase 2B smoke-test fixture.

Run once (`uv run python tests/fixtures/xm_smoke/generate_fixture.py` from
repo root) and commit the output alongside this script. Not run at test
time — the fixture files it produces are the actual test input.
"""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

FECHA = date(2024, 4, 18)
MMDD = "0418"
BASE = Path(__file__).parent
HOURS = [datetime(2024, 4, 18) + timedelta(hours=h) for h in range(24)]

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

(BASE / "dispo_declarada").mkdir(exist_ok=True)
with open(BASE / "dispo_declarada" / "dispo_declarada_2024.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "resource_name", "dispo", "gen_type"])
    for g in GENERATORS:
        for h in HOURS:
            w.writerow([h.isoformat(sep=" "), g["name"], g["dispo_kw"], "TERMICA"])

(BASE / "ofertas").mkdir(exist_ok=True)
with open(BASE / "ofertas" / "ofertas_2024.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Date", "resource_name", "Value"])
    for g in GENERATORS:
        w.writerow([FECHA.isoformat(), g["name"], g["bid_cop_kwh"]])

(BASE / "demaCome").mkdir(exist_ok=True)
with open(BASE / "demaCome" / "demaCome_2024.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "dema"])
    for h in HOURS:
        w.writerow([h.isoformat(sep=" "), 350_000])

agc_dir = BASE / str(FECHA)
agc_dir.mkdir(exist_ok=True)
with open(agc_dir / "agc_asignado.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "recurso", "agc"])
    for h in HOURS:
        w.writerow([h.isoformat(sep=" "), "TERMO1", 0])

with open(BASE / "parametros_plantas.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["generador", "TMG"])
    for g in GENERATORS:
        w.writerow([g["name"], 1])

(BASE / "precio_bolsa").mkdir(exist_ok=True)
with open(BASE / "precio_bolsa" / "precio_bolsa_2024.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "precio_bolsa"])
    for h in HOURS:
        w.writerow([h.isoformat(sep=" "), 200])

(BASE / "dispo_come").mkdir(exist_ok=True)
with open(BASE / "dispo_come" / "dispo_come_2024.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["datetime", "resource_name", "dispo"])
    for g in GENERATORS:
        for h in HOURS:
            w.writerow([h.isoformat(sep=" "), g["name"], g["dispo_kw"]])

(BASE / "ramps.json").write_text("{}")
(BASE / "preideal_dispatch_map.json").write_text("{}")

flat_dir = BASE / str(FECHA)
flat_dir.mkdir(exist_ok=True)
ci_dir = BASE / "condicion_inicial" / str(FECHA)
ci_dir.mkdir(parents=True, exist_ok=True)

ofei_lines = []
for g in GENERATORS:
    # Real XM PAP schema (issue #38): tres tipos por recurso, fria/tibia/caliente
    # (PAPF02/PAPT02/PAPC02), precios en COP. cold_start selecciona el tipo frio.
    ofei_lines.append(f"{g['name']}, PAPF02,{g['pap_cop']}")
    ofei_lines.append(f"{g['name']}, PAPT02,{int(g['pap_cop'] * 0.8)}")
    ofei_lines.append(f"{g['name']}, PAPC02,{int(g['pap_cop'] * 0.6)}")
for g in GENERATORS:
    mo_vals = ",".join(str(g["mo"]) for _ in range(24))
    ofei_lines.append(f"{g['name']}, MO,{mo_vals}")
(flat_dir / f"OFEI{MMDD}.txt").write_text("\n".join(ofei_lines) + "\n")

prid_row = ["TOTAL"] + ["350"] * 24
(flat_dir / f"PrId{MMDD}_NAL.txt").write_text(",".join(prid_row) + "\n", encoding="latin1")

# Real XM schema (issue #34) -- Planta/ESTADOPINI1/GPPINI_1/CONFPINI1/TL/TFL, not the
# Recurso/Tipo/Gpini-1/Conf_Pini-1/T_CONF_Pini-1 layout this fixture used to assume.
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


with open(flat_dir / f"dCondIniP{MMDD}.txt", "w") as f:
    f.write(DCONDINIP_HEADER)
    for g in GENERATORS:
        f.write(dcondinip_row(g))

(flat_dir / f"dCondIniU{MMDD}.txt").write_text("Recurso,Tipo,Gini-1,Cini-1\n")

mpo_row = ",".join(["150000.00"] * 24)
delta_row = ",".join(["0.00"] * 24)
imar_lines = [f'"Costo Marginal",{mpo_row}', f'"Delta",{delta_row}', f'"MPO",{mpo_row}']
(flat_dir / f"iMAR{MMDD}.txt").write_text("\n".join(imar_lines) + "\n")

agcu_lines = []
for g in GENERATORS:
    agcu_lines.append(f'"{g["name"]}",0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0')
(flat_dir / f"dAGCUNIDAD{MMDD}.txt").write_text("\n".join(agcu_lines) + "\n")

with open(ci_dir / f"dCondIniP{MMDD}.txt", "w") as f:
    f.write(DCONDINIP_HEADER)
    for g in GENERATORS:
        f.write(dcondinip_row(g))

(ci_dir / f"dCondIniU{MMDD}.txt").write_text("Recurso,Tipo,Gini-1,Cini-1\n")

print("fixture written to", BASE)
