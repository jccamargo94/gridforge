from app.nodal.network.schemas import Branch, BusLoad, Generator, NodalNetwork, Zone


def make_three_zone_network(*, congested: bool = False) -> NodalNetwork:
    rating = 120.0 if congested else 400.0
    return NodalNetwork(
        name="three_zone",
        baseMVA=100.0,
        reference_zone="norte",
        zones=[Zone(name="norte"), Zone(name="centro"), Zone(name="sur")],
        generators=[
            Generator(
                name="G_N",
                zone="norte",
                p_min=0.0,
                p_max=500.0,
                marginal_cost=20.0,
                fuel="hydro",
                initial_status=1,
            ),
            Generator(
                name="G_C",
                zone="centro",
                p_min=0.0,
                p_max=300.0,
                marginal_cost=80.0,
                fuel="gas",
                initial_status=-1,
            ),
            Generator(
                name="G_S",
                zone="sur",
                p_min=0.0,
                p_max=300.0,
                marginal_cost=120.0,
                fuel="coal",
                initial_status=-1,
            ),
        ],
        branches=[
            Branch(name="NC", from_zone="norte", to_zone="centro", reactance=0.1, rating=rating),
            Branch(name="CS", from_zone="centro", to_zone="sur", reactance=0.1, rating=rating),
        ],
        loads=[
            BusLoad(zone="norte", p_load=[100.0] * 24),
            BusLoad(zone="centro", p_load=[100.0] * 24),
            BusLoad(zone="sur", p_load=[100.0] * 24),
        ],
    )
