from datetime import date

import requests

from app.data.paratec import (
    ensure_paratec_all,
    fetch_thermal_fuel_unit_info,
    fetch_thermal_plant_detail,
    fetch_thermal_plants,
)
from app.storage import LocalStorage

# ---------------------------------------------------------------------------
# Sample responses that match the shape the real API returns
# ---------------------------------------------------------------------------

_PLANTS_JSON = [
    {"elementMRID": "PLANT01", "name": "TermoCentro", "type": "TERMICA"},
    {"elementMRID": "PLANT02", "name": "TermoNorte", "type": "TERMICA"},
]

_DETAIL_JSON = {
    "elementMRID": "PLANT01",
    "plantName": "TermoCentro",
    "fuelType": "GAS",
    "configurationNumber": 1,
    "minGenerationTime": 4.0,
    "uploadSpeed": 10.0,
    "downloadSpeed": 10.0,
    "ramps": [{"configurationNumber": 1, "uploadSpeed": 10.0, "downloadSpeed": 10.0}],
}

_FUEL_JSON = [
    {"thermalPlantUnitMRID": "UNIT01", "fuelType": "GAS", "plantMRID": "PLANT01"},
    {"thermalPlantUnitMRID": "UNIT02", "fuelType": "CARBON", "plantMRID": "PLANT02"},
]


# ---------------------------------------------------------------------------
# Monkeypatched requests.get
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _fake_get(url, timeout=30):
    if url.endswith("/ThermalPlant/getAll"):
        return _FakeResponse(_PLANTS_JSON)
    if "/ThermalPlant/getThermalPlantDetail/" in url:
        return _FakeResponse(_DETAIL_JSON)
    if url.endswith("/ThermalUnit/ThermalFuelUnitInfo"):
        return _FakeResponse(_FUEL_JSON)
    raise requests.ConnectionError(f"Unrecognized URL in test: {url}")


# ---------------------------------------------------------------------------
# Tests: individual fetch functions
# ---------------------------------------------------------------------------


def test_fetch_thermal_plants_returns_list(monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_get)
    data = fetch_thermal_plants()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["elementMRID"] == "PLANT01"


def test_fetch_thermal_plant_detail_returns_dict(monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_get)
    data = fetch_thermal_plant_detail("PLANT01")
    assert isinstance(data, dict)
    assert data["fuelType"] == "GAS"


def test_fetch_thermal_fuel_unit_info_returns_list(monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_get)
    data = fetch_thermal_fuel_unit_info()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["fuelType"] == "GAS"


# ---------------------------------------------------------------------------
# Tests: ensure_paratec_all orchestration
# ---------------------------------------------------------------------------


def test_ensure_paratec_all_writes_three_files(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_get)
    snapshot = date(2026, 8, 6)

    ensure_paratec_all(str(tmp_path), snapshot_date=snapshot)

    plants = tmp_path / "paratec" / "thermal_plants_2026-08-06.json"
    details = tmp_path / "paratec" / "thermal_plant_details_2026-08-06.json"
    fuel = tmp_path / "paratec" / "thermal_fuel_unit_info_2026-08-06.json"

    assert plants.exists()
    assert details.exists()
    assert fuel.exists()

    import json

    with open(plants) as f:
        data = json.load(f)
    assert len(data) == 2

    with open(details) as f:
        data = json.load(f)
    assert "PLANT01" in data
    assert "PLANT02" in data

    with open(fuel) as f:
        data = json.load(f)
    assert len(data) == 2


