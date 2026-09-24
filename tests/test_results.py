"""Die vorgerechnete Messreihe (data/fv_results.json) und ihre Auswertung (fv_results.py): Schlüssel und Invarianten, Urteil in drei
Zuständen an der 2-Standardfehler-Grenze, Meldungszustand an der 2-%-Schwelle, Wechselwirkung aus vier Zellenkosten, Auswahl der
passenden Messreihe, Achsen des Kernabschnitts, Tabellen. Null-Spalten-Signal: keine Kennzahl ist über alle Reihen exakt 0."""
import copy
import json
import pathlib

import pytest

import fv_constants as C
import fv_results as R

DATA = R.load_results()
KEEP = ["basis", "kein_fenster", "lade20", "lade90", "kein_fenster_lade20", "kein_fenster_lade90", "reich300", "reich600",
        "fenster_locker", "fenster_eng", "fenster_regelbewusst", "fahrzeuge2", "fahrzeuge4", "live10", "live10_kein_fenster",
        "live10_kein_fenster_lade20", "live10_kein_fenster_lade90", "live10_reich300", "live10_reich400", "live10_reich600",
        "unbezahlt_basis", "unbezahlt_kein_fenster", "unbezahlt_kein_fenster_lade20", "unbezahlt_kein_fenster_lade90",
        "strafe20", "strafe80"]


# ---------------------------------------------------------------------------------------------------
# Datei
# ---------------------------------------------------------------------------------------------------
def test_results_file_is_small_and_has_exactly_the_expected_keys():
    path = pathlib.Path(R.DATA_PATH)
    assert path.stat().st_size < 120_000                                              # nur Aggregate, keine Rohdaten
    assert set(DATA) == set(KEEP) | {"_meta", "_ap0_c_unbezahlte_pausen", "_ap0_d_verspaetungsstrafe", "_ap0_b_suchrauschen", "_timings"}
    assert R.series_names(DATA) == KEEP
    text = path.read_text(encoding="utf-8")
    assert '"F-S"' not in text and '"FES"' not in text and "stafette" not in text.lower()      # die App zeigt keine Stafette


def test_no_raw_instance_data_in_the_file():
    text = pathlib.Path(R.DATA_PATH).read_text(encoding="utf-8")
    assert '"routes"' not in text and '"seeds_used"' not in text and '"xy"' not in text


@pytest.mark.parametrize("name", KEEP)
def test_series_invariants(name):
    s = DATA[name]
    assert s["instances"] == s["used"] + s["excluded"] and s["used"] > 0
    assert s["tw_ref"] in ("plain", "rules") and set(s["overrides"]) <= {"t_typ", "R", "pause_paid", "c_late"}
    for key in ("dF", "dE", "dFE", "I", "I_eur", "I_oper"):
        st = s[key]
        assert st["n"] == s["used"] and st["se"] >= 0 and st["q1"] <= st["median"] <= st["q3"] and 0 <= st["neg_share"] <= 1
    assert set(s["cells"]) == set(C.CELLS) and set(s["comps_I"]) == set(C.COST_KEYS)
    st = s["states"]
    assert st["n"] == s["used"] and st["billiger"] + st["additiv"] + st["teurer"] == pytest.approx(1.0, abs=2e-4)


@pytest.mark.parametrize("name", KEEP)
def test_interaction_is_the_sum_of_its_cost_components(name):
    """Zerlegung nach Kostenart schließt: die Komponenten der Wechselwirkung summieren sich zu I in EUR (Mittelwerte, 4 Stellen)."""
    s = DATA[name]
    assert sum(v["mean"] for v in s["comps_I"].values()) == pytest.approx(s["I_eur"]["mean"], abs=0.05)


@pytest.mark.parametrize("name", KEEP)
def test_extra_costs_and_interaction_are_consistent(name):
    """I in Prozent = Mehrkosten F+E minus F minus E (Mittelwerte sind linear)."""
    s = DATA[name]
    assert s["dFE"]["mean"] - s["dF"]["mean"] - s["dE"]["mean"] == pytest.approx(s["I"]["mean"], abs=2e-3)


def test_rule_free_cell_has_no_lateness_and_windowless_series_have_none_anywhere():
    """Konstruktion: Fenster um die regelfreie Referenz, die regelfreie Zelle ist nie verspätet; ohne Fenster gibt es nirgends
    Verspätung - dieser Nullwert ist ausdrücklich erwartet (kein Fehler-Signal)."""
    for name in KEEP:
        s = DATA[name]
        # Ausnahmen mit winziger Verspätung der regelfreien Zelle: Fenster nach Regelplan kalibriert (Referenz ist nicht die regelfreie
        # Tour) und 24 Kunden (die Suche findet eine andere regelfreie Lösung als die Referenztour, 0,003 h)
        if name in ("fenster_regelbewusst", "fahrzeuge4"):
            assert 0.0 < s["cells"]["---"]["late_h"] < 0.05
        else:
            assert s["cells"]["---"]["late_h"] == 0.0
        if s["tw_share"] == 0.0:
            assert all(s["cells"][c]["late_h"] == 0.0 for c in C.CELLS) and s["comps_I"]["verspaetung"]["mean"] == 0.0


