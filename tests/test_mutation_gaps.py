"""Testlücken, die der Fehler-Einbau-Test (tools/mutation_check.py) gefunden hat, und die Tests, die sie schließen: jede Prüfung
hier ließ mindestens einen eingebauten Fehler überleben, bevor sie geschrieben wurde. Geordnet nach Modul."""
import copy

import pytest

import fv_constants as C
import fv_results as R
import fv_schedule as S
import fv_visualization as V
from live_cache import get_live

DATA = R.load_results()
N = 6


# ---------------------------------------------------------------------------------------------------
# fv_results: find_series und Achsen
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,window", [("fenster_regelbewusst", "mittel"), ("unbezahlt_basis", "mittel"), ("strafe20", "mittel"),
                                         ("strafe80", "mittel"), ("unbezahlt_kein_fenster", "keine"), ("unbezahlt_kein_fenster_lade90", "keine")])
def test_sensitivity_runs_are_never_offered_as_the_series_of_a_setting(name, window):
    """Nur die Reihe allein zur Auswahl (kein 'mehr Instanzen'-Vorrang einer anderen): Fenster nach Regelplan, unbezahlte Pausen und
    andere Verspätungsstrafen sind Annahmen-Vergleiche, keine Reihe zu einer Reglerstellung."""
    s = DATA[name]
    charge = int(s["overrides"].get("t_typ", 45.0))
    assert R.find_series({name: s}, s["n"], s["K"], window, charge, 400) is None


def test_find_series_matches_range_charge_and_window_width_exactly():
    reich = {"reich300": DATA["reich300"]}
    assert R.find_series(reich, 18, 3, "mittel", 45, 300) == "reich300" and R.find_series(reich, 18, 3, "mittel", 45, 400) is None
    assert R.find_series(reich, 18, 3, "mittel", 45, 600) is None
    lade = {"lade90": DATA["lade90"]}
    assert R.find_series(lade, 18, 3, "mittel", 90, 400) == "lade90" and R.find_series(lade, 18, 3, "mittel", 45, 400) is None
    wide = copy.deepcopy(DATA["basis"])
    wide["tw_width_h"] = 12.0                                                              # mittel = 8 h Breite
    assert R.find_series({"basis": wide}, 18, 3, "mittel", 45, 400) is None
    assert R.find_series({"basis": DATA["basis"]}, 18, 3, "mittel", 45, 400) == "basis"
    assert R.find_series({"basis": DATA["basis"]}, 18, 3, "eng", 45, 400) is None
    assert R.find_series({"basis": DATA["basis"]}, 18, 2, "mittel", 45, 400) is None
    no_window = copy.deepcopy(DATA["kein_fenster"])
    no_window["tw_width_h"] = 3.0                                                          # ohne Fenster ist die Breite gleichgültig
    assert R.find_series({"kein_fenster": no_window}, 18, 3, "keine", 45, 400) == "kein_fenster"


