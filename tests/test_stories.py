"""Abnahmekriterien der Presets (fv_stories.py) an KÜNSTLICHEN Messreihen: jedes Kriterium wird einzeln an seiner Schwelle gekippt
(gerade noch erfüllt, gerade nicht mehr), und Vorzeichen-Kriterien kippen auch über die Standardfehler-Bedingung. Die echten
Presets gegen die echte Messreihe stehen in tests/test_preset_stories.py."""
import copy

import pytest

import fv_constants as C
import fv_results as R
import fv_stories as ST

DATA = R.load_results()


def _stat(mean, se=1.0, neg_share=0.5, n=60):
    return dict(n=n, mean=mean, se=se, median=mean, q1=mean - 1, q3=mean + 1, neg_share=neg_share)


def _data(**overrides):
    """Künstliche Messreihe, in der ALLE Kriterien aller Presets knapp erfüllt sind; overrides ändern einzelne Werte."""
    d = {
        "basis": dict(used=60, instances=60, I=_stat(10.0), I_oper=_stat(3.0), dF=_stat(40.0), dE=_stat(20.0)),
        "live10": dict(used=60, instances=60, I=_stat(8.0), I_oper=_stat(3.0)),
        "kein_fenster": dict(used=60, instances=60, I=_stat(-1.0, se=0.25, neg_share=0.65)),
        "kein_fenster_lade90": dict(used=40, instances=40, I=_stat(-5.0, se=0.3, neg_share=0.95)),
        "kein_fenster_lade20": dict(used=40, instances=40, I=_stat(1.5, se=0.3)),
        "live10_kein_fenster_lade20": dict(used=40, instances=40, I=_stat(1.4, se=0.5)),
        "reich300": dict(used=28, instances=40, I=_stat(15.0, se=2.0)),
    }
    for path, value in overrides.items():
        name, *keys = path.split("__")
        target = d[name]
        for k in keys[:-1]:
            target = target[k]
        target[keys[-1]] = value
    return d


def _ok(name, data):
    return [ok for ok, _ in ST.criteria(name, data)]


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_the_artificial_series_satisfy_every_criterion(name):
    assert all(_ok(name, _data())), name


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_criteria_have_texts_and_the_real_data_satisfy_them(name):
    crit = ST.criteria(name, DATA)
    assert crit and all(ok for ok, _ in crit), [t for ok, t in crit if not ok]
    assert all(isinstance(t, str) and len(t) > 10 for _, t in crit)


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        ST.criteria("Unbekannt", DATA)


# --- Standard --------------------------------------------------------------------------------------
def test_standard_i_must_be_positive_and_beyond_two_standard_errors():
    assert _ok("Standard", _data(basis__I__mean=2.01, basis__I__se=1.0, basis__I_oper__mean=0.5))[0]
    assert not _ok("Standard", _data(basis__I__mean=2.0, basis__I__se=1.0, basis__I_oper__mean=0.5))[0]      # genau 2 SE: nicht belastbar
    assert not _ok("Standard", _data(basis__I__mean=-5.0))[0]
    assert not _ok("Standard", _data(live10__I__mean=2.0, live10__I__se=1.0, live10__I_oper__mean=0.5))[2]
    assert _ok("Standard", _data(live10__I__mean=2.01, live10__I__se=1.0, live10__I_oper__mean=0.5))[2]
    assert not _ok("Standard", _data(live10__I__mean=-8.0))[2]


def test_standard_operating_share_is_at_most_forty_percent():
    assert _ok("Standard", _data(basis__I_oper__mean=4.0))[1] and not _ok("Standard", _data(basis__I_oper__mean=4.01))[1]
    assert _ok("Standard", _data(live10__I_oper__mean=3.2))[3] and not _ok("Standard", _data(live10__I_oper__mean=3.21))[3]
    assert ST.STANDARD_OPER_MAX_SHARE == 0.40


def test_standard_needs_drivers_rules_to_cost_more_than_electric():
    assert _ok("Standard", _data(basis__dF__mean=20.5))[4] and not _ok("Standard", _data(basis__dF__mean=20.0))[4]
    assert not _ok("Standard", _data(basis__dF__mean=15.0))[4]


# --- Ohne Zeitfenster --------------------------------------------------------------------------------
def test_no_window_needs_a_clearly_negative_but_small_interaction():
    assert _ok("Ohne Zeitfenster", _data(kein_fenster__I__mean=-0.51, kein_fenster__I__se=0.25))[0]
    assert not _ok("Ohne Zeitfenster", _data(kein_fenster__I__mean=-0.5, kein_fenster__I__se=0.25))[0]       # genau 2 SE
    assert not _ok("Ohne Zeitfenster", _data(kein_fenster__I__mean=1.0))[0]                                  # positiv
    assert _ok("Ohne Zeitfenster", _data(kein_fenster__I__mean=-1.99, kein_fenster__I__se=0.1))[1]
    assert not _ok("Ohne Zeitfenster", _data(kein_fenster__I__mean=-2.0, kein_fenster__I__se=0.1))[1]        # |I| unter 2, nicht gleich
    assert not _ok("Ohne Zeitfenster", _data(kein_fenster__I__mean=-3.0, kein_fenster__I__se=0.1))[1]
    assert ST.NO_WINDOW_MAX_ABS_I == 2.0


