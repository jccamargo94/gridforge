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


def _capacity_data_report():
    # Real PARATEC shape: the fuel taxonomy ("Planta Hidráulica"/"Planta
    # Solar"/"Planta térmica") lives on the plant_group, one level above
    # generatorTypes. generatorTypes.name is a dispatch/ownership category
    # ("Generador"/"Autogenerador"/"Cogenerador"), never a fuel string.
    return [
        {
            "name": "Planta Hidráulica",
            "dispatchedType": [
                {
                    "generatorTypes": [
                        {
                            "name": "Generador",
                            "elements": [
                                {
                                    "elementName": "GUATAPE",
                                    "netEffectiveCapacity": "1000",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "name": "Planta térmica",
            "dispatchedType": [
                {
                    "generatorTypes": [
                        {
                            "name": "Generador",
                            "elements": [
                                {
                                    "elementName": "TERMOZIPA",
                                    "netEffectiveCapacity": "500",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    ]


def test_parse_demand_pron_reads_en_rows_and_skips_pot():
    text = (
        "SubArea Valle,1,EN,100.0,101.0,102.0,103.0,104.0,105.0,106.0\n"
        "SubArea Valle,1,POT,50.0,51.0,52.0,53.0,54.0,55.0,56.0\n"
        "SubArea Valle,2,EN,200.0,0,0,0,0,0,0\n"
    )
    demand = parse.parse_demand(text, "pron")
    assert demand["SubArea Valle"][0] == 100.0
    assert demand["SubArea Valle"][1] == 200.0


def test_parse_generators_flat_data_report():
    payload = {"dataReport": _capacity_data_report()}
    gens = parse.parse_generators(payload, {}, {}, {}, {})
    assert len(gens) == 2
    by_name = {g["name"]: g for g in gens}
    assert by_name["GUATAPE"]["fuel"] == "hydro"
    assert by_name["GUATAPE"]["marginal_cost"] == 0.0
    assert by_name["TERMOZIPA"]["fuel"] == "thermal"
    assert by_name["TERMOZIPA"]["marginal_cost"] == 80.0


def test_parse_generators_nested_data_report():
    payload = {
        "header": {"code": 200},
        "data": {"dataReport": _capacity_data_report()},
    }
    gens = parse.parse_generators(payload, {}, {}, {}, {})
    by_name = {g["name"]: g for g in gens}
    assert by_name["GUATAPE"]["fuel"] == "hydro"
    assert by_name["TERMOZIPA"]["fuel"] == "thermal"


def test_parse_lines_includes_own_subarea():
    payload = {
        "data": [
            {
                "name": "AGUABLANCA - ALFEREZ II 1 115 kV",
                "subStation": "AGUABLANCA - ALFEREZ II",
                "subArea": "SubArea Valle",
                "ratedVoltage": "115",
                "thermalLimit": 600,
                "length": 5.63,
                "typeLines": [{"reactance": 1.23, "length": 5.63}],
            }
        ]
    }
    lines = parse.parse_lines(payload)
    assert lines[0]["subarea"] == "SubArea Valle"


def test_parse_map_lines_extracts_structured_endpoints():
    payload = {
        "data": [
            {
                "type": "Feature",
                "properties": {
                    "nameLine": "CALLE67 - LA PAZ (BOGOTA) 1 115 kV",
                    "sub1": "CALLE67",
                    "sub2": "LA PAZ (BOGOTA)",
                    "subArea1": 2,
                    "subArea2": 2,
                    "emergencyLimit": 920,
                    "ratedCurrent": 800,
                },
                "geometry": {"type": "LineString", "coordinates": [[-74.06, 4.65], [-74.12, 4.63]]},
            }
        ]
    }
    lines = parse.parse_map_lines(payload)
    assert lines == [
        {
            "name": "CALLE67 - LA PAZ (BOGOTA) 1 115 kV",
            "sub1": "CALLE67",
            "sub2": "LA PAZ (BOGOTA)",
        }
    ]
