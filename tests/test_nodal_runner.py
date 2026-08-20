import json
from datetime import date

from app.nodal.runner import build_generator_costs, run_nodal
from app.schemas import DispatchCase, DispatchLevel
from tests.fixtures.nodal import make_three_zone_network


def test_run_nodal_writes_artifacts(tmp_path):
    net = make_three_zone_network(congested=True)
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(net.model_dump()))
    case = DispatchCase(
        dispatch_date="2024-04-18", level=DispatchLevel.lmp, nodal_network=str(net_path)
    )
    result = run_nodal(case, out=str(tmp_path / "out"), data_dir=str(tmp_path))
    assert result.ok, result.error
    assert result.metrics["congestion_rent_total"] > 0
    assert tmp_path.joinpath("out", "2024-04-18-lmp", "summary.json").exists()


def test_run_nodal_populates_nodal_result_with_full_paths(tmp_path):
    net = make_three_zone_network(congested=True)
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(net.model_dump()))
    case = DispatchCase(
        dispatch_date="2024-04-18", level=DispatchLevel.lmp, nodal_network=str(net_path)
    )
    out_dir = str(tmp_path / "out")
    result = run_nodal(case, out=out_dir, data_dir=str(tmp_path))
    assert result.ok, result.error
    nodal = result.nodal
    assert nodal is not None
    # dispatch_path ya no es relativo (bug latente corregido)
    assert result.dispatch_path == f"{out_dir}/2024-04-18-lmp/dispatch.csv"
    assert nodal.lmp_path == f"{out_dir}/2024-04-18-lmp/lmp.csv"
    assert nodal.summary_path == f"{out_dir}/2024-04-18-lmp/summary.json"
    assert nodal.network["name"] == "three_zone"
    assert len(nodal.redistribution) == 3
    assert len(nodal.gen_revenue_by_zone) == 3
    for attr in (
        "lmp_path",
        "dispatch_path",
        "branch_flows_path",
        "settlement_status_quo_path",
        "settlement_lmp_path",
        "comparison_path",
        "summary_path",
    ):
        assert getattr(nodal, attr) is not None


def test_build_generator_costs_skips_synthetic_networks(tmp_path):
    # No demand_shares (three_zone example) -> no market lookup, no attempt
    # to read data_dir at all.
    net = make_three_zone_network()
    costs = build_generator_costs(net, date(2026, 8, 1), str(tmp_path))
    assert [g.marginal_cost for g in costs] == [g.marginal_cost for g in net.generators]


def test_build_generator_costs_overrides_matched_generator_from_ofertas(tmp_path):
    # Realistic multi-word names -- short synthetic names like "G_N"/"G_C"
    # are too similar to each other for the fuzzy matcher to disambiguate.
    net = make_three_zone_network().model_copy(
        update={
            "demand_shares": {"norte": 0.5, "centro": 0.3, "sur": 0.2},
            "generators": [
                g.model_copy(update={"name": name})
                for g, name in zip(
                    make_three_zone_network().generators,
                    ["GUATAPE", "TERMOZIPA", "GECELCA3"],
                    strict=True,
                )
            ],
        }
    )
    ofertas_dir = tmp_path / "ofertas"
    ofertas_dir.mkdir()
    ofertas_dir.joinpath("ofertas_2026.csv").write_text(
        "Date,resource_name,Value\n2026-08-01,GUATAPE,45.5\n2026-08-01,TERMOZIPA,88.0\n"
    )
    costs = build_generator_costs(net, date(2026, 8, 1), str(tmp_path))
    by_name = {g.name: g for g in costs}
    assert by_name["GUATAPE"].marginal_cost == 45.5
    assert by_name["TERMOZIPA"].marginal_cost == 88.0
    # No matching oferta for GECELCA3 -> keeps its static topology-scrape cost.
    assert by_name["GECELCA3"].marginal_cost == 120.0
