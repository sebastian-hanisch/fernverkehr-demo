"""JEDE Zahl aus dem README und den App-Texten wird hier nachgerechnet (Playbook: erst messen, dann Text schreiben). Die Zahlen
kommen aus data/fv_results.json (vorgerechnet aus tools/sweep.py und tools/dump_sweep.py); der Test formatiert sie wie die App und
verlangt, dass genau diese Zeichenkette im README steht. Die Aussagen der Vorab-Messung, die nicht in der Ergebnisdatei stehen
(Stafette, Evaluator-Fehler 0,18 %, 20 % erreichbare Lagen), stehen im README ausdrücklich als solche und sind NICHT Teil der CI-Tests."""
import pathlib
import re

import pytest

import fv_results as R
import fv_ui_panel as UI

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
DATA = R.load_results()


def band(name, key="I", digits=1):
    """'+7,9 ± 1,0 %' wie in der App und im README."""
    return UI.fmt_band(R.stat(DATA, name, key), digits)


def num(v, digits=1, signed=False):
    return UI.fmt_num(v, digits, signed)


def has(*needles):
    for n in needles:
        assert n in README, n


def test_what_the_rules_cost():
    has(band("basis", "dF"), band("basis", "dE"), band("basis", "dFE"))                        # mit Fenstern (18/3)
    free = [band("kein_fenster", k).replace(" %", "") for k in ("dF", "dE", "dFE")]                # ohne Fenster: "+21,1 ± 0,2 / +18,1 ± 0,4 / +38,3 ± 0,5 %"
    has("ohne Zeitfenster " + " / ".join(free) + " %")
    assert R.stat(DATA, "basis", "dF").mean > R.stat(DATA, "basis", "dE").mean


def test_the_overlap_is_real():
    m = DATA["kein_fenster"]["mechanism"]
    assert f"{m['share_breaks_at_charger']['mean']:.0f} % der Pausen liegen an einer Ladesäule" in README
    assert f"{m['free_charge_min_FE']['mean']:.0f} Lademinuten" in README
    assert f"{num(m['rests_at_charger_FE']['mean'])} von {num(m['nights_FE']['mean'])} Tagesruhen" in README
    assert 60 < m["share_breaks_at_charger"]["mean"] < 67                                     # "knapp zwei Drittel"
    assert "knapp zwei Drittel der Pausen" in README


def test_without_time_windows_the_costs_nearly_add():
    s = R.stat(DATA, "kein_fenster")
    c = DATA["kein_fenster"]["comps_I"]
    has(band("kein_fenster").replace("-", "−"), f"bei {s.neg_share * 100:.0f} % der Instanzen I < 0")
    has(f"{num(c['fahrer']['mean'], 0, True)} ± {num(c['fahrer']['se'], 0)} EUR".replace("-", "−"),
        f"{num(c['naechte']['mean'], 0, True)} ± {num(c['naechte']['se'], 0)} EUR", f"{num(c['fahrzeug']['mean'], 0, True)} ± {num(c['fahrzeug']['se'], 0)} EUR")
    assert s.verdict() == "neg" and abs(s.mean) < 2.0
    summe = R.stat(DATA, "kein_fenster", "dF").mean + R.stat(DATA, "kein_fenster", "dE").mean
    assert 0.02 < abs(s.mean) / summe < 0.03                                                   # "rund 2 % der Summe der Einzelkosten"
    has("rund 2 % der Summe der Einzelkosten")


def test_with_time_windows_the_combination_is_dearer():
    s = R.stat(DATA, "basis")
    c = DATA["basis"]["comps_I"]["verspaetung"]
    has(band("basis"), f"nur bei {s.neg_share * 100:.0f} % der Instanzen I < 0", band("basis", "I_oper"),
        f"{num(c['mean'], 0, True)} ± {num(c['se'], 0)} EUR")
    assert s.verdict() == "pos" and R.stat(DATA, "basis", "I_oper").verdict() == "none"
    assert c["mean"] > 4 * c["se"]


def test_the_sign_depends_on_the_charging_time():
    free = [R.stat(DATA, n) for n in ("kein_fenster_lade20", "kein_fenster", "kein_fenster_lade90")]
    win = [R.stat(DATA, n) for n in ("lade20", "basis", "lade90")]
    has("I = +1,6 ± 0,3 / −0,9 ± 0,3 / **−4,8 ± 0,3 %**")
    has("+11,3 ± 1,2 / +7,9 ± 1,0 / +3,9 ± 1,4 %")
    assert [UI.fmt_band(s, 1) for s in free] == ["+1,6 ± 0,3 %", "-0,9 ± 0,3 %", "-4,8 ± 0,3 %"]
    assert [UI.fmt_band(s, 1) for s in win] == ["+11,3 ± 1,2 %", "+7,9 ± 1,0 %", "+3,9 ± 1,4 %"]
    assert free[0].mean > 0 > free[2].mean and win[0].mean > win[1].mean > win[2].mean          # Reihenfolge kehrt sich um
    assert R.stat(DATA, "kein_fenster_lade90").neg_share == 1.0 and "in 100 % der Instanzen I < 0" in README


