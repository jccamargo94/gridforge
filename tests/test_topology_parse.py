# tests/test_topology_parse.py
from app.data.topology import parse


def test_parse_substations_extracts_zone_fields():
    payload = {
        "header": {"code": 200},
        "data": [
            {
                "elementName": "AGUABLANCA",
                "subAreaName": "SubArea Valle",
                "voltageLevel": [115, 110],
                "latitude": 3.45,
                "longitude": -76.5,
            }
        ],
    }
    subs = parse.parse_substations(payload)
    assert subs == [
        {
            "name": "AGUABLANCA",
            "base_kv": 115.0,
            "subarea": "SubArea Valle",
            "latitude": 3.45,
            "longitude": -76.5,
        }
    ]


def test_parse_lines_computes_reactance_ohm_and_rating_mw():
    payload = {
        "data": [
            {
                "name": "AGUABLANCA - JUANCHITO 1 115 kV",
                "subStation": "AGUABLANCA - JUANCHITO 1",
                "ratedVoltage": "115",
                "thermalLimit": 600,
                "length": 5.63,
                "typeLines": [{"reactance": 1.23, "length": 5.63}],
            }
        ]
    }
    lines = parse.parse_lines(payload)
    line = lines[0]
    assert line["from_zone"] == "AGUABLANCA"
    assert line["to_zone"] == "JUANCHITO 1"
    # 1.23 Ω/km × 5.63 km = 6.9249 Ω total (per-unit conversion happens in build)
    assert abs(line["reactance_ohm"] - 6.9249) < 1e-3
    assert line["kv"] == 115.0
    # 600 A × 115 kV × sqrt(3) / 1000 ≈ 119.5 MW
    assert abs(line["rating"] - 119.5) < 0.1


def test_parse_demand_ddem_skips_excluded_rows():
    text = "SubArea Valle,1.0,2.0,3.0\nEcuador138,9.9,9.9\nTotal,4.0,4.0\n"
    demand = parse.parse_demand(text, "ddem")
    assert "SubArea Valle" in demand
    assert "Ecuador138" not in demand
    assert "Total" not in demand
