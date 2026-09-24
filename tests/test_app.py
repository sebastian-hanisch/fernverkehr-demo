"""AppTest: Skelett und Footer, jedes Preset, Permalink, alle Regler an Min und Max, alle Meldungszustände, Kernabschnitt, Ansichten,
PDF, Texte. Die Live-Rechnung läuft in diesen Tests mit 6 Kunden (Fixture small_live: echter Code, nur kleiner); die Rechnung mit
den echten Kundenzahlen und ohne Ersatz steht in tests/test_app_real.py. Keine Wall-Clock-Assertions."""
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import fv_constants as C
import fv_live
import fv_results as R
from fv_presets import PRESET_STATE_KEYS, SETTING_SPECS
from live_cache import fresh_copy, get_live

pytestmark = pytest.mark.usefixtures("small_live")

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
DATA = R.load_results()
FOOTER = ("Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
          "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
          "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)")
LABELS = {"customers_slider": "Kunden", "charge_slider": "Typische Ladezeit", "range_slider": "Reichweite", "window_slider": "Zeitfenster"}


@pytest.fixture(autouse=True)
def clean_state():
    """st.cache_data ist prozessweit: Tests dürfen keine Ergebnisse anderer Tests sehen."""
    import streamlit as st
    st.cache_data.clear()
    yield


def fresh(**query):
    at = AppTest.from_file(APP, default_timeout=180)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def set_and_run(at, **values):
    for key, value in values.items():
        if key == "seed_input":
            at.number_input(key=key).set_value(value)
        elif key == "customers_slider":
            at.slider(key=key).set_value(value)
        else:
            at.select_slider(key=key).set_value(value)
    at.run()
    assert not at.exception, at.exception
    return at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, at.exception
    return at


def main_metrics(at):
    return [(m.label, m.value) for m in at.metric[:4]]


def box(at, kind, needle):
    for x in getattr(at, kind):
        if needle in x.value:
            return x.value
    return None


def any_box(at, needle):
    return next((v for k in ("success", "warning", "info", "error") for v in [box(at, k, needle)] if v), None)


# ---------------------------------------------------------------------------------------------------
# Skelett
# ---------------------------------------------------------------------------------------------------
def test_skeleton_and_footer():
    at = fresh()
    assert [h.value for h in at.sidebar.header] == ["⚙️ Einstellungen"]                   # genau EIN Header
    assert len(at.title) == 1 and "Fernverkehr" in at.title[0].value
    assert any(v.value.startswith("## 🚛 Was kosten Fahrerregeln und Elektro-Lkw") for v in at.markdown)
    assert any(v.value.startswith("### 📐 Was die Messreihe über 60 Instanzen zeigt") for v in at.markdown)
    assert [e.label for e in at.expander] == ["🔧 Wie wir das erreichen – Fahrplan-Evaluator und Tourensuche",
                                              "Wie funktioniert diese Demo?", "📐 Mathematische Formulierung"]
    assert any(c.value == FOOTER for c in at.caption)
    presets = [b.label for b in at.button if b.label in C.PRESETS]
    assert presets == list(C.PRESETS) and len(presets) == 5 and all(len(n) <= 32 for n in presets)
    assert [s.label for s in at.sidebar.slider] == ["Kunden"]
    assert [s.label for s in at.sidebar.select_slider] == ["Typische Ladezeit", "Reichweite", "Zeitfenster"]
    assert [n.label for n in at.sidebar.number_input] == ["Seed"]
    assert [b.label for b in at.sidebar.button] == ["🎲 Neue Instanz"]                     # letztes Sidebar-Element
    assert [type(e).__name__ for e in at.sidebar.children.values()][-1] == "Button"


def test_sidebar_has_no_second_header_or_subheader():
    at = fresh()
    assert len(at.sidebar.header) == 1 and len(at.sidebar.subheader) == 0


def test_there_are_no_switches_for_the_rules():
    """Die Live-Instanz rechnet immer alle vier Zellen: keine F- und E-Schalter, die ohne den anderen wirkungslos wären."""
    at = fresh()
    assert not at.sidebar.checkbox and not at.sidebar.toggle and not at.checkbox and not at.toggle
    labels = " ".join(w.label for w in list(at.sidebar.slider) + list(at.sidebar.select_slider))
    assert "Fahrerregeln" not in labels and "Elektro" not in labels and "Stafette" not in labels