def test_range_amplifies_the_effect():
    r = [R.stat(DATA, n) for n in ("reich600", "basis", "reich300")]
    has("+2,7 ± 0,5 / +7,9 ± 1,0 / **+18,0 ± 2,0 %**")
    assert [UI.fmt_band(s) for s in r] == ["+2,7 ± 0,5 %", "+7,9 ± 1,0 %", "+18,0 ± 2,0 %"] and r[0].mean < r[1].mean < r[2].mean
    d = DATA["reich300"]
    has(f"nur {d['used']} von {d['instances']} Lagen auswertbar")


def test_window_tightness_fleet_size_and_calibration():
    has("+3,1 ± 0,8 / +7,9 ± 1,0 / +10,1 ± 1,6 %", "+4,3 ± 1,2 / +7,9 ± 1,0 / +6,0 ± 1,0 %", band("fenster_regelbewusst"))
    w = [R.stat(DATA, n) for n in ("fenster_locker", "basis", "fenster_eng")]
    assert [UI.fmt_band(s) for s in w] == ["+3,1 ± 0,8 %", "+7,9 ± 1,0 %", "+10,1 ± 1,6 %"]
    f = [R.stat(DATA, n) for n in ("fahrzeuge2", "basis", "fahrzeuge4")]
    assert [UI.fmt_band(s) for s in f] == ["+4,3 ± 1,2 %", "+7,9 ± 1,0 %", "+6,0 ± 1,0 %"]
    assert [(DATA[n]["n"], DATA[n]["K"]) for n in ("fahrzeuge2", "basis", "fahrzeuge4")] == [(12, 2), (18, 3), (24, 4)]
    assert R.stat(DATA, "fenster_regelbewusst").verdict() == "pos" and R.stat(DATA, "fenster_regelbewusst").neg_share == 0.0


def test_the_pattern_carries_to_the_live_size():
    has(band("live10_kein_fenster").replace("-", "−"), band("live10"))
    has("+1,4 ± 0,5 / −5,5 ± 0,5 %", "+3,0 ± 0,8 / +5,3 ± 1,2 / +12,6 ± 2,7 %")
    assert UI.fmt_band(R.stat(DATA, "live10_kein_fenster_lade20")) == "+1,4 ± 0,5 %" and UI.fmt_band(R.stat(DATA, "live10_kein_fenster_lade90")) == "-5,5 ± 0,5 %"
    assert [UI.fmt_band(R.stat(DATA, n)) for n in ("live10_reich600", "live10_reich400", "live10_reich300")] == ["+3,0 ± 0,8 %", "+5,3 ± 1,2 %", "+12,6 ± 2,7 %"]
    assert f"({DATA['live10_reich300']['used']} von {DATA['live10_reich300']['instances']} Lagen)" in README
    assert R.stat(DATA, "live10").verdict() == "pos" and R.stat(DATA, "live10_kein_fenster").verdict() == "neg"


def test_unpaid_pauses_keep_the_sign():
    un = {n: R.stat(DATA, n) for n in ("unbezahlt_kein_fenster", "unbezahlt_basis", "unbezahlt_kein_fenster_lade90", "unbezahlt_kein_fenster_lade20")}
    has("−2,9 ± 0,3 statt −0,9 %", "+5,5 ± 1,0 statt +7,9 %", "90 min: −7,0 ± 0,3 %, 20 min: +0,5 ± 0,3 %")
    assert UI.fmt_band(un["unbezahlt_kein_fenster"]) == "-2,9 ± 0,3 %" and UI.fmt_band(un["unbezahlt_basis"]) == "+5,5 ± 1,0 %"
    assert UI.fmt_band(un["unbezahlt_kein_fenster_lade90"]) == "-7,0 ± 0,3 %" and UI.fmt_band(un["unbezahlt_kein_fenster_lade20"]) == "+0,5 ± 0,3 %"
    assert un["unbezahlt_kein_fenster"].mean < R.stat(DATA, "kein_fenster").mean < 0 < un["unbezahlt_basis"].mean < R.stat(DATA, "basis").mean
    assert un["unbezahlt_kein_fenster_lade20"].verdict() == "none"


def test_the_penalty_scales_the_size_not_the_sign():
    p = DATA["_ap0_d_verspaetungsstrafe"]
    has("+4,6 ± 0,7 / +8,4 ± 1,2 / +16,4 ± 2,2 %")
    assert [UI.fmt_band(R.Stat.from_dict(p[k]["I"])) for k in ("20", "40", "80")] == ["+4,6 ± 0,7 %", "+8,4 ± 1,2 %", "+16,4 ± 2,2 %"]
    assert all(R.Stat.from_dict(p[k]["I"]).verdict() == "pos" for k in p)                                # Vorzeichen bleibt
    eur = [p[k]["I_eur"]["mean"] for k in ("20", "40", "80")]
    assert eur[1] / eur[0] == pytest.approx(1.8, abs=0.2) and eur[2] / eur[1] == pytest.approx(2.0, abs=0.3)     # fast linear
    assert all(p[k]["I_oper"]["mean"] < 2.0 for k in p) and "höchstens 2 %" in README