def test_no_window_share_of_negative_instances_is_between_55_and_75_percent():
    for value, expected in ((0.55, True), (0.549, False), (0.75, True), (0.751, False), (0.65, True), (0.1, False), (1.0, False)):
        assert _ok("Ohne Zeitfenster", _data(kein_fenster__I__neg_share=value))[2] is expected, value
    assert ST.NO_WINDOW_NEG_SHARE == (0.55, 0.75)


# --- Lange Ladung ---------------------------------------------------------------------------------------
def test_long_charge_needs_at_most_minus_three_points_beyond_two_standard_errors():
    assert _ok("Lange Ladung", _data(kein_fenster_lade90__I__mean=-3.0, kein_fenster_lade90__I__se=0.5))[0]
    assert not _ok("Lange Ladung", _data(kein_fenster_lade90__I__mean=-2.99, kein_fenster_lade90__I__se=0.1))[0]   # nicht weit genug
    assert not _ok("Lange Ladung", _data(kein_fenster_lade90__I__mean=-3.0, kein_fenster_lade90__I__se=1.5))[0]    # nicht > 2 SE
    assert not _ok("Lange Ladung", _data(kein_fenster_lade90__I__mean=+5.0))[0]
    assert ST.LONG_CHARGE_MAX_I == -3.0


def test_long_charge_needs_at_least_ninety_percent_negative_instances():
    assert _ok("Lange Ladung", _data(kein_fenster_lade90__I__neg_share=0.90))[1]
    assert not _ok("Lange Ladung", _data(kein_fenster_lade90__I__neg_share=0.899))[1]
    assert _ok("Lange Ladung", _data(kein_fenster_lade90__I__neg_share=1.0))[1]
    assert ST.LONG_CHARGE_MIN_NEG_SHARE == 0.90


# --- Knappe Reichweite ---------------------------------------------------------------------------------
def test_tight_range_needs_at_least_ten_points_beyond_two_standard_errors():
    assert _ok("Knappe Reichweite", _data(reich300__I__mean=10.0, reich300__I__se=1.99))[0]                 # 10 >= 10 und > 2 SE
    assert _ok("Knappe Reichweite", _data(reich300__I__mean=10.0, reich300__I__se=1.0))[0]
    assert not _ok("Knappe Reichweite", _data(reich300__I__mean=9.99, reich300__I__se=1.0))[0]
    assert not _ok("Knappe Reichweite", _data(reich300__I__mean=10.0, reich300__I__se=5.0))[0]            # genau 2 SE: nicht belastbar
    assert not _ok("Knappe Reichweite", _data(reich300__I__mean=-20.0, reich300__I__se=1.0))[0]
    assert ST.TIGHT_RANGE_MIN_I == 10.0


def test_tight_range_text_names_the_excluded_layouts():
    text = ST.criteria("Knappe Reichweite", DATA)[0][1]
    assert "28 von 40" in text


# --- Kurze Ladung ------------------------------------------------------------------------------------------
def test_short_charge_needs_a_positive_interaction_in_both_sizes():
    assert not _ok("Kurze Ladung", _data(kein_fenster_lade20__I__mean=0.5, kein_fenster_lade20__I__se=0.25))[0]     # genau 2 SE
    assert _ok("Kurze Ladung", _data(kein_fenster_lade20__I__mean=0.51, kein_fenster_lade20__I__se=0.25))[0]
    assert not _ok("Kurze Ladung", _data(kein_fenster_lade20__I__mean=-1.5))[0]
    assert not _ok("Kurze Ladung", _data(live10_kein_fenster_lade20__I__mean=1.0, live10_kein_fenster_lade20__I__se=0.5))[1]
    assert _ok("Kurze Ladung", _data(live10_kein_fenster_lade20__I__mean=1.01, live10_kein_fenster_lade20__I__se=0.5))[1]
    assert not _ok("Kurze Ladung", _data(live10_kein_fenster_lade20__I__mean=-1.0))[1]


def test_short_charge_has_no_criterion_on_the_share_of_negative_instances():
    """Plan Abschnitt 7: kein Kriterium auf dem Anteil I < 0 (Live-Größe 55 %)."""
    assert len(ST.criteria("Kurze Ladung", DATA)) == 2
    assert _ok("Kurze Ladung", _data(live10_kein_fenster_lade20__I__neg_share=0.9)) == [True, True]


def test_every_criterion_of_every_preset_is_tested_individually():
    counts = {name: len(ST.criteria(name, DATA)) for name in C.PRESETS}
    assert counts == {"Standard": 5, "Ohne Zeitfenster": 3, "Lange Ladung": 2, "Kurze Ladung": 2, "Knappe Reichweite": 1}


def test_the_artificial_data_do_not_alias_the_real_data():
    d = _data()
    assert d["basis"] is not DATA["basis"]
    real = copy.deepcopy(DATA["basis"]["I"])
    _data(basis__I__mean=99.0)
    assert DATA["basis"]["I"] == real