def test_main_metrics_are_2x2_with_the_right_labels():
    at = fresh()
    assert [m[0] for m in main_metrics(at)] == ["Mehrkosten Fahrerregeln (F)", "Mehrkosten Elektro (E)", "Mehrkosten beides (F+E)", "Wechselwirkung I"]
    res = get_live(6, 45, 400, "mittel", C.SEED_DEFAULT)
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    values = dict(main_metrics(at))
    assert values["Mehrkosten Fahrerregeln (F)"] == f"{x['dF_pct']:+.1f} %".replace(".", ",")
    assert values["Wechselwirkung I"] == f"{x['I_pct']:+.1f} %".replace(".", ",")
    delta = {m.label: m.delta for m in at.metric[:4]}
    assert delta["Mehrkosten beides (F+E)"].startswith("Summe der Einzelnen") and delta["Wechselwirkung I"].endswith("EUR")


def test_charts_are_present_with_unique_keys():
    at = fresh()
    keys = [c.key for c in at.get("plotly_chart")]
    assert len(set(keys)) == len(keys) and all(keys)
    assert set(keys) == {"main_map", "main_timeline", "core_sum_chart", "core_axis_chart", "core_comp_chart", "core_pause_chart",
                         "core_penalty_chart", "tab_map_0", "tab_map_1", "tab_map_2", "tab_map_3", "tab_cost_live", "tab_fix_live"}


def test_pdf_download_button_is_offered():
    at = fresh()
    buttons = at.get("download_button")
    assert len(buttons) == 1 and buttons[0].proto.label == "📄 Fahrplan als PDF herunterladen"


def test_texts_state_the_model_the_honest_limits_and_the_neighbours():
    at = fresh()
    text = "\n".join(m.value for m in at.expander[1].markdown)
    for needle in ("vrp_demo", "Zeitfenster", "Fahrerregeln (F)", "Elektro (E)", "erfunden, nicht kalibriert", "Fahrplan-Evaluator", "Tourensuche",
                   "Wechselwirkung", "Heuristik", "Stark stilisiert", "bezahlte Fahrerzeit", "EU-Regeln vereinfacht", "Weiche Zeitfenster",
                   "Stafette", "Ausgeschlossene Lagen", "mehr als doppelt"):
        assert needle in text, needle
    math_text = "\n".join(m.value for m in at.expander[2].markdown)
    for needle in ("Label-Setting", "Tourenproblem", "Wechselwirkung", "2\\,\\text{SE}", "fv_evaluator.py", "fv_live.py"):
        assert needle in math_text, needle
    intro = at.markdown[0].value
    assert "vrp_demo" in intro and "Wie funktioniert diese Demo?" in intro and "📐 Mathematische Formulierung" in intro
    assert "slow-steaming-demo" in intro and "leercontainer-demo" in intro and "Lenk- und Ruhezeiten" in intro


def test_model_constants_in_the_texts_come_from_the_parameters():
    from fv_model import Cfg
    c = Cfg()
    text = "\n".join(m.value for m in fresh().expander[1].markdown)
    for needle in (f"{c.c_km:.2f} EUR je km", f"{c.c_drv:.0f} EUR je Stunde bezahlte Fahrerzeit", f"{c.c_night:.0f} EUR je Tagesruhe",
                   f"{c.c_late:.0f} EUR je Stunde Verspätung", f"{c.speed:.0f} km/h", "12 feste Ladesäulen"):
        assert needle in text, needle


def test_expander_tabs_are_named_as_planned():
    at = fresh()
    labels = [t.label for t in at.tabs]
    assert labels[:2] == ["Halteliste Lkw 1", "Halteliste Lkw 2"] or "Halteliste Lkw 1" in labels
    for tab in ("🗺️ Fahrplan", "📊 Kostenzerlegung", "🔁 Fest oder neu geplant", "📈 Messreihe"):
        assert tab in labels