def test_no_column_is_exactly_zero_everywhere():
    """Null-Spalten-Signal: eine Kennzahl, die in allen Reihen exakt 0 ist, wäre ein Fehler (Zweig nie ausgeführt)."""
    for key in ("dF", "dE", "dFE", "I", "I_oper"):
        assert any(DATA[n][key]["mean"] != 0.0 for n in KEEP), key
    # je Zelle die Felder, die dort möglich sind (F lädt nie, E macht nie Pause oder Nacht: das sind Schalter-Nullen, keine Fehler)
    for cell, fields in (("F--", ("nights", "breaks", "km", "idle_h", "late_h")), ("-E-", ("charges", "km", "idle_h", "late_h")),
                         ("FE-", ("nights", "breaks", "charges", "km", "idle_h", "late_h"))):
        for field in fields:
            values = [DATA[n]["cells"][cell][field] for n in KEEP]
            assert any(v != 0.0 for v in values), (cell, field)
    for k in C.COST_KEYS:
        assert any(DATA[n]["comps_I"][k]["mean"] != 0.0 for n in KEEP), k
    for k in DATA["basis"]["mechanism"]:
        assert any(DATA[n]["mechanism"][k]["mean"] != 0.0 for n in KEEP), k
    for name in KEEP:
        assert DATA[name]["cells"]["F--"]["charges"] == 0.0 and DATA[name]["cells"]["-E-"]["breaks"] == 0.0     # Schalter greifen nur einzeln
        assert DATA[name]["cells"]["-E-"]["nights"] == 0.0 and DATA[name]["cells"]["---"]["nights"] == 0.0


def test_stat_fields_survive_the_json_roundtrip():
    st = R.stat(DATA, "basis")
    assert st == R.Stat.from_dict(DATA["basis"]["I"]) and st.n == 60 and st.se > 0
    assert R.stat_fix(DATA, "basis").mean > st.mean                                     # feste Touren überschätzen die Wechselwirkung


def test_sizes_and_counts_are_labelled():
    s = DATA["reich300"]
    assert R.size_label(s) == "18 Kunden, 3 Lkw" and R.size_short(s) == "18/3"
    assert R.count_label(s) == "28 von 40 Instanzen" and R.number_label(s) == "18 Kunden, 3 Lkw, 28 von 40 Instanzen"
    assert R.count_label(DATA["basis"]) == "60 Instanzen" and R.number_label(DATA["live10"]) == "10 Kunden, 2 Lkw, 60 Instanzen"


def test_excluded_series_are_named():
    ex = {e["series"]: e for e in R.excluded_series(DATA)}
    assert set(ex) == {"reich300", "live10_reich300"}
    assert (ex["reich300"]["used"], ex["reich300"]["instances"], ex["reich300"]["excluded"]) == (28, 40, 12)
    assert (ex["live10_reich300"]["used"], ex["live10_reich300"]["instances"], ex["live10_reich300"]["excluded"]) == (29, 40, 11)
    assert ex["live10_reich300"]["reasons"] == dict(suche_ohne_loesung=3, basistouren_unter_E_nicht_fahrbar=8)


# ---------------------------------------------------------------------------------------------------
# Urteil in drei Zuständen
# ---------------------------------------------------------------------------------------------------
def test_verdict_is_decided_at_two_standard_errors_and_only_strictly_beyond():
    assert R.verdict(2.01, 1.0) == "pos" and R.verdict(-2.01, 1.0) == "neg"
    assert R.verdict(2.0, 1.0) == "none" and R.verdict(-2.0, 1.0) == "none"           # genau 2 SE: noch nicht belastbar
    assert R.verdict(0.0, 1.0) == "none" and R.verdict(1.99, 1.0) == "none" and R.verdict(-1.99, 1.0) == "none"
    assert R.verdict(0.5, 0.0) == "pos" and R.verdict(-0.5, 0.0) == "neg" and R.verdict(0.0, 0.0) == "none"
    assert R.verdict(3.0, 1.0, factor=3.0) == "none" and R.verdict(3.1, 1.0, factor=3.0) == "pos"
    assert C.SE_FACTOR == 2.0


