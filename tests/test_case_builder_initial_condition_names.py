"""dCondIniP plant names must map to availability resources only on a strong match.

Regression for 2026-10-27 (real XM data): PROELECTRICA 1/2 were absent from the day's
availability and the cutoff-less fuzzy matcher sent them to MERILECTRICA 1 (scores 77
and 69), so that resource had three initial-condition rows and `Ton` could not be
built ("Invalid parameter value: Ton[MERILECTRICA 1] = 'Recurso ...'").
"""

from app.pipeline.case_builder import _map_condicion_inicial_names


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
