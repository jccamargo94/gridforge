import json

from app.nodal.runner import run_nodal
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
