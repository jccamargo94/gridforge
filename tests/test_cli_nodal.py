import json

from typer.testing import CliRunner

from app.cli import app
from tests.fixtures.nodal import make_three_zone_network

runner = CliRunner()


def test_cli_run_lmp(tmp_path):
    net = make_three_zone_network(congested=True)
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(net.model_dump()))
    result = runner.invoke(
        app,
        [
            "run",
            "2024-04-18",
            "-t",
            "lmp",
            "--nodal-network",
            str(net_path),
            "--out",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert tmp_path.joinpath("out", "2024-04-18-lmp", "summary.json").exists()