def test_axes_list_exactly_the_planned_series():
    expected = {
        "Ladezeit": [("ohne Zeitfenster", "20 min", "live10_kein_fenster_lade20"), ("ohne Zeitfenster", "20 min", "kein_fenster_lade20"),
                     ("ohne Zeitfenster", "45 min", "live10_kein_fenster"), ("ohne Zeitfenster", "45 min", "kein_fenster"),
                     ("ohne Zeitfenster", "90 min", "live10_kein_fenster_lade90"), ("ohne Zeitfenster", "90 min", "kein_fenster_lade90"),
                     ("Zeitfenster mittel", "20 min", "lade20"), ("Zeitfenster mittel", "45 min", "live10"),
                     ("Zeitfenster mittel", "45 min", "basis"), ("Zeitfenster mittel", "90 min", "lade90")],
        "Reichweite": [("Zeitfenster mittel", "300 km", "live10_reich300"), ("Zeitfenster mittel", "300 km", "reich300"),
                       ("Zeitfenster mittel", "400 km", "live10_reich400"), ("Zeitfenster mittel", "400 km", "basis"),
                       ("Zeitfenster mittel", "600 km", "live10_reich600"), ("Zeitfenster mittel", "600 km", "reich600")],
        "Zeitfenster": [("Ladezeit 45 min", "keine", "live10_kein_fenster"), ("Ladezeit 45 min", "keine", "kein_fenster"),
                        ("Ladezeit 45 min", "locker", "fenster_locker"), ("Ladezeit 45 min", "mittel", "live10"),
                        ("Ladezeit 45 min", "mittel", "basis"), ("Ladezeit 45 min", "eng", "fenster_eng")],
        "Fahrzeuge": [("Zeitfenster mittel", "2 Lkw", "fahrzeuge2"), ("Zeitfenster mittel", "3 Lkw", "basis"),
                      ("Zeitfenster mittel", "4 Lkw", "fahrzeuge4")],
    }
    for axis, rows in expected.items():
        assert [(r["group"], r["level"], r["series"]) for r in R.axis_rows(DATA, axis)] == rows, axis
    assert [(r["series"], r["window"]) for r in R.sum_rows(DATA)] == [("live10_kein_fenster", "ohne Zeitfenster"), ("live10", "Zeitfenster mittel"),
                                                                       ("kein_fenster", "ohne Zeitfenster"), ("basis", "Zeitfenster mittel")]
    reich = {(r["level"], r["size"]): r["stat"].mean for r in R.axis_rows(DATA, "Reichweite")}
    assert reich[("400 km", "10/2")] == pytest.approx(5.34, abs=0.01)                    # die 40-Instanzen-Reihe, nicht die 60 von live10


def test_excluded_series_are_only_those_with_excluded_instances():
    keep = R.series_names(DATA)
    assert {e["series"] for e in R.excluded_series(DATA)} == {n for n in keep if DATA[n]["excluded"]}


# ---------------------------------------------------------------------------------------------------
# fv_stories
# ---------------------------------------------------------------------------------------------------
def test_standard_operating_share_needs_a_positive_interaction_first():
    """Ein negatives Gesamt-I mit noch negativerem Betriebs-I erfüllt 'höchstens 40 %' rechnerisch, ist aber keine Überadditivität."""
    import fv_stories as ST
    d = copy.deepcopy({k: DATA[k] for k in ("basis", "live10")})
    d["basis"]["I"].update(mean=-10.0)
    d["basis"]["I_oper"].update(mean=-20.0)
    d["live10"]["I"].update(mean=-8.0)
    d["live10"]["I_oper"].update(mean=-9.0)
    ok = [x for x, _ in ST.criteria("Standard", d)]
    assert not ok[1] and not ok[3]


# ---------------------------------------------------------------------------------------------------
# fv_presets: Zustand und Adresszeile ohne laufende App
# ---------------------------------------------------------------------------------------------------
@pytest.fixture
def fake_streamlit(monkeypatch):
    import fv_presets
    state, params = {}, {}
    monkeypatch.setattr(fv_presets.st, "session_state", state, raising=False)
    monkeypatch.setattr(fv_presets.st, "query_params", params, raising=False)
    return state, params


def test_apply_preset_sets_every_widget_state_from_the_named_preset(fake_streamlit):
    from fv_presets import PRESET_STATE_KEYS, apply_preset
    state, _ = fake_streamlit
    for name, p in C.PRESETS.items():
        apply_preset(name)
        assert {k: state[k] for k in PRESET_STATE_KEYS.values()} == {PRESET_STATE_KEYS[f]: p[f] for f in PRESET_STATE_KEYS}, name
    apply_preset("Lange Ladung")
    assert state["charge_slider"] == 90 and state["window_slider"] == "keine"


def test_random_seed_covers_the_whole_slider_range(fake_streamlit, monkeypatch):
    import fv_presets
    from fv_presets import randomize_seed
    state, _ = fake_streamlit
    seen = []
    monkeypatch.setattr(fv_presets.random, "randint", lambda a, b: seen.append((a, b)) or b)
    randomize_seed()
    assert seen == [C.SEED_RANGE] and state["seed_input"] == C.SEED_RANGE[1]
    monkeypatch.setattr(fv_presets.random, "randint", lambda a, b: a)
    randomize_seed()
    assert state["seed_input"] == C.SEED_RANGE[0]


