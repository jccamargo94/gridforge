import json

from typer.testing import CliRunner

from app import cli

runner = CliRunner()


def test_scrape_topology_writes_network_json(tmp_path, monkeypatch):
    out = tmp_path / "network.json"

    def fake_fetch_all(storage, *, refresh=False):
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
            "capacity": {"dataReport": []},
            "thermal_fuel": {"data": []},
            "hydro": {"data": []},
            "solar": {"data": []},
            "wind": {"data": []},
        }

    def fake_fetch_demand(storage, d, source):
        return "SubArea Valle,1.0\n"

    monkeypatch.setattr("app.data.topology.fetch.fetch_all", fake_fetch_all)
    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    result = runner.invoke(
        cli.app,
        ["scrape-topology", "--date", "2024-04-18", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert "zones" in data


def test_scrape_topology_rejects_bad_demand_source(tmp_path):
    result = runner.invoke(
        cli.app,
        ["scrape-topology", "--date", "2024-04-18", "--demand-source", "bogus"],
    )
    assert result.exit_code != 0
