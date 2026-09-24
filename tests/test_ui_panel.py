"""Panel-Logik ohne Streamlit-Aufruf: Zahlenformate, die vier Meldungszustände samt Texten, Vergleichstabelle, passende Messreihen,
Tabellen des Kernabschnitts (Spalten und Werte gegen die Daten)."""
import pytest

import fv_constants as C
import fv_results as R
import fv_ui_panel as UI
from live_cache import fresh_copy, get_live

DATA = R.load_results()


# ---------------------------------------------------------------------------------------------------
# Zahlenformate
# ---------------------------------------------------------------------------------------------------
def test_number_formats_use_the_decimal_comma_and_explicit_signs():
    assert UI.fmt_num(3.14159, 2) == "3,14" and UI.fmt_num(2.0, 1, True) == "+2,0" and UI.fmt_num(-2.04, 1, True) == "-2,0"
    assert UI.fmt_pct(7.92, 1, True) == "+7,9 %" and UI.fmt_pct(-0.9) == "-0,9 %" and UI.fmt_pct(12.0, 0) == "12 %"
    assert UI.fmt_eur(1234.4) == "1.234 EUR" and UI.fmt_eur(-127.0, True) == "-127 EUR" and UI.fmt_eur(50.0, True) == "+50 EUR"
    assert UI.fmt_eur(1234567.0) == "1.234.567 EUR"
    assert UI.fmt_share(0.567) == "57 %" and UI.fmt_share(0.0) == "0 %" and UI.fmt_share(1.0) == "100 %"
    assert UI.fmt_band(R.Stat(n=60, mean=7.92, se=0.99)) == "+7,9 ± 1,0 %" and UI.fmt_band(R.Stat(n=1, mean=-4.78, se=0.33), 2) == "-4,78 ± 0,33 %"


def test_cell_labels_map_back_to_cells():
    for cell, label in C.CELL_LABELS.items():
        assert UI.cell_from_label(label) == cell
    with pytest.raises(KeyError):
        UI.cell_from_label("gibt es nicht")


# ---------------------------------------------------------------------------------------------------
# Meldung in drei Zuständen (plus unzulässig)
# ---------------------------------------------------------------------------------------------------
def _with_costs(base=1000.0, f=1400.0, e=1300.0, fe=1700.0):
    """Echtes Ergebnis mit künstlich gesetzten Kosten: I = fe - f - e + base (EUR), in % von base."""
    res = fresh_copy(get_live())
    for c, v in zip(C.CELLS, (base, f, e, fe)):
        res["cells"][c]["total"] = v
    return res, R.interaction_from_costs(dict(zip(C.CELLS, (base, f, e, fe))))


def test_message_cheaper_than_the_sum_is_a_success_with_the_saving_in_eur_and_percent():
    res, x = _with_costs(fe=1400.0 + 1300.0 - 1000.0 - 80.0)                       # I = -80 EUR = -8 %
    state, text = UI.message(res, x, DATA)
    assert state == "billiger" and text.startswith("✅") and "80 EUR" in text and "8,0 %" in text and "billiger als die Summe" in text
    assert "belastbar" in text and "nie zu billig" in text


def test_message_additive_lies_within_two_percent():
    res, x = _with_costs(fe=1400.0 + 1300.0 - 1000.0 + 15.0)                        # I = +1,5 %
    state, text = UI.message(res, x, DATA)
    assert state == "additiv" and text.startswith("ℹ️") and "+1,5 %" in text and "±2 %" in text and "addieren" in text


def test_message_dearer_than_the_sum_warns_about_a_possible_search_artifact():
    res, x = _with_costs(fe=1400.0 + 1300.0 - 1000.0 + 90.0)                        # I = +9 %
    state, text = UI.message(res, x, DATA)
    noise = DATA["_ap0_b_suchrauschen"]["live10"]["best_of_6"]["gap"]
    assert state == "teurer" and text.startswith("⚠️") and "90 EUR" in text and "9,0 %" in text
    assert "Suchartefakt" in text and "nie zu billig" in text
    assert UI.fmt_num(noise["mean"]) in text and UI.fmt_num(noise["max"]) in text


