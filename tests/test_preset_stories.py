"""Erfüllen die echten Presets ihre Abnahmekriterien - auf der vorgerechneten Messreihe - und erzählt die gezeigte Live-Instanz (ein
Seed außerhalb der Stichprobe) qualitativ dieselbe Geschichte? Deterministisch; die Live-Rechnung mit 10 Kunden dauert je Preset
einige Sekunden (test_shown_instance_tells_the_story_of_its_preset)."""
import pytest

import fv_constants as C
import fv_live as LV
import fv_results as R
import fv_stories as ST
from fv_ui_panel import message

DATA = R.load_results()
# Meldungszustand, den die gezeigte Instanz je Preset zeigen soll (tools/tune_presets.py: der in der Messreihe häufigste Zustand)
EXPECTED_STATE = {"Standard": "teurer", "Ohne Zeitfenster": "additiv", "Lange Ladung": "billiger", "Kurze Ladung": "additiv",
                  "Knappe Reichweite": "teurer"}


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_preset_satisfies_its_own_acceptance_criteria(name):
    for ok, text in ST.criteria(name, DATA):
        assert ok, f"{name}: {text}"


def test_each_story_shows_up_in_the_sign_pattern_of_the_interaction():
    """Kernaussage der Demo: das Vorzeichen der Wechselwirkung hängt von Ladezeit, Reichweite und Zeitfenstern ab."""
    v = {name: R.stat(DATA, s).verdict() for name, s in (("std", "basis"), ("kein", "kein_fenster"), ("lang", "kein_fenster_lade90"),
                                                          ("kurz", "kein_fenster_lade20"), ("knapp", "reich300"))}
    assert v == {"std": "pos", "kein": "neg", "lang": "neg", "kurz": "pos", "knapp": "pos"}


def test_the_presets_use_the_measured_series_they_are_checked_against():
    p = C.PRESETS
    assert R.find_series(DATA, 18, 3, p["Standard"]["window"], p["Standard"]["charge"], p["Standard"]["range_km"]) == "basis"
    assert R.find_series(DATA, 18, 3, p["Ohne Zeitfenster"]["window"], p["Ohne Zeitfenster"]["charge"], p["Ohne Zeitfenster"]["range_km"]) == "kein_fenster"
    assert R.find_series(DATA, 18, 3, p["Lange Ladung"]["window"], p["Lange Ladung"]["charge"], p["Lange Ladung"]["range_km"]) == "kein_fenster_lade90"
    assert R.find_series(DATA, 18, 3, p["Kurze Ladung"]["window"], p["Kurze Ladung"]["charge"], p["Kurze Ladung"]["range_km"]) == "kein_fenster_lade20"
    assert R.find_series(DATA, 18, 3, p["Knappe Reichweite"]["window"], p["Knappe Reichweite"]["charge"], p["Knappe Reichweite"]["range_km"]) == "reich300"
    for name, q in p.items():                                                             # jedes Preset hat auch eine Reihe in Live-Größe
        assert R.find_series(DATA, 10, 2, q["window"], q["charge"], q["range_km"]) is not None, name


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_shown_instance_tells_the_story_of_its_preset(name):
    """Die gezeigte Einzelinstanz bleibt qualitativ: alle Zellen zulässig und der Meldungszustand ist der in der Messreihe
    häufigste. Der Anzeige-Seed liegt weit genug von der Schwelle, dass ein Rundungsunterschied den Zustand nicht kippt."""
    p = C.PRESETS[name]
    res = LV.solve_live(p["customers"], p["charge"], p["range_km"], p["window"], p["seed"])
    assert all(c["feasible"] for c in res["cells"].values())
    costs = {c: res["cells"][c]["total"] for c in C.CELLS}
    x = R.interaction_from_costs(costs)
    state, _ = message(res, x, DATA)
    assert state == EXPECTED_STATE[name], (name, x["I_pct"])
    assert abs(abs(x["I_pct"]) - C.THRESHOLD_PCT) > 0.5, (name, x["I_pct"])                 # Abstand zur Schwelle
    series = R.stat(DATA, R.find_series(DATA, 10, 2, p["window"], p["charge"], p["range_km"]))
    assert abs(x["I_pct"] - series.mean) < 3 * series.se + 1.0                               # nah am Mittel der Messreihe


def test_the_state_shown_is_a_common_state_of_the_measured_instances():
    """Der gezeigte Meldungszustand ist kein Ausreißer: er kommt in der Messreihe in Live-Größe bei mindestens 25 % der Instanzen vor
    (Schwelle 2 %); bei 'Ohne Zeitfenster' ist 'billiger' häufiger (57 %), gezeigt wird die Instanz nahe am Mittel (praktisch additiv,
    30 %), passend zur Geschichte 'spart etwas, aber kaum'."""
    for name, p in C.PRESETS.items():
        s = DATA[R.find_series(DATA, 10, 2, p["window"], p["charge"], p["range_km"])]["states"]
        assert s[EXPECTED_STATE[name]] >= 0.25, (name, s)
    lange = DATA["live10_kein_fenster_lade90"]["states"]
    assert lange["billiger"] > lange["additiv"] and lange["billiger"] > lange["teurer"]              # Lange Ladung: klar billiger
    kurz = DATA["live10_kein_fenster_lade20"]["states"]
    assert kurz["additiv"] + kurz["teurer"] > 0.5                                                    # Kurze Ladung: nicht billiger
