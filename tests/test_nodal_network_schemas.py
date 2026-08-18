import pytest
from pydantic import ValidationError

from app.nodal.network.schemas import Branch, BusLoad, Generator, NodalNetwork, Zone


def _valid_net() -> NodalNetwork:
    return NodalNetwork(
        reference_zone="norte",
        zones=[Zone(name="norte"), Zone(name="centro")],
        generators=[Generator(name="G1", zone="norte", p_max=100.0, marginal_cost=20.0)],
        branches=[
            Branch(name="NC", from_zone="norte", to_zone="centro", reactance=0.1, rating=100.0)
        ],
        loads=[
            BusLoad(zone="norte", p_load=[10.0] * 24),
            BusLoad(zone="centro", p_load=[10.0] * 24),
        ],
    )


def test_valid_network_constructs():
    net = _valid_net()
    assert net.reference_zone == "norte"
    assert len(net.loads) == 2


@pytest.mark.parametrize(
    "mutate, error_substr",
    [
        (lambda n: n.__dict__.update(reference_zone="sur"), "reference"),
        (lambda n: n.generators[0].__dict__.update(zone="sur"), "zone"),
        (lambda n: n.branches[0].__dict__.update(to_zone="sur"), "to_zone"),
        (lambda n: n.loads[0].__dict__.update(zone="sur"), "zone"),
    ],
)
def test_invalid_references_rejected(mutate, error_substr):
    net = _valid_net()
    mutate(net)
    with pytest.raises(ValidationError, match=error_substr):
        NodalNetwork.model_validate(net.model_dump())


def test_loads_must_be_24_hours():
    with pytest.raises(ValidationError):
        BusLoad(zone="norte", p_load=[10.0, 20.0])


def test_demand_shares_must_sum_to_one():
    net = _valid_net()
    net.demand_shares = {"norte": 0.5, "centro": 0.4}
    with pytest.raises(ValidationError, match="sum"):
        NodalNetwork.model_validate(net.model_dump())


def test_demand_shares_must_cover_all_zones():
    net = _valid_net()
    net.demand_shares = {"norte": 1.0}
    with pytest.raises(ValidationError, match="zone"):
        NodalNetwork.model_validate(net.model_dump())
