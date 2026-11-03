"""dCondIniP plant names must map to availability resources only on a strong match.

Regression for 2026-10-27 (real XM data): PROELECTRICA 1/2 were absent from the day's
availability and the cutoff-less fuzzy matcher sent them to MERILECTRICA 1 (scores 77
and 69), so that resource had three initial-condition rows and `Ton` could not be
built ("Invalid parameter value: Ton[MERILECTRICA 1] = 'Recurso ...'").
"""

import shutil
from datetime import date
from pathlib import Path

from app.pipeline.case_builder import _map_condicion_inicial_names, build_case
from app.schemas.case import DispatchCase, DispatchLevel
from app.schemas.input_pack import InputPack, InputSource

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
FECHA = date(2024, 4, 18)


def _map(names, choices, overrides=None):
    return _map_condicion_inicial_names(names, choices, overrides or {})


def test_exact_names_map_to_themselves():
    assert _map(["TERMO1", "TERMO2"], ["TERMO1", "TERMO2"]) == {
        "TERMO1": "TERMO1",
        "TERMO2": "TERMO2",
    }


def test_legitimate_suffix_matches_measured_on_real_data_are_kept():
    choices = ["VILLANUEVA 1", "TERMOCARIBE III 1", "MERILECTRICA 1"]
    got = _map(["VILLANUEVA", "TERMOCARIBE III"], choices)
    assert got == {"VILLANUEVA": "VILLANUEVA 1", "TERMOCARIBE III": "TERMOCARIBE III 1"}


def test_plants_absent_from_availability_are_not_forced_onto_a_lookalike():
    choices = ["MERILECTRICA 1", "TERMO1"]
    got = _map(["MERILECTRICA 1", "PROELECTRICA 1", "PROELECTRICA 2"], choices)
    assert got == {"MERILECTRICA 1": "MERILECTRICA 1"}


def test_overrides_win_even_with_a_low_fuzzy_score():
    got = _map(["FLORES IV", "TERMO1"], ["TERMO1"], overrides={"FLORES IV": "FLORES 4 CC"})
    assert got == {"TERMO1": "TERMO1", "FLORES IV": "FLORES 4 CC"}


def test_build_case_ignores_unmatched_on_plant_instead_of_duplicating_a_resource(tmp_path):
    """End to end on the xm_smoke fixture: an ON plant ("TERMO1XYZ", Gpini != 0) that is
    absent from the availability data scores ~80 against TERMO1. Without the cutoff it
    was mapped onto TERMO1, giving that resource two initial-condition rows and
    breaking the `Ton` parameter (same failure as MERILECTRICA 1 on 2026-10-27)."""
    shutil.copytree(DD, tmp_path, dirs_exist_ok=True)
    extra = "TERMO1XYZ, 0, 0, 0, 1, 0, 150,  - , 150.0000, 150.0000, 0, 0, 10, 0, 5, 0, 5, 0\n"
    for p in tmp_path.rglob("dCondIniP0418.txt"):
        p.write_text(p.read_text().rstrip("\n") + "\n" + extra)

    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.ideal)
    inputs = InputPack(dispatch_date=FECHA, source=InputSource.historical, data_dir=str(tmp_path))
    set_data, param_data, meta = build_case(case, inputs)

    assert "TERMO1XYZ" not in set(set_data["I"])
    init = meta["initial_condition_df"]
    assert list(init["Recurso"]).count("TERMO1") == 1
    assert "TERMO1XYZ" not in set(init["Recurso"])
