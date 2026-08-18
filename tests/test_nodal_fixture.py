from tests.fixtures.nodal import make_three_zone_network


def test_fixture_structure():
    for congested in (False, True):
        net = make_three_zone_network(congested=congested)
        assert net.reference_zone == "norte"
        assert [z.name for z in net.zones] == ["norte", "centro", "sur"]
        assert {g.name for g in net.generators} == {"G_N", "G_C", "G_S"}
        assert {b.name for b in net.branches} == {"NC", "CS"}
        assert {load.zone for load in net.loads} == {"norte", "centro", "sur"}
        assert all(len(load.p_load) == 24 for load in net.loads)


def test_fixture_congested_rating():
    rating_loose = next(
        b.rating for b in make_three_zone_network(congested=False).branches if b.name == "NC"
    )
    rating_tight = next(
        b.rating for b in make_three_zone_network(congested=True).branches if b.name == "NC"
    )
    assert rating_loose > rating_tight