@pytest.mark.parametrize("delta,state", [(-20.1, "billiger"), (-20.0, "additiv"), (0.0, "additiv"), (20.0, "additiv"), (20.1, "teurer")])
def test_message_state_switches_exactly_at_two_percent(delta, state):
    res, x = _with_costs(fe=1700.0 + delta)
    assert UI.message(res, x, DATA)[0] == state


def test_message_names_the_measurement_series_of_the_same_settings():
    res, x = _with_costs(fe=1790.0)
    text = UI.message(res, x, DATA)[1]
    s = DATA["live10"]
    assert "10 Kunden, 2 Lkw, 60 Instanzen" in text and UI.fmt_band(R.Stat.from_dict(s["I"])) in text
    assert f"{100 * s['states']['billiger']:.0f} % „billiger“" in text and f"{100 * s['states']['teurer']:.0f} % „teurer“" in text


def test_message_without_a_series_in_this_size_says_so():
    res = fresh_copy(get_live(6, 45, 400, "eng", 3))
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    assert "keine vorgerechnete Messreihe" in UI.message(res, x, DATA)[1]


def test_message_for_an_infeasible_layout_explains_and_gives_the_measurement_frequency():
    res = get_live(6, 45, 300, "keine", 10)
    assert UI.live_costs(res) is None and UI.infeasible_cells(res) == [C.CELL_E, C.CELL_FE]
    state, text = UI.message(res, None, DATA)
    assert state == "unzulaessig" and "keine zulässige Lösung" in text and "Elektro (E), beides (F+E)" in text
    assert "3 von 40 Lagen" in text and "300 km" in text and "anderen Seed" in text


def test_excluded_sentence_is_taken_from_the_data():
    assert UI.excluded_sentence(DATA) == ("In der Messreihe (Reichweite 300 km, 10 Kunden, 2 Lkw) kam das bei 3 von 40 Lagen vor; "
                                          "solche Lagen sind dort ausgeschlossen.")


def test_live_costs_needs_all_four_cells():
    assert set(UI.live_costs(get_live())) == set(C.CELLS)


# ---------------------------------------------------------------------------------------------------
# Passende Messreihen, Vergleichstabelle
# ---------------------------------------------------------------------------------------------------
def test_matching_series_lists_live_size_ten_two_and_main_series_without_duplicates():
    res = get_live()                                                              # 6 Kunden: nur die zwei Standardgrößen
    assert UI.matching_series(res, DATA) == ["live10", "basis"]
    res12 = fresh_copy(res)
    res12["n"] = 12
    assert UI.matching_series(res12, DATA) == ["fahrzeuge2", "live10", "basis"]        # 12 Kunden, 2 Lkw: eigene Reihe
    res10 = fresh_copy(res)
    res10["n"] = 10
    assert UI.matching_series(res10, DATA) == ["live10", "basis"]
    eng = get_live(6, 45, 400, "eng", 3)
    assert UI.matching_series(eng, DATA) == ["fenster_eng"]


def test_comparison_table_has_live_and_series_columns_with_size_and_count():
    res = get_live()
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    df = UI.comparison_table(res, x, DATA)
    assert list(df["Kennzahl"]) == ["Mehrkosten Fahrerregeln (F)", "Mehrkosten Elektro (E)", "Mehrkosten beides (F+E)", "Wechselwirkung I"]
    assert list(df.columns) == ["Kennzahl", "Live-Instanz (6 Kunden, 2 Lkw, 1 Instanz)", "10 Kunden, 2 Lkw, 60 Instanzen",
                                "18 Kunden, 3 Lkw, 60 Instanzen"]
    live = df["Live-Instanz (6 Kunden, 2 Lkw, 1 Instanz)"]
    assert live.iloc[0] == UI.fmt_pct(x["dF_pct"], signed=True) and live.iloc[3] == UI.fmt_pct(x["I_pct"], signed=True)
    assert df["18 Kunden, 3 Lkw, 60 Instanzen"].iloc[3] == "+7,9 ± 1,0 %" and df["10 Kunden, 2 Lkw, 60 Instanzen"].iloc[3] == "+6,4 ± 1,2 %"