def test_live_caption_names_the_instance_and_the_solution_time():
    at = fresh()
    cap = next(c.value for c in at.caption if c.value.startswith("Live-Instanz:"))
    assert "Ladezeit 45 min" in cap and "Reichweite 400 km" in cap and f"Instanz Nr. {C.SEED_DEFAULT}" in cap and "Seed " in cap
    assert "gerechnet in" in cap and "Eine einzelne Instanz" in cap


# ---------------------------------------------------------------------------------------------------
# Presets, Permalink
# ---------------------------------------------------------------------------------------------------
def _widget(at, key):
    if key == "seed_input":
        return at.number_input(key=key)
    return at.slider(key=key) if key == "customers_slider" else at.select_slider(key=key)


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_every_preset_loads_within_widget_bounds(name):
    at = fresh()
    click(at, name)
    preset = C.PRESETS[name]
    for field, key in PRESET_STATE_KEYS.items():
        assert _widget(at, key).value == preset[field], (name, field)
    assert at.get("download_button")
    assert any_box(at, "Messreihe") is not None                                        # eine der drei Meldungen ist da


def test_permalink_is_clamped_snapped_and_ignores_garbage():
    at = fresh(n="999", lt="30", r="abc", w="sehr eng", seed="99999", junk="ignored")
    assert at.slider(key="customers_slider").value == 12                                # geklemmt
    assert at.select_slider(key="charge_slider").value == 20                            # auf die nächste Stufe eingerastet (30 -> 20)
    assert at.select_slider(key="range_slider").value == C.RANGE_DEFAULT                # Müll ignoriert
    assert at.select_slider(key="window_slider").value == C.WINDOW_DEFAULT
    assert at.number_input(key="seed_input").value == C.SEED_RANGE[1]


def test_permalink_roundtrip_reflects_settings():
    at = fresh(n="8", lt="90", r="600", w="eng", seed="42")
    values = {k: at.session_state[k] for k in SETTING_SPECS}
    assert values == {"customers_slider": 8, "charge_slider": 90, "range_slider": 600, "window_slider": "eng", "seed_input": 42}
    for key, spec in SETTING_SPECS.items():
        got = at.query_params[spec.url_param]
        got = got[0] if isinstance(got, list) else got
        assert got == spec.encoder(at.session_state[key]), key


def test_new_instance_button_changes_only_the_seed_and_randomizes():
    at = fresh()
    before = {k: at.session_state[k] for k in SETTING_SPECS if k != "seed_input"}
    seeds = set()
    for _ in range(6):
        click(at, "🎲 Neue Instanz")
        seeds.add(at.session_state["seed_input"])
        assert C.SEED_RANGE[0] <= at.session_state["seed_input"] <= C.SEED_RANGE[1]
    assert len(seeds) > 1
    assert {k: at.session_state[k] for k in SETTING_SPECS if k != "seed_input"} == before


# ---------------------------------------------------------------------------------------------------
# Regler an den Grenzen
# ---------------------------------------------------------------------------------------------------
CONTROLS = [("customers_slider", C.CUSTOMERS_RANGE), ("charge_slider", C.CHARGE_OPTIONS), ("range_slider", C.RANGE_OPTIONS),
            ("window_slider", C.WINDOW_OPTIONS), ("seed_input", C.SEED_RANGE)]


@pytest.mark.parametrize("key,value", [(k, v) for k, opts in CONTROLS for v in (opts[0], opts[-1])])
def test_every_control_works_at_its_minimum_and_maximum(key, value):
    at = set_and_run(fresh(), **{key: value})
    assert at.session_state[key] == value and len(at.metric) >= 4 and not at.exception


@pytest.mark.parametrize("key,options", [("charge_slider", C.CHARGE_OPTIONS), ("range_slider", C.RANGE_OPTIONS), ("window_slider", C.WINDOW_OPTIONS)])
def test_every_step_of_the_step_controls_runs(key, options):
    for value in options:
        at = set_and_run(fresh(), **{key: value})
        assert at.session_state[key] == value and at.get("download_button")


