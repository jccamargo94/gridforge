"""Mecanismo 3 (Paratec raw JSON cache) of the XM ingesta design:
docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md sections 1, 3, 7.

Fetches raw JSON from three Paratec API endpoints and caches them as timestamped
snapshots under data/paratec/. No interpretation of the content -- that is
deliberately deferred to a separate modelling spec
(issue #26, project_thermal-configuration-dispatch).

Does NOT replace parametros_plantas.csv or ramps.json.
"""

import json
from datetime import date
from typing import Any

import requests

from app.storage import get_storage

BASE_URL = "https://paratecbackend.xm.com.co/reportegeneracion/api"
TIMEOUT = 30  # seconds, enough for the detail endpoint that may be slower


def _fetch_json(url: str) -> Any:
    """Fetch and parse JSON from *url*.  Raises on connectivity issues or HTTP errors."""
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Three individual fetch functions (one per endpoint)
# ---------------------------------------------------------------------------


def fetch_thermal_plants() -> Any:
    """GET ThermalPlant/getAll -- list of all thermal plants (includes elementMRID)."""
    return _fetch_json(f"{BASE_URL}/ThermalPlant/getAll")


def fetch_thermal_plant_detail(element_mrid: str) -> Any:
    """GET ThermalPlant/getThermalPlantDetail/{elementMRID} -- ramp rates,
    min-generation times and other technical parameters for a single plant."""
    return _fetch_json(f"{BASE_URL}/ThermalPlant/getThermalPlantDetail/{element_mrid}")


def fetch_thermal_fuel_unit_info() -> Any:
    """GET ThermalUnit/ThermalFuelUnitInfo -- fuel-type / unit info for all thermal units."""
    return _fetch_json(f"{BASE_URL}/ThermalUnit/ThermalFuelUnitInfo")


# ---------------------------------------------------------------------------
# Combined orchestration (check-then-fetch -> Storage -> manifest upsert)
# ---------------------------------------------------------------------------


def ensure_paratec_all(
    data_dir: str,
    snapshot_date: date | None = None,
    session=None,
) -> None:
    """Cache all three Paratec JSON snapshots if not already cached for *snapshot_date*.

    Writes under ``data/paratec/<kind>_<iso_date>.json`` via :class:`Storage`.
    Upserts into ``input_datasets`` manifest when *session* is provided
    (``source='paratec:...'``, ``partition_key='latest'``).
    """
    today = snapshot_date or date.today()
    date_str = today.isoformat()

    storage = get_storage(data_dir)

    plants_path = f"paratec/thermal_plants_{date_str}.json"
    details_path = f"paratec/thermal_plant_details_{date_str}.json"
    fuel_path = f"paratec/thermal_fuel_unit_info_{date_str}.json"

    # ---- 1. Thermal plants list -------------------------------------------
    plants: list | None = None
    if not storage.exists(plants_path):
        plants = fetch_thermal_plants()
        with storage.open(plants_path, "w") as f:
            json.dump(plants, f)
        if session is not None:
            # lazy import to avoid hard coupling when session is not available
            from app.db.queries import upsert_input_dataset

            count = len(plants) if isinstance(plants, list) else None
            upsert_input_dataset(
                session,
                dataset="paratec_plants",
                partition_key="latest",
                source="paratec:ThermalPlant.getAll",
                row_count=count,
            )

    # ---- 2. Per-plant details ---------------------------------------------
    if not storage.exists(details_path):
        # Ensure we have the plant list (may have been fetched above or read from cache)
        if plants is None:
            if storage.exists(plants_path):
                with storage.open(plants_path, "r") as f:
                    plants = json.load(f)
            else:
                plants = fetch_thermal_plants()
                with storage.open(plants_path, "w") as f:
                    json.dump(plants, f)

        details: dict[str, Any] = {}
        if isinstance(plants, list):
            for plant in plants:
                mrid = plant.get("elementMRID") if isinstance(plant, dict) else None
                if not mrid:
                    continue
                try:
                    details[mrid] = fetch_thermal_plant_detail(mrid)
                except (requests.RequestException, ValueError) as exc:
                    print(f"...Paratec: fallo detalle para {mrid}: {exc}")

        with storage.open(details_path, "w") as f:
            json.dump(details, f)
        if session is not None:
            from app.db.queries import upsert_input_dataset

            upsert_input_dataset(
                session,
                dataset="paratec_plant_details",
                partition_key="latest",
                source="paratec:ThermalPlant.getThermalPlantDetail",
                row_count=len(details),
            )

    # ---- 3. Thermal fuel/unit info ----------------------------------------
    if not storage.exists(fuel_path):
        data = fetch_thermal_fuel_unit_info()
        with storage.open(fuel_path, "w") as f:
            json.dump(data, f)
        if session is not None:
            from app.db.queries import upsert_input_dataset

            count = len(data) if isinstance(data, list) else None
            upsert_input_dataset(
                session,
                dataset="paratec_fuel_units",
                partition_key="latest",
                source="paratec:ThermalUnit.ThermalFuelUnitInfo",
                row_count=count,
            )