def test_comparison_table_with_an_infeasible_layout_shows_dashes():
    res = get_live(6, 45, 300, "keine", 10)
    df = UI.comparison_table(res, None, DATA)
    assert set(df.iloc[:, 1]) == {"–"} and list(df.columns) == ["Kennzahl", "Live-Instanz (6 Kunden, 2 Lkw, 1 Instanz)"]


def test_comparison_table_without_a_live_size_series_has_only_the_main_series_column():
    res = get_live(6, 45, 400, "eng", 3)
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    assert list(UI.comparison_table(res, x, DATA).columns) == ["Kennzahl", "Live-Instanz (6 Kunden, 2 Lkw, 1 Instanz)", "18 Kunden, 3 Lkw, 40 Instanzen"]


# ---------------------------------------------------------------------------------------------------
# Tabellen des Kernabschnitts
# ---------------------------------------------------------------------------------------------------
def test_sum_table_shows_the_sum_next_to_the_measured_combination():
    df = UI.sum_table(DATA)
    assert list(df.columns) == ["Größe", "Zeitfenster", "Instanzen", "Fahrerregeln allein", "Elektro allein", "Summe der Einzelnen",
                                "beides, gemessen", "Wechselwirkung I", "Urteil"]
    row = df.iloc[3]
    assert row["Größe"] == "18 Kunden, 3 Lkw" and row["Zeitfenster"] == "Zeitfenster mittel" and row["Instanzen"] == "60 Instanzen"
    assert row["Fahrerregeln allein"] == "+39,7 ± 1,1 %" and row["Elektro allein"] == "+21,9 ± 0,6 %" and row["beides, gemessen"] == "+69,5 ± 2,1 %"
    assert row["Summe der Einzelnen"] == "+61,6 %" and row["Urteil"] == "teurer als die Summe"
    assert df.iloc[2]["Urteil"] == "billiger als die Summe"                                   # 18/3 ohne Fenster


@pytest.mark.parametrize("axis", R.AXIS_NAMES)
def test_axis_table_has_one_row_per_series_with_median_quartiles_share_and_verdict(axis):
    rows = R.axis_rows(DATA, axis)
    df = UI.axis_table(rows)
    assert len(df) == len(rows)
    assert list(df.columns) == ["Gruppe", "Stufe", "Größe", "Instanzen", "Wechselwirkung I", "Median [Q1; Q3]", "Anteil I < 0", "Urteil"]
    assert set(df["Urteil"]) <= set(R.VERDICT_SHORT.values())
    assert all("[" in v and ";" in v for v in df["Median [Q1; Q3]"]) and all(v.endswith(" %") for v in df["Anteil I < 0"])


def test_axis_table_marks_excluded_layouts_in_the_count():
    df = UI.axis_table(R.axis_rows(DATA, "Reichweite"))
    assert "28 von 40 Instanzen" in set(df["Instanzen"]) and "29 von 40 Instanzen" in set(df["Instanzen"])


def test_fix_table_compares_fixed_and_replanned_tours():
    df = UI.fix_table(DATA)
    assert len(df) == 4 and set(df["Größe"]) == {"10 Kunden, 2 Lkw", "18 Kunden, 3 Lkw"}
    row = df[(df["Größe"] == "18 Kunden, 3 Lkw") & (df["Zeitfenster"] == "Zeitfenster mittel")].iloc[0]
    assert row["I fest"] == "+18,9 ± 1,4 %" and row["I neu geplant"] == "+7,9 ± 1,0 %"
    assert row["F fest / neu"] == "+51,4 % / +39,7 %" and row["F+E fest / neu"] == "+95,8 % / +69,5 %"