def test_extreme_combinations_run_without_exception():
    fresh(n="6", lt="20", r="300", w="eng", seed="0")
    fresh(n="12", lt="90", r="600", w="keine", seed="299")
    fresh(n="6", lt="90", r="300", w="locker", seed="150")


@pytest.mark.parametrize("key,value", [("charge_slider", 20), ("charge_slider", 90), ("range_slider", 300), ("range_slider", 600),
                                       ("window_slider", "keine"), ("window_slider", "eng"), ("seed_input", 7)])
def test_no_control_is_dead_it_changes_the_shown_results(key, value):
    """Jeder Regler verändert die Hauptansicht (Kennzahlen); Ladezeit und Reichweite wirken, weil immer alle vier Zellen gerechnet werden."""
    base = main_metrics(fresh())
    assert main_metrics(set_and_run(fresh(), **{key: value})) != base, (key, value)


def test_charge_time_and_range_change_the_electric_cell_even_without_rules_switch():
    """E ist immer mitgerechnet: die Ladezeit wirkt auch in der Zelle E allein (Mehrkosten Elektro), die Reichweite ebenso."""
    e = lambda at: dict(main_metrics(at))["Mehrkosten Elektro (E)"]
    base = e(fresh())
    assert e(set_and_run(fresh(), charge_slider=90)) != base and e(set_and_run(fresh(), range_slider=300)) != base


def test_control_help_texts_are_present():
    at = fresh()
    for w in list(at.sidebar.slider) + list(at.sidebar.select_slider) + list(at.sidebar.number_input):
        assert w.help, w.label


# ---------------------------------------------------------------------------------------------------
# Bedingte Meldung: alle Zustände
# ---------------------------------------------------------------------------------------------------
def _fake(monkeypatch, base=1000.0, f=1400.0, e=1300.0, fe=1700.0, infeasible=()):
    def solve(n, charge, range_km, window, seed_index):
        res = fresh_copy(get_live(6, charge, range_km, window, seed_index))
        for c, v in zip(C.CELLS, (base, f, e, fe)):
            res["cells"][c]["total"] = v
        for c in infeasible:
            res["cells"][c].update(feasible=False, total=None, metrics=None, comps=None, trucks=[], fix_total=None)
        return res
    monkeypatch.setattr(fv_live, "solve_live", solve)


def test_message_state_cheaper(monkeypatch):
    _fake(monkeypatch, fe=1400.0 + 1300.0 - 1000.0 - 80.0)
    at = fresh()
    assert at.success and "Hier sparen Pause und Laden zusammen" in at.success[0].value and "80 EUR" in at.success[0].value
    assert dict(main_metrics(at))["Wechselwirkung I"] == "-8,0 %"


def test_message_state_additive(monkeypatch):
    _fake(monkeypatch, fe=1400.0 + 1300.0 - 1000.0 + 10.0)
    at = fresh()
    msg = any_box(at, "praktisch additiv")
    assert msg is not None and "+1,0 %" in msg and not at.success


def test_message_state_dearer_with_the_search_artifact_hint(monkeypatch):
    _fake(monkeypatch, fe=1400.0 + 1300.0 - 1000.0 + 120.0)
    at = fresh()
    msg = box(at, "warning", "teurer als die Summe der Einzelkosten")
    assert msg is not None and "Suchartefakt" in msg and "12,0 %" in msg


def test_message_state_infeasible_layout(monkeypatch):
    _fake(monkeypatch, infeasible=(C.CELL_E, C.CELL_FE))
    at = fresh()
    assert box(at, "warning", "keine zulässige Lösung") is not None
    assert [m[1] for m in main_metrics(at)] == ["–"] * 4
    assert at.get("download_button")                                                    # PDF geht auch dann


