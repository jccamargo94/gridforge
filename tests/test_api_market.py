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