def test_verdict_of_a_stat_object():
    assert R.Stat(n=10, mean=2.5, se=1.0).verdict() == "pos" and R.Stat(n=10, mean=-2.5, se=1.0).verdict() == "neg"
    assert R.Stat(n=10, mean=1.5, se=1.0).verdict() == "none"


def test_verdicts_of_the_measured_headline_results():
    assert R.stat(DATA, "basis").verdict() == "pos" and R.stat(DATA, "live10").verdict() == "pos"
    assert R.stat(DATA, "kein_fenster").verdict() == "neg" and R.stat(DATA, "kein_fenster_lade90").verdict() == "neg"
    assert R.stat(DATA, "unbezahlt_kein_fenster_lade20").verdict() == "none"           # bei 20 min unbezahlt: nicht von 0 zu unterscheiden
    assert {R.VERDICT_TEXT[v] for v in ("neg", "pos", "none")} == {"billiger als die Summe (belastbar)", "teurer als die Summe (belastbar)",
                                                                   "nicht von additiv zu unterscheiden"}


# ---------------------------------------------------------------------------------------------------
# Meldung der Live-Instanz und Wechselwirkung
# ---------------------------------------------------------------------------------------------------
def test_message_state_boundaries_at_two_percent():
    assert C.THRESHOLD_PCT == 2.0
    assert R.message_state(-2.01) == "billiger" and R.message_state(-2.0) == "additiv" and R.message_state(0.0) == "additiv"
    assert R.message_state(2.0) == "additiv" and R.message_state(2.01) == "teurer"
    assert R.message_state(-50.0) == "billiger" and R.message_state(50.0) == "teurer"
    assert R.message_state(2.4, threshold=3.0) == "additiv" and R.message_state(3.1, threshold=3.0) == "teurer"


def test_interaction_from_costs_by_hand():
    x = R.interaction_from_costs({"---": 1000.0, "F--": 1400.0, "-E-": 1200.0, "FE-": 1700.0})
    assert x["dF_eur"] == 400.0 and x["dE_eur"] == 200.0 and x["dFE_eur"] == 700.0 and x["sum_eur"] == 600.0
    assert x["I_eur"] == 100.0 and x["I_pct"] == 10.0 and x["dF_pct"] == 40.0 and x["dE_pct"] == 20.0 and x["dFE_pct"] == 70.0
    y = R.interaction_from_costs({"---": 2000.0, "F--": 2600.0, "-E-": 2500.0, "FE-": 2900.0})
    assert y["I_eur"] == -200.0 and y["I_pct"] == -10.0                              # Kombination billiger als die Summe
    assert R.interaction_from_costs({"---": 500.0, "F--": 600.0, "-E-": 700.0, "FE-": 800.0})["I_eur"] == 0.0


# ---------------------------------------------------------------------------------------------------
# Passende Messreihe zu den Reglern
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("n,K,window,charge,rng,expected", [
    (18, 3, "mittel", 45, 400, "basis"), (18, 3, "keine", 45, 400, "kein_fenster"), (18, 3, "mittel", 20, 400, "lade20"),
    (18, 3, "mittel", 90, 400, "lade90"), (18, 3, "keine", 20, 400, "kein_fenster_lade20"), (18, 3, "keine", 90, 400, "kein_fenster_lade90"),
    (18, 3, "mittel", 45, 300, "reich300"), (18, 3, "mittel", 45, 600, "reich600"), (18, 3, "locker", 45, 400, "fenster_locker"),
    (18, 3, "eng", 45, 400, "fenster_eng"), (10, 2, "mittel", 45, 400, "live10"), (10, 2, "keine", 45, 400, "live10_kein_fenster"),
    (10, 2, "keine", 20, 400, "live10_kein_fenster_lade20"), (10, 2, "keine", 90, 400, "live10_kein_fenster_lade90"),
    (10, 2, "mittel", 45, 300, "live10_reich300"), (10, 2, "mittel", 45, 600, "live10_reich600"), (12, 2, "mittel", 45, 400, "fahrzeuge2"),
    (24, 4, "mittel", 45, 400, "fahrzeuge4"),
])
def test_find_series_matches_size_and_settings(n, K, window, charge, rng, expected):
    assert R.find_series(DATA, n, K, window, charge, rng) == expected


def test_find_series_returns_none_without_a_measured_series_and_ignores_sensitivity_runs():
    assert R.find_series(DATA, 10, 2, "eng", 45, 400) is None and R.find_series(DATA, 10, 2, "mittel", 90, 400) is None
    assert R.find_series(DATA, 8, 2, "mittel", 45, 400) is None and R.find_series(DATA, 18, 3, "mittel", 45, 350) is None
    for name in ("unbezahlt_basis", "strafe20", "strafe80", "fenster_regelbewusst"):
        found = {R.find_series(DATA, DATA[name]["n"], DATA[name]["K"], w, t, r) for w in C.WINDOW_OPTIONS for t in C.CHARGE_OPTIONS
                 for r in C.RANGE_OPTIONS}
        assert name not in found