def test_re_evaluating_old_tours_overestimates():
    has("I = +18,9 ± 1,4 % statt +7,9 ± 1,0 %", "+12,8 ± 1,5 statt +6,4 ± 1,2 %")
    assert UI.fmt_band(R.stat_fix(DATA, "basis")) == "+18,9 ± 1,4 %" and UI.fmt_band(R.stat_fix(DATA, "live10")) == "+12,8 ± 1,5 %"
    assert R.stat_fix(DATA, "basis").mean > 2 * R.stat(DATA, "basis").mean and R.stat_fix(DATA, "live10").mean > 1.9 * R.stat(DATA, "live10").mean


def test_search_noise_gives_the_two_percent_threshold():
    g = DATA["_ap0_b_suchrauschen"]["gepoolt"]
    has(f"bei {g['nicht_null']} von {g['n']} verschieden", f"{num(g['abs_dI']['p95'])} % der regelfreien Kosten, Maximum {num(g['abs_dI']['max'])} %")
    has(f"Maximum des Unterschieds von I {num(g['abs_dI']['max'])} % der regelfreien Kosten")
    assert g["abs_dI"]["p95"] <= 2.1 and g["abs_dI"]["median"] == 0.0 and g["kippen_bei_2_prozent"]["seed1_vs_seed2"] == 1
    for name in ("live10", "live10_kein_fenster"):
        z = DATA["_ap0_b_suchrauschen"][name]
        assert all(v == z["n"] for v in z["andere_zellen_identisch"].values())                       # nur F+E rauscht
    has("Nur die Zelle F+E rauscht", "Meldungsschwelle von 2 %")


def test_message_states_on_single_instances():
    w, f = DATA["live10"]["states"], DATA["live10_kein_fenster"]["states"]
    has(f"mit Fenstern billiger {w['billiger'] * 100:.0f} % / praktisch additiv {w['additiv'] * 100:.0f} % / teurer {w['teurer'] * 100:.0f} %",
        f"ohne Fenster {f['billiger'] * 100:.0f} % / {f['additiv'] * 100:.0f} % / {f['teurer'] * 100:.0f} %")
    assert (round(w["billiger"] * 100), round(w["additiv"] * 100), round(w["teurer"] * 100)) == (20, 17, 63)
    assert (round(f["billiger"] * 100), round(f["additiv"] * 100), round(f["teurer"] * 100)) == (57, 30, 13)


def test_excluded_layouts_and_sizes_in_the_readme():
    has("28 von 40 (18/3) bzw. 29 von 40 Instanzen (10/2)", "3 von 40 Lagen")
    assert (DATA["reich300"]["used"], DATA["live10_reich300"]["used"]) == (28, 29)
    assert DATA["live10_reich300"]["excluded_reasons"]["suche_ohne_loesung"] == 3


def test_the_readme_names_every_test_it_refers_to_and_every_module():
    """Jeder im README genannte Test existiert in den Testdateien."""
    tests_dir = ROOT / "tests"
    sources = {p.name: p.read_text(encoding="utf-8") for p in tests_dir.glob("test_*.py")}
    for name in re.findall(r"`(?:test_claims\.py)?::(test_\w+)`", README):
        assert f"def {name}(" in sources["test_claims.py"], name
    for fname in re.findall(r"`(test_\w+\.py)", README):
        assert fname in sources, fname
    for path in re.findall(r"`((?:fv_|app|tools/|data/|tests/)[\w/.]*\.(?:py|json))`", README):
        assert (ROOT / path).exists(), path


def test_the_readme_states_the_honest_limits_and_the_neighbours():
    has("erfunden, nicht kalibriert", "Pausen zählen als bezahlte Fahrerzeit", "EU-Regeln vereinfacht", "Weiche Zeitfenster sind eine Modellwahl",
        "Die Tourensuche ist eine Heuristik", "Stafette nicht enthalten", "## Verwandte Demos mit demselben mathematischen Modell",
        "`vrp_demo`", "`linehaul-demo`", "`slow-steaming-demo`", "`leercontainer-demo`", "starr gegen reaktiv",
        "Stafette und Fahrerdienstplan", "Stand 2026-09-24", "(noch nicht deployed)", "## Reproduktion der Messreihe", "52 Minuten",
        "## Bewusst nicht umgesetzt", "## Lokal ausführen", "Gebaut mit Streamlit, Plotly und fpdf2.")
    for stripped in ("Energiepreis", "Ladeleistungskurve", "Unbezahlte Pausen als Regler", "Wochenruhe"):
        assert stripped in README
    assert "streamlit.app" not in README and "8675" not in README                                     # keine Deploy-Adresse, kein Port


def test_readme_uses_proper_umlauts():
    for wrong in ("Fuer ", "waehrend", "ueber ", "Loesung", "Aenderung", "ausserhalb"):
        assert wrong not in README, wrong
