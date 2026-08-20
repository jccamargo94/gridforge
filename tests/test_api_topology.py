from app.db import queries
from app.storage import LocalStorage
from tests.fixtures.nodal import make_three_zone_network


def _fake_fetch_all(_storage, *, refresh=False):
    return {
        "substations": {
            "data": [
                {
                    "elementName": "CALI",
                    "subAreaName": "SubArea Valle",
                    "voltageLevel": [115],
                    "latitude": 3.4,
                    "longitude": -76.5,
                }
            ]
        },
        "lines": {"data": []},
        "lines_map": {"data": []},
        "capacity": {"dataReport": []},
        "thermal_fuel": {"data": []},
        "hydro": {"data": []},
        "solar": {"data": []},
        "wind": {"data": []},
    }


def _fake_fetch_demand(_storage, _d, _source):
    return "SubArea Valle,1.0\n"


def _patch_storage_root(monkeypatch, tmp_path):
    monkeypatch.setattr("services.api.main.get_storage", lambda root: LocalStorage(str(tmp_path)))


def test_scrape_topology_writes_network_and_registers_dataset(api_client, tmp_path, monkeypatch):
    _patch_storage_root(monkeypatch, tmp_path)
    monkeypatch.setattr("app.data.topology.fetch.fetch_all", _fake_fetch_all)
    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", _fake_fetch_demand)

    resp = api_client.post(
        "/topology/scrape", json={"dispatch_date": "2024-04-18", "demand_source": "ddem"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["zones"] == 1

    assert (tmp_path / "topology" / "network.json").exists()


def test_scrape_topology_rejects_bad_demand_source(api_client):
    resp = api_client.post(
        "/topology/scrape", json={"dispatch_date": "2024-04-18", "demand_source": "bogus"}
    )
    assert resp.status_code == 400


def test_get_topology_network_404_before_any_scrape(api_client, tmp_path, monkeypatch):
    _patch_storage_root(monkeypatch, tmp_path)
    resp = api_client.get("/topology/network")
    assert resp.status_code == 404


def test_get_topology_network_returns_cached_network_after_scrape(
    api_client, tmp_path, monkeypatch
):
    _patch_storage_root(monkeypatch, tmp_path)
    monkeypatch.setattr("app.data.topology.fetch.fetch_all", _fake_fetch_all)
    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", _fake_fetch_demand)

    api_client.post(
        "/topology/scrape", json={"dispatch_date": "2024-04-18", "demand_source": "ddem"}
    )

    resp = api_client.get("/topology/network")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scraped_at"] is not None
    assert len(body["network"]["zones"]) == 1


def test_create_run_recompute_demand_shares_requires_nodal_network(api_client):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "preideal",
            "recompute_demand_shares": True,
        },
    )
    assert resp.status_code == 400


def test_create_run_recompute_demand_shares_overrides_cached_shares(
    api_client, tmp_path, monkeypatch
):
    _patch_storage_root(monkeypatch, tmp_path)

    def fake_fetch_demand(_storage, _d, _source):
        return "norte,3.0\ncentro,1.0\nsur,0.0\n"

    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "lmp",
            "nodal_network": make_three_zone_network().model_dump(),
            "recompute_demand_shares": True,
        },
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    case = queries.get_case(session, run.case_id)
    session.close()

    assert case.nodal_network["demand_shares"] == {"norte": 0.75, "centro": 0.25, "sur": 0.0}
