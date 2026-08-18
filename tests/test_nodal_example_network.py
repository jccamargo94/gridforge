import json
from importlib.resources import files

from app.nodal.network.schemas import NodalNetwork


def test_example_network_valid():
    path = files("app.nodal.data").joinpath("example_zonal_network.json")
    net = NodalNetwork.model_validate(json.loads(path.read_text()))
    assert net.name == "example_zonal_network"
    assert {z.name for z in net.zones} >= {"norte", "centro", "sur"}
    assert net.demand_shares