def test_defaults_permalink_and_query_sync_without_the_app(fake_streamlit):
    from fv_presets import SETTING_SPECS, init_session_state_defaults, load_permalink_settings, sync_query_params
    state, params = fake_streamlit
    params.update(n="99", lt="40", w="eng", junk="x")
    load_permalink_settings()
    assert state["customers_slider"] == 12 and state["charge_slider"] == 45 and state["window_slider"] == "eng" and state["permalink_loaded"]
    params["n"] = "7"
    load_permalink_settings()                                                              # nur beim ersten Aufruf
    assert state["customers_slider"] == 12
    init_session_state_defaults()
    assert state["customers_slider"] == 12 and state["range_slider"] == C.RANGE_DEFAULT and state["seed_input"] == C.SEED_DEFAULT
    sync_query_params({k: state[k] for k in SETTING_SPECS})
    assert params["n"] == "12" and params["lt"] == "45" and params["w"] == "eng" and params["seed"] == str(C.SEED_DEFAULT) and params["r"] == "400"


# ---------------------------------------------------------------------------------------------------
# fv_schedule, fv_visualization, fv_pdf_export
# ---------------------------------------------------------------------------------------------------
def test_a_sub_minute_lateness_is_reported_rounded_not_hidden():
    rows = S.halteliste([("serve", 0.0, 30.0, 3, 0.6), ("serve", 30.0, 60.0, 4, 1e-12)], N)
    assert rows[0]["einzelheit"] == "1 min verspätet" and rows[1]["einzelheit"] == "pünktlich"


def test_timeline_bars_end_where_the_events_end():
    """Balkenlänge = Dauer des Ereignisses: Beginn + Länge ist das Ende (Stunden seit Abfahrt)."""
    res = get_live()
    fig = V.timeline_figure(res, C.CELL_FE)
    ends = sorted(round(b + x, 6) for tr in fig.data for b, x in zip(tr.base, tr.x))
    expected = sorted(round(bar["t1"], 6) for t in res["cells"][C.CELL_FE]["trucks"] for bar in S.bars(t["events"], res["n"]))
    assert ends == expected
    assert all(x > 0 for tr in fig.data for x in tr.x)


def test_pdf_table_shows_extra_costs_event_counts_and_the_sum_of_the_singles():
    from test_pdf_export import _pdf, _plain
    res = get_live()
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    text = _plain(_pdf(res, C.CELL_FE, compress=False))
    fe = res["cells"][C.CELL_FE]["metrics"]
    base = res["cells"][C.CELL_BASE]["total"]
    for cell in (C.CELL_F, C.CELL_E, C.CELL_FE):
        pct = 100 * (res["cells"][cell]["total"] - base) / base
        assert f"{pct:+.1f} %".replace(".", ",") in text                                   # Mehrkosten je Zelle in Prozent der regelfreien Kosten
    assert f"{fe['breaks']}/{fe['nights']}/{fe['charges']}" in text                       # Pausen/Ruhen/Laden in der Reihenfolge der Überschrift
    assert f"{x['dF_pct'] + x['dE_pct']:+.1f} %".replace(".", ",") in text and "Summe der Einzel-Mehrkosten" in text


# ---------------------------------------------------------------------------------------------------
# fv_ui_panel: die Texte der Meldung im Wortlaut
# ---------------------------------------------------------------------------------------------------
def _with_costs(fe):
    import fv_ui_panel as UI
    from live_cache import fresh_copy
    res = fresh_copy(get_live())
    costs = dict(zip(C.CELLS, (1000.0, 1400.0, 1300.0, fe)))
    for c, v in costs.items():
        res["cells"][c]["total"] = v
    return UI, res, R.interaction_from_costs(costs)


def test_message_wording_puts_the_saving_as_a_positive_amount_and_the_dearer_amount_too():
    UI, res, x = _with_costs(1700.0 - 80.0)
    text = UI.message(res, x, DATA)[1]
    assert "die Kombination ist um 80 EUR (8,0 % der regelfreien Kosten) billiger" in text and "-80" not in text
    assert "nie zu billig" in text and "nur zu teuer finden kann" in text
    UI, res, x = _with_costs(1700.0 + 90.0)
    text = UI.message(res, x, DATA)[1]
    assert "die Kombination um 90 EUR (9,0 % der regelfreien Kosten) teurer" in text and "nur zu teuer finden und nie zu billig" not in text
    assert "kann die Kombination nur zu teuer finden, nie zu billig" in text


