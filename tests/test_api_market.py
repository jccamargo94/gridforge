from pathlib import Path

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def test_merit_position_endpoint_uses_observed_data(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    resp = api_client.get("/market/merit-position", params={"date": "2024-03-01", "own": "TERMO1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["date"] == "2024-03-01"
    assert len(body["hours"]) == 24
    mine = body["hours"][0]["own"][0]
    assert mine["resource"] == "TERMO1" and mine["rank"] == 1
    assert mine["price_cop_mwh"] == 150_000.0


def test_merit_position_requires_own(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    resp = api_client.get("/market/merit-position", params={"date": "2024-03-01", "own": " , "})
    assert resp.status_code == 422


def test_merit_position_404_without_year_data(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    resp = api_client.get("/market/merit-position", params={"date": "2019-01-01", "own": "X"})
    assert resp.status_code == 404


def test_position_series_endpoint_and_range_cap(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    ok = api_client.get(
        "/market/position-series",
        params={"start": "2024-03-01", "end": "2024-03-02", "own": "TERMO1"},
    )
    assert ok.status_code == 200, ok.text
    assert {r["date"] for r in ok.json()} == {"2024-03-01", "2024-03-02"}
    too_long = api_client.get(
        "/market/position-series",
        params={"start": "2024-01-01", "end": "2024-12-31", "own": "TERMO1"},
    )
    assert too_long.status_code == 422


def test_offer_audit_endpoint_published_and_candidate(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    resp = api_client.post(
        "/market/offer-audit",
        json={
            "date": "2024-03-20",
            "window_days": 30,
            "offers": [
                {"resource": "TERMO1"},
                {"resource": "TERMO1", "price_cop_mwh": 900000},
                {"resource": "NOEXISTE"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    published, candidate, missing = resp.json()
    assert published["price_source"] == "published"
    assert candidate["price_source"] == "candidate"
    assert candidate["flag"] in {"changed", "alert"}
    assert missing["status"] == "no_offer"


def test_offer_audit_validates_input(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    assert (
        api_client.post(
            "/market/offer-audit", json={"date": "2024-03-20", "offers": []}
        ).status_code
        == 422
    )
    bad = api_client.post(
        "/market/offer-audit",
        json={"date": "2024-03-20", "window_days": 1, "offers": [{"resource": "X"}]},
    )
    assert bad.status_code == 422
    nodata = api_client.post(
        "/market/offer-audit", json={"date": "2019-01-01", "offers": [{"resource": "X"}]}
    )
    assert nodata.status_code == 404


def test_marginal_map_endpoint(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    resp = api_client.get(
        "/market/marginal-map", params={"start": "2024-03-01", "end": "2024-03-10"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_hours"] > 0 and "cells" in body
    assert all("resource" not in c and "resource_name" not in c for c in body["cells"])


def test_marginal_map_validates_range_and_tol(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    long = api_client.get(
        "/market/marginal-map", params={"start": "2023-01-01", "end": "2024-12-31"}
    )
    assert long.status_code == 422
    bad_tol = api_client.get(
        "/market/marginal-map", params={"start": "2024-03-01", "end": "2024-03-02", "tol": 0.9}
    )
    assert bad_tol.status_code == 422
    nodata = api_client.get(
        "/market/marginal-map", params={"start": "2019-01-01", "end": "2019-01-02"}
    )
    assert nodata.status_code == 404


def test_availability_check_requires_cached_capacity_then_works(api_client, monkeypatch, tmp_path):
    import json
    import shutil

    data = tmp_path / "data"
    shutil.copytree(DD, data)
    monkeypatch.setenv("DATA_DIR", str(data))
    params = {"start": "2024-03-01", "end": "2024-03-10"}
    assert api_client.get("/market/availability-check", params=params).status_code == 404

    capacity = {
        "dataReport": [
            {
                "name": "Planta térmica",
                "dispatchedType": [
                    {
                        "generatorTypes": [
                            {"elements": [{"elementName": "Termo1", "netEffectiveCapacity": 100.0}]}
                        ]
                    }
                ],
            }
        ]
    }
    raw = data / "topology" / "raw"
    raw.mkdir(parents=True)
    (raw / "capacity.json").write_text(json.dumps(capacity))
    resp = api_client.get("/market/availability-check", params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["matched"] == 1
    assert [f["resource"] for f in body["findings"]] == ["TERMO1"]  # fixture declares 300 MW > 100


def test_availability_check_validates_params(api_client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", DD)
    resp = api_client.get(
        "/market/availability-check",
        params={"start": "2024-03-01", "end": "2024-03-10", "low_pct": 2},
    )
    assert resp.status_code == 422