def test_pause_and_penalty_tables_show_the_assumption_sensitivities():
    p = UI.pause_table(DATA)
    assert len(p) == 4 and p.iloc[0]["I, Pausen bezahlt"] == "-0,9 ± 0,3 %" and p.iloc[0]["I, Pausen unbezahlt"] == "-2,9 ± 0,3 %"
    assert p.iloc[1]["I, Pausen unbezahlt"] == "+5,5 ± 1,0 %" and p.iloc[2]["Urteil unbezahlt"] == "nicht von additiv unterscheidbar"
    q = UI.penalty_table(DATA)
    assert list(q.iloc[:, 0])[1].endswith("(Grundannahme)") and len(q) == 3
    assert list(q["Wechselwirkung I"]) == ["+4,6 ± 0,7 %", "+8,4 ± 1,2 %", "+16,4 ± 2,2 %"]
    assert set(q["Urteil"]) == {"teurer als die Summe"}


def test_mechanism_and_components_tables():
    m = UI.mechanism_table(DATA)
    assert len(m) == 4 and "63 %" in m.iloc[0]["davon an einer Ladesäule"]
    c = UI.comps_I_table(DATA)
    assert list(c["Kostenart"]) == [C.COST_LABELS[k] for k in C.COST_KEYS]
    assert c.iloc[1]["18 Kunden, 3 Lkw, ohne Zeitfenster"] == "-153 ± 7 EUR" and c.iloc[4]["18 Kunden, 3 Lkw, Zeitfenster mittel"].startswith("+398")


def test_measured_overview_lists_the_plain_series_only():
    df = UI.measured_overview(DATA)
    assert len(df) == 19                                                                 # 26 minus 4 unbezahlt, 2 Strafe, 1 Regelplan
    assert set(df["Reichweite"]) == {"300 km", "400 km", "600 km"}
    assert "28 von 40 Instanzen" in set(df["Instanzen"]) and set(df["Ladezeit"]) == {"20 min", "45 min", "90 min"}
    assert list(df.columns)[:5] == ["Größe", "Zeitfenster", "Ladezeit", "Reichweite", "Instanzen"]


def test_live_tables_of_the_expander():
    res = get_live()
    costs = UI.cost_component_table(res)
    assert list(costs.columns) == ["Kostenart"] + [C.CELL_LABELS[c] for c in C.CELLS] + ["Wechselwirkung I"]
    assert list(costs["Kostenart"]) == [C.COST_LABELS[k] for k in C.COST_KEYS]
    live = UI.live_cost_table(res)
    assert list(live["Zelle"]) == [C.CELL_LABELS[c] for c in C.CELLS] and live.iloc[0]["Pflichtpausen"] == 0
    bad = UI.live_cost_table(get_live(6, 45, 300, "keine", 10))
    assert bad.iloc[2]["Kosten"] == "keine zulässige Lösung"


def test_halteliste_frame_and_summary_line():
    res = get_live()
    t = res["cells"][C.CELL_FE]["trucks"][0]
    df = UI.halteliste_frame(t["events"], res["n"])
    assert list(df.columns) == ["Von", "Bis", "Ort", "Ereignis", "Einzelheit", "Dauer"] and len(df) == len(t["events"])
    assert df.iloc[0]["Von"] == "Tag 1, 00:00" and df.iloc[-1]["Ort"] == "unterwegs nach Depot"
    line = UI.cell_summary_line(res, C.CELL_FE)
    assert line.startswith("beides (F+E): ") and " EUR, " in line and "Pausen" in line and "Tagesruhen" in line and "Ladehalte" in line