def test_message_search_noise_numbers_come_from_the_live_size_with_windows():
    UI, res, x = _with_costs(1790.0)
    gap = DATA["_ap0_b_suchrauschen"]["live10"]["best_of_6"]["gap"]
    other = DATA["_ap0_b_suchrauschen"]["live10_kein_fenster"]["best_of_6"]["gap"]
    text = UI.message(res, x, DATA)[1]
    assert f"im Mittel {UI.fmt_num(gap['mean'])} Prozentpunkte" in text and f"im Einzelfall bis {UI.fmt_num(gap['max'])}" in text
    assert gap["max"] != other["max"]


def test_series_verdict_box_kind_follows_the_verdict_and_prefers_the_live_size(monkeypatch):
    """Kasten des Kernabschnitts: billiger -> success, teurer -> warning, sonst info; er folgt der Reihe in Live-Größe (10/2)."""
    import fv_ui_panel as UI
    kinds = []
    for kind in ("success", "warning", "info"):
        monkeypatch.setattr(UI.st, kind, lambda text, k=kind: kinds.append(k))
    res = get_live(6, 90, 400, "keine", 3)                       # 10/2: billiger, 18/3: billiger
    assert UI.render_series_verdict(res, DATA) == "neg" and kinds == ["success"]
    kinds.clear()
    data = copy.deepcopy(DATA)
    data["live10_kein_fenster_lade90"]["I"]["mean"] = 0.0         # nur die 10/2-Reihe kippt auf "nicht unterscheidbar": sie führt
    assert UI.render_series_verdict(res, data) == "none" and kinds == ["info"]
    kinds.clear()
    assert UI.render_series_verdict(get_live(6, 45, 400, "mittel", 3), DATA) == "pos" and kinds == ["warning"]


def test_series_verdict_lists_every_matching_series_with_size_and_count():
    import fv_ui_panel as UI
    shown = []
    import streamlit as st
    orig = st.warning
    st.warning = lambda text: shown.append(text)
    try:
        UI.render_series_verdict(get_live(), DATA)
    finally:
        st.warning = orig
    assert "- 10 Kunden, 2 Lkw, 60 Instanzen: I = +6,4 ± 1,2 % – teurer als die Summe (belastbar)" in shown[0]
    assert "- 18 Kunden, 3 Lkw, 60 Instanzen: I = +7,9 ± 1,0 % – teurer als die Summe (belastbar)" in shown[0]
    assert "Ladezeit 45 min, Reichweite 400 km, Zeitfenster mittel" in shown[0]


def test_expander_cost_table_shows_the_interaction_per_cost_type_summing_to_the_total():
    import fv_ui_panel as UI
    res = get_live()
    df = UI.cost_component_table(res)
    cells = res["cells"]
    total = 0.0
    for key, (_, row) in zip(C.COST_KEYS, df.iterrows()):
        c = {name: cells[name]["comps"][key] for name in C.CELLS}
        i = c[C.CELL_FE] - c[C.CELL_F] - c[C.CELL_E] + c[C.CELL_BASE]
        total += i
        assert row["Wechselwirkung I"] == UI.fmt_eur(i, signed=True), key
    x = R.interaction_from_costs({name: cells[name]["total"] for name in C.CELLS})
    assert total == pytest.approx(x["I_eur"], abs=1e-6)                                   # die Zerlegung der Wechselwirkung schließt


def test_first_fit_decreasing_accepts_an_exactly_full_packing():
    """Kapazitätsgrenze: zwei Kunden mit je 5 passen genau in Q = 10 (Gleichheit ist zulässig), nicht in Q = 9."""
    from fv_model import _ffd_ok
    assert _ffd_ok([5, 5], 1, 10) and not _ffd_ok([5, 5], 1, 9) and _ffd_ok([5, 5], 2, 5) and not _ffd_ok([6, 5], 2, 5)