def test_ensure_paratec_all_is_noop_when_files_exist(tmp_path, monkeypatch):
    """When all three cached files already exist, no HTTP request is made."""
    storage = LocalStorage(str(tmp_path))
    snapshot = date(2026, 8, 6)

    for fname in [
        "paratec/thermal_plants_2026-08-06.json",
        "paratec/thermal_plant_details_2026-08-06.json",
        "paratec/thermal_fuel_unit_info_2026-08-06.json",
    ]:
        with storage.open(fname, "w") as f:
            f.write("[]")

    calls = []

    def _tracking_get(url, timeout=30):
        calls.append(url)
        raise AssertionError("should not fetch when all files exist")

    monkeypatch.setattr(requests, "get", _tracking_get)
    ensure_paratec_all(str(tmp_path), snapshot_date=snapshot)

    assert len(calls) == 0


def test_ensure_paratec_all_handles_connection_error_gracefully(tmp_path, monkeypatch):
    """When the detail endpoint fails for one plant, others should still be fetched."""
    storage = LocalStorage(str(tmp_path))
    snapshot = date(2026, 8, 6)

    # Pre-populate plants list so we only test detail fetching
    import json

    with storage.open("paratec/thermal_plants_2026-08-06.json", "w") as f:
        json.dump(_PLANTS_JSON, f)

    call_count = {"detail": 0, "fuel": 0}

    def _partial_fake_get(url, timeout=30):
        if url.endswith("/ThermalUnit/ThermalFuelUnitInfo"):
            call_count["fuel"] += 1
            return _FakeResponse(_FUEL_JSON)
        if "/ThermalPlant/getThermalPlantDetail/" in url:
            call_count["detail"] += 1
            if "PLANT01" in url:
                raise requests.ConnectionError("Simulated network failure for PLANT01")
            return _FakeResponse(_DETAIL_JSON)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(requests, "get", _partial_fake_get)
    ensure_paratec_all(str(tmp_path), snapshot_date=snapshot)

    # Details should still exist with PLANT02 only
    details_path = tmp_path / "paratec" / "thermal_plant_details_2026-08-06.json"
    assert details_path.exists()
    with open(details_path) as f:
        details = json.load(f)
    assert "PLANT02" in details
    assert "PLANT01" not in details  # failed

    # Fuel info should still be fetched
    assert call_count["fuel"] == 1

    # Fuel file exists
    assert (tmp_path / "paratec" / "thermal_fuel_unit_info_2026-08-06.json").exists()


def test_ensure_paratec_all_reads_plants_from_cache_when_available(tmp_path, monkeypatch):
    """When plants file already exists but details don't, the plants list should be
    read from cache rather than fetched again."""
    storage = LocalStorage(str(tmp_path))
    snapshot = date(2026, 8, 6)

    import json

    with storage.open("paratec/thermal_plants_2026-08-06.json", "w") as f:
        json.dump(_PLANTS_JSON, f)

    calls = []

    def _tracking_get(url, timeout=30):
        calls.append(url)
        if "/ThermalPlant/getThermalPlantDetail/" in url:
            return _FakeResponse(_DETAIL_JSON)
        if url.endswith("/ThermalUnit/ThermalFuelUnitInfo"):
            return _FakeResponse(_FUEL_JSON)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(requests, "get", _tracking_get)
    ensure_paratec_all(str(tmp_path), snapshot_date=snapshot)

    # getAll should NOT have been called (plants were read from cache)
    urls = [c for c in calls if "getAll" in c]
    assert len(urls) == 0

    # But detail + fuel endpoints were called
    assert any("getThermalPlantDetail" in c for c in calls)
    assert any("ThermalFuelUnitInfo" in c for c in calls)

    details_path = tmp_path / "paratec" / "thermal_plant_details_2026-08-06.json"
    assert details_path.exists()


def test_ensure_paratec_all_uses_today_as_default(tmp_path, monkeypatch):
    """When snapshot_date is not provided, date.today() is used as fallback."""
    monkeypatch.setattr(requests, "get", _fake_get)

    ensure_paratec_all(str(tmp_path))  # no snapshot_date -> date.today()

    today_str = date.today().isoformat()
    plants_path = tmp_path / "paratec" / f"thermal_plants_{today_str}.json"
    assert plants_path.exists()