def test_each_state_message_is_exclusive(monkeypatch):
    needles = ["Hier sparen Pause und Laden zusammen", "Auf dieser Instanz praktisch additiv", "Hier ist die Kombination um",
               "keine zulässige Lösung, die Kennzahlen lassen sich nicht bilden"]
    results = {}
    for name, kw in (("billiger", dict(fe=1400 + 1300 - 1000 - 80.0)), ("additiv", dict(fe=1400 + 1300 - 1000 + 10.0)),
                     ("teurer", dict(fe=1400 + 1300 - 1000 + 120.0)), ("unzulaessig", dict(infeasible=(C.CELL_E,)))):
        import streamlit as st
        st.cache_data.clear()                                                            # sonst liefert der Cache das alte Ergebnis
        _fake(monkeypatch, **kw)
        at = fresh()
        hits = [n for n in needles if any_box(at, n) is not None]
        results[name] = hits
        assert len(hits) == 1, (name, hits)
    assert len({h[0] for h in results.values()}) == 4                                    # vier verschiedene Meldungen erreichbar


def test_dearer_message_is_a_warning_and_cheaper_message_a_success(monkeypatch):
    import streamlit as st
    _fake(monkeypatch, fe=1400.0 + 1300.0 - 1000.0 + 120.0)
    assert fresh().warning
    st.cache_data.clear()
    _fake(monkeypatch, fe=1400.0 + 1300.0 - 1000.0 - 80.0)
    assert fresh().success


# ---------------------------------------------------------------------------------------------------
# Kernabschnitt
# ---------------------------------------------------------------------------------------------------
def test_core_section_gives_the_verdict_of_the_measurement_series_for_the_settings():
    at = fresh()
    msg = any_box(at, "Urteil der Messreihe zu Ihren Einstellungen")
    assert msg is not None and "10 Kunden, 2 Lkw, 60 Instanzen" in msg and "18 Kunden, 3 Lkw, 60 Instanzen" in msg and "teurer als die Summe (belastbar)" in msg
    assert at.warning                                                                     # Standard: teurer -> Warnkasten
    assert "billiger als die Summe (belastbar)" in any_box(set_and_run(fresh(), charge_slider=90, window_slider="keine"), "Urteil der Messreihe")


def test_core_verdict_has_three_states():
    assert "teurer als die Summe (belastbar)" in any_box(fresh(), "Urteil der Messreihe")
    assert "billiger als die Summe (belastbar)" in any_box(fresh(lt="90", w="keine"), "Urteil der Messreihe")
    none = any_box(fresh(lt="45", w="keine", r="400"), "Urteil der Messreihe")
    assert none is not None and "billiger als die Summe (belastbar)" in none                # 18/3 ohne Fenster: -0,9 +- 0,3 (3,5 SE)
    assert fresh(lt="20", w="eng").info is not None


def test_core_verdict_names_the_missing_series():
    at = fresh(w="eng", lt="20")
    msg = any_box(at, "Für genau diese Einstellungen")
    assert msg is not None and "keine vorgerechnete Messreihe" in msg and "Ladezeit 20 min, Reichweite 400 km, Zeitfenster eng" in msg


def test_core_section_shows_both_sizes_in_the_sum_table():
    at = fresh()
    tables = [d.value for d in at.dataframe]
    sums = [t for t in tables if "Summe der Einzelnen" in t.columns]
    assert len(sums) == 1 and set(sums[0]["Größe"]) == {"10 Kunden, 2 Lkw", "18 Kunden, 3 Lkw"} and len(sums[0]) == 4


@pytest.mark.parametrize("axis", R.AXIS_NAMES)
def test_axis_selection_changes_table_and_chart(axis):
    at = fresh()
    at.selectbox(key="axis_select").set_value(axis).run()
    assert not at.exception, at.exception
    tables = [d.value for d in at.dataframe if "Median [Q1; Q3]" in d.value.columns and "Gruppe" in d.value.columns]
    assert len(tables) == 1 and len(tables[0]) == len(R.axis_rows(DATA, axis))
    assert set(tables[0]["Größe"]) >= {"18 Kunden, 3 Lkw"} or axis == "Fahrzeuge"


def test_axis_default_is_the_charge_time():
    assert fresh().selectbox(key="axis_select").value == "Ladezeit"


@pytest.mark.parametrize("window", ["mittel", "keine"])
def test_decomposition_radio_switches_between_the_two_series(window):
    at = fresh()
    at.radio(key="comp_window").set_value(window).run()
    assert not at.exception, at.exception
    assert "core_comp_chart" in [c.key for c in at.get("plotly_chart")]