def test_find_series_prefers_the_series_with_more_instances():
    assert DATA["live10"]["used"] > DATA["live10_reich400"]["used"]
    assert R.find_series(DATA, 10, 2, "mittel", 45, 400) == "live10"


# ---------------------------------------------------------------------------------------------------
# Achsen des Kernabschnitts
# ---------------------------------------------------------------------------------------------------
def test_every_axis_lists_both_sizes_where_measured_with_counts_and_verdicts():
    assert R.AXIS_NAMES == ("Ladezeit", "Reichweite", "Zeitfenster", "Fahrzeuge")
    for axis in R.AXIS_NAMES:
        rows = R.axis_rows(DATA, axis)
        assert rows and all(r["used"] > 0 and r["count"] and r["size"] and r["verdict"] in ("neg", "pos", "none") for r in rows)
    sizes = {a: {r["size"] for r in R.axis_rows(DATA, a)} for a in R.AXIS_NAMES}
    assert sizes["Ladezeit"] == sizes["Reichweite"] == sizes["Zeitfenster"] == {"10/2", "18/3"}
    assert sizes["Fahrzeuge"] == {"12/2", "18/3", "24/4"}                               # jede Stufe ihre eigene Größe


def test_axis_values_are_the_measured_ones():
    lade = {(r["group"], r["level"], r["size"]): r["stat"].mean for r in R.axis_rows(DATA, "Ladezeit")}
    assert lade[("ohne Zeitfenster", "90 min", "18/3")] == pytest.approx(-4.78, abs=0.01)
    assert lade[("ohne Zeitfenster", "20 min", "18/3")] == pytest.approx(1.61, abs=0.01)
    assert lade[("Zeitfenster mittel", "20 min", "18/3")] == pytest.approx(11.29, abs=0.01)
    assert lade[("ohne Zeitfenster", "90 min", "10/2")] == pytest.approx(-5.52, abs=0.01)
    reich = {(r["level"], r["size"]): r["stat"].mean for r in R.axis_rows(DATA, "Reichweite")}
    assert reich[("300 km", "18/3")] == pytest.approx(18.05, abs=0.01) and reich[("600 km", "18/3")] == pytest.approx(2.67, abs=0.01)
    assert reich[("300 km", "10/2")] == pytest.approx(12.58, abs=0.01)
    fenster = {(r["level"], r["size"]): r["stat"].mean for r in R.axis_rows(DATA, "Zeitfenster")}
    assert fenster[("locker", "18/3")] == pytest.approx(3.08, abs=0.01) and fenster[("eng", "18/3")] == pytest.approx(10.10, abs=0.01)
    fzg = {r["level"]: r["stat"].mean for r in R.axis_rows(DATA, "Fahrzeuge")}
    assert fzg["2 Lkw"] == pytest.approx(4.29, abs=0.01) and fzg["3 Lkw"] == pytest.approx(7.92, abs=0.01) and fzg["4 Lkw"] == pytest.approx(5.95, abs=0.01)


def test_sum_rows_cover_both_sizes_with_and_without_windows():
    rows = R.sum_rows(DATA)
    assert [(r["size"], r["window"]) for r in rows] == [("10/2", "ohne Zeitfenster"), ("10/2", "Zeitfenster mittel"),
                                                        ("18/3", "ohne Zeitfenster"), ("18/3", "Zeitfenster mittel")]
    for r in rows:
        assert r["dF"].mean > 0 and r["dE"].mean > 0 and r["dFE"].mean > 0
        assert r["dFE"].mean - r["dF"].mean - r["dE"].mean == pytest.approx(r["I"].mean, abs=2e-3)
        assert r["dFE"].mean < r["dF"].mean + r["dE"].mean or r["window"] == "Zeitfenster mittel"       # ohne Fenster nicht teurer


# ---------------------------------------------------------------------------------------------------
# Laden robust
# ---------------------------------------------------------------------------------------------------
def test_load_results_reads_any_path(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"basis": {"n": 1}}), encoding="utf-8")
    assert R.load_results(p) == {"basis": {"n": 1}}
    assert R.load_results() is R.load_results()                                        # zwischengespeichert


def test_series_names_skips_private_keys():
    assert R.series_names({"_meta": 1, "a": 2, "b": 3, "_x": 4}) == ["a", "b"]


def test_deep_copies_of_the_data_do_not_affect_the_cached_object():
    d = copy.deepcopy(DATA)
    d["basis"]["I"]["mean"] = 99.0
    assert R.load_results()["basis"]["I"]["mean"] != 99.0
