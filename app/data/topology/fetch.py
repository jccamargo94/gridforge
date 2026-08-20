# app/data/topology/fetch.py
from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx

from app.storage import Storage

PARATEC_HEADERS: dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://paratec.xm.com.co",
    "referer": "https://paratec.xm.com.co/",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
}

XM_DEMAND_HEADERS: dict[str, str] = {
    "accept": "text/plain, */*",
    "origin": "https://www.xm.com.co",
    "referer": "https://www.xm.com.co/",
    "user-agent": PARATEC_HEADERS["user-agent"],
}

PARATEC_BASE = "https://paratecbackend.xm.com.co"
XM_DEMAND_BASE = "https://api-portalxm.xm.com.co/administracion-archivos/ficheros/descarga-archivo"

ENDPOINTS: dict[str, str] = {
    "substations": f"{PARATEC_BASE}/reportetransmision/api/Substation/SubstationInfo",
    "lines": f"{PARATEC_BASE}/reportetransmision/api/Line/getAll",
    "lines_map": f"{PARATEC_BASE}/mapas/api/TransmissionMap/getLines",
    "capacity": (
        f"{PARATEC_BASE}/reportegeneracion/api/NetEffectiveCapacities/getNetEffectiveCapacity"
    ),
    "thermal_fuel": f"{PARATEC_BASE}/reportegeneracion/api/ThermalPlant/getAllFuel",
    "hydro": (f"{PARATEC_BASE}/reportegeneracion/api/HydraulicPlant/HydraulicPlantInfo"),
    "solar": f"{PARATEC_BASE}/reportegeneracion/api/SolarPlant/getAll",
    "wind": f"{PARATEC_BASE}/reportegeneracion/api/WindPlant/WindPlantInfo",
}

TIMEOUT = 30


def fetch_json(url: str, *, headers: dict[str, str]) -> Any:
    """GET url and return parsed JSON; raises on non-2xx."""
    resp = httpx.get(url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_all(storage: Storage, *, refresh: bool = False) -> dict[str, Any]:
    """Fetch every endpoint in ENDPOINTS, caching raw JSON under data/topology/raw/."""
    result: dict[str, Any] = {}
    for name, url in ENDPOINTS.items():
        raw_path = f"topology/raw/{name}.json"
        if not refresh and storage.exists(raw_path):
            with storage.open(raw_path, "r") as fh:
                result[name] = json.load(fh)
            continue
        payload = fetch_json(url, headers=PARATEC_HEADERS)
        with storage.open(raw_path, "w") as fh:
            json.dump(payload, fh)
        result[name] = payload
    return result


def fetch_demand(storage: Storage, d: date, source: str) -> str:
    """Download the dDEM or PRON demand .txt for a date; return its raw text."""
    if source not in ("ddem", "pron"):
        raise ValueError(f"demand source must be 'ddem' or 'pron', got {source!r}")
    month = f"{d.year:04d}-{d.month:02d}"
    mmdd = f"{d.month:02d}{d.day:02d}"
    if source == "ddem":
        ruta = f"M:/InformacionAgentes/Usuarios/Publico/DESPACHO/{month}/dDEM{mmdd}.txt"
    else:
        ruta = (
            "M:/InformacionAgentes/Usuarios/Publico/DEMANDAS/"
            f"Pronostico%20Oficial/{month}/PRON_AREAS{mmdd}.txt"
        )
    raw_path = f"topology/raw/{source}_{d:%Y%m%d}.txt"
    if storage.exists(raw_path):
        with storage.open(raw_path, "r") as fh:
            return fh.read()
    resp = httpx.get(
        XM_DEMAND_BASE,
        params={"ruta": ruta, "nombreBlobContainer": "storageportalxm"},
        headers=XM_DEMAND_HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    text = resp.content.decode("utf-8")
    with storage.open(raw_path, "w") as fh:
        fh.write(text)
    return text