def test_core_section_states_paid_pauses_penalty_and_the_excluded_layouts():
    at = fresh()
    caps = " ".join(c.value for c in at.caption)
    assert "Ausgeschlossen bei Reichweite 300 km" in caps and "28 von 40 Lagen auswertbar" in caps and "29 von 40 Lagen auswertbar" in caps
    assert "die Ausgeschlossenen" in caps or "schwierigeren Lagen" in caps
    assert "Pausen zählen in der Grundannahme als bezahlte Fahrerzeit" in caps
    assert "Rechenzeiten (gemessen, dieses Gerät)" in caps and "12 Kunden 9,0 und 10,7 s" in caps
    assert any(i.value.startswith("Wer die regelfreien Touren nur unter den Regeln neu bewertet") for i in at.info)


def test_assumption_tables_are_shown_with_verdicts():
    at = fresh()
    pause = [d.value for d in at.dataframe if "I, Pausen unbezahlt" in d.value.columns]
    strafe = [d.value for d in at.dataframe if "Verspätungsstrafe (18 Kunden, 3 Lkw, Zeitfenster mittel)" in d.value.columns]
    assert len(pause) == 1 and len(strafe) == 1 and len(strafe[0]) == 3 and len(pause[0]) == 4


# ---------------------------------------------------------------------------------------------------
# Ansichten
# ---------------------------------------------------------------------------------------------------
def test_view_select_offers_the_four_cells_and_defaults_to_both():
    at = fresh()
    radio = at.radio(key="view_select")
    assert list(radio.options) == [C.CELL_LABELS[c] for c in C.CELLS] and radio.value == "beides (F+E)"


@pytest.mark.parametrize("cell", C.CELLS)
def test_view_select_shows_the_chosen_cell_and_pdf_follows(cell):
    at = fresh()
    at.radio(key="view_select").set_value(C.CELL_LABELS[cell]).run()
    assert not at.exception, at.exception
    assert any(c.value.startswith(f"{C.CELL_LABELS[cell]}: ") for c in at.caption)
    res = get_live(6, 45, 400, "mittel", C.SEED_DEFAULT)
    tabs = [t.label for t in at.tabs if t.label.startswith("Halteliste")]
    assert tabs == [f"Halteliste Lkw {t['truck']}" for t in res["cells"][cell]["trucks"]]
    assert at.get("download_button")


def test_view_select_is_no_scenario_setting_and_stays_out_of_the_permalink():
    at = fresh()
    at.radio(key="view_select").set_value(C.CELL_LABELS[C.CELL_F]).run()
    assert set(at.query_params) == {spec.url_param for spec in SETTING_SPECS.values()}


def test_an_infeasible_view_cell_shows_a_warning_instead_of_a_schedule(monkeypatch):
    _fake(monkeypatch, infeasible=(C.CELL_E,))
    at = fresh()
    at.radio(key="view_select").set_value(C.CELL_LABELS[C.CELL_E]).run()
    assert not at.exception, at.exception
    assert box(at, "warning", "fand die Suche keine zulässige Lösung") is not None
    assert "main_map" not in [c.key for c in at.get("plotly_chart")]


def test_expander_tabs_show_costs_of_the_four_cells_and_the_measurement_overview():
    at = fresh()
    frames = [d.value for d in at.dataframe]
    live = [t for t in frames if "Pflichtpausen" in t.columns]
    assert len(live) == 1 and list(live[0]["Zelle"]) == [C.CELL_LABELS[c] for c in C.CELLS]
    comp = [t for t in frames if "Kostenart" in t.columns]
    assert len(comp) == 2 and sum("Wechselwirkung I" in t.columns for t in comp) == 1    # live und Messreihe
    overview = [t for t in frames if "Ladezeit" in t.columns and "Reichweite" in t.columns and "F+E" in t.columns]
    assert len(overview) == 1 and len(overview[0]) == 19
    fix = [t for t in frames if "I fest" in t.columns]
    assert len(fix) == 1 and len(fix[0]) == 4
