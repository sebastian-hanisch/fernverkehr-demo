"""
Fernverkehr: Fahrerregeln und Elektro-Lkw in der Tourenplanung - interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Erweiterung der Tourenplanungs-Demo (vrp_demo): Das Basismodell (CVRP mit Zeitfenstern) bleibt, neu ist eine Ressourcenschicht
entlang der Route (Lenkzeit-Zähler, Akkustand), die aus jeder Stoppfolge einen Fahrplan mit Pausen, Ruhezeiten und Ladestopps macht.
Live: eine kleine Instanz (6 bis 12 Kunden, 2 Lkw), immer vier Zellen gerechnet (ohne Regeln, Fahrerregeln, Elektro, beides).
Vorgerechnet: die Messreihe über je 60 gepaarte Instanzen (data/fv_results.json), die die Aussage über die Wechselwirkung trägt.

Lauffähig mit: streamlit run app.py
"""
import streamlit as st

import fv_constants as C
import fv_live as LV
import fv_results as R
import fv_ui_panel as UI
import fv_visualization as V
from fv_model import Cfg
from fv_pdf_export import generate_fv_pdf
from fv_presets import (SETTING_SPECS, apply_preset, bounds, init_session_state_defaults, load_permalink_settings, randomize_seed,
                        sync_query_params)

st.set_page_config(page_title="Fernverkehr – Sebastian Hanisch", layout="wide")

SCENARIO_KEYS = list(SETTING_SPECS)
CFG = Cfg()
DATA = R.load_results()


@st.cache_data(show_spinner=False, max_entries=C.CACHE_ENTRIES)
def _live(n, charge, range_km, window, seed_index):
    """Live-Rechnung der vier Zellen (Sekunden), je Einstellung zwischengespeichert. Der Aufruf geht über das Modul, damit die Tests
    die Rechnung ersetzen können."""
    return LV.solve_live(n, charge, range_km, window, seed_index)


st.title("🚛 Fernverkehr: Fahrerregeln und Elektro-Lkw")
st.markdown(
    """
Ein Lkw fährt mehrere Stopps über hunderte Kilometer, und zwei Pflichten bestimmen den Fahrplan: die **Lenk- und Ruhezeiten** der Fahrer und beim Elektro-Lkw die **Ladestopps** an festen Ladesäulen. Man würde
erwarten, dass sich die Pflichtpause zum Laden nutzen lässt und die Kombination deshalb billiger wird als die Summe der Einzelkosten – die Demo prüft, ob sich die Kosten addieren oder ob die Pflichten einander helfen
(die **Wechselwirkung**), live auf einer kleinen Instanz und vorgerechnet über je 60 Instanzen. Eine **Erweiterung der Tourenplanungs-Demo** (`vrp_demo`): sie legt eine Ressourcenschicht entlang der Route über
das Basismodell (CVRP mit Zeitfenstern). Wie das Modell funktioniert, steht im Expander „Wie funktioniert diese Demo?“ weiter unten, die formale Beschreibung im Expander „📐 Mathematische Formulierung“. Die Geschwindigkeitswahl
(`slow-steaming-demo`) und der Bestandsausgleich (`leercontainer-demo`) sind ausdrücklich nicht Teil des Modells.
"""
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
preset_names = list(C.PRESETS)
for row in (preset_names[:3], preset_names[3:]):
    cols = st.columns(3)
    for col, name in zip(cols, row):
        with col:
            st.button(name, width="stretch", on_click=apply_preset, args=(name,), help=C.PRESET_HELP[name])

st.caption("🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, um ein Szenario zu teilen.")

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    customers = st.slider("Kunden", *bounds("customers_slider"), key="customers_slider",
                          help="Live-Instanz mit 2 Lkw. Die Rechenzeit wächst stark mit der Kundenzahl (gemessen: etwa 1 s bei 8, 5 s bei "
                               f"10 und 10 s bei 12 Kunden), deshalb höchstens {C.CUSTOMERS_RANGE[1]}.")
    charge = st.select_slider("Typische Ladezeit", options=list(C.CHARGE_OPTIONS), key="charge_slider",
                              format_func=lambda v: f"{v} min",
                              help="Zeit für eine typische Ladung von 60 % der Reichweite. Bestimmt, ob die 45-Minuten-Pause zum Laden reicht.")
    range_km = st.select_slider("Reichweite", options=list(C.RANGE_OPTIONS), key="range_slider", format_func=lambda v: f"{v} km",
                                help="Reichweite des Elektro-Lkw bei vollem Akku (Start voll). Bei 300 km sind nur gut erreichbare Lagen "
                                     "zulässig: der Seed wählt nur unter diesen.")
    window = st.select_slider("Zeitfenster", options=list(C.WINDOW_OPTIONS), key="window_slider",
                              help="Anteil der Kunden mit Zeitfenster und Breite der Fenster: locker 40 % · 12 h, mittel 60 % · 8 h, eng "
                                   "80 % · 4 h. „keine“ = nur Betriebskosten, ohne Verspätung.")
    seed = st.number_input("Seed", *bounds("seed_input"), key="seed_input", step=1,
                           help="Nummer der Instanz: der i-te gültige Seed (jeder Kunde ist mit der eingestellten Reichweite per Rundfahrt "
                                "erreichbar). Die Kennzahlen der Messreihe stehen auf 60 bzw. 40 anderen Instanzen.")
    st.button("🎲 Neue Instanz", width="stretch", on_click=randomize_seed, help="Würfelt einen neuen Seed.")

sync_query_params({key: st.session_state[key] for key in SCENARIO_KEYS})
customers, charge, range_km, seed = int(customers), int(charge), int(range_km), int(seed)

est = C.LIVE_SECONDS.get(customers, 10)
with st.spinner(f"Rechne die vier Fahrpläne für {customers} Kunden … (auf diesem Gerät etwa {est:.0f} s, danach je Einstellung gespeichert)"):
    res = _live(customers, charge, range_km, window, seed)

# ---------------------------------------------------------------------------------------------------
# Hauptansicht
# ---------------------------------------------------------------------------------------------------
st.markdown("## 🚛 Was kosten Fahrerregeln und Elektro-Lkw – und addieren sich die Kosten?")
st.caption(f"Live-Instanz: {res['n']} Kunden, {res['K']} Lkw, davon {res['tw_count']} mit Zeitfenster (Zeitfenster {window}), Ladezeit {charge} min, "
           f"Reichweite {range_km} km, Instanz Nr. {seed} (Seed {res['seed']}). Vier Fahrpläne gerechnet in {UI.fmt_num(res['seconds'])} s: ohne Regeln, "
           "Fahrerregeln (F), Elektro (E) und beides (F+E). Eine einzelne Instanz – die vorgerechnete Messreihe unten trägt die Aussage.")

metric_rows = [st.columns(2), st.columns(2)]
x = UI.render_metrics(metric_rows[0] + metric_rows[1], res)
msg_state = UI.render_message(res, x, DATA)
_, msg_text = UI.message(res, x, DATA)

st.markdown("**Live-Instanz und Messreihe nebeneinander**")
UI.render_comparison(res, x, DATA)

view_label = st.radio("Fahrplan anzeigen für", [C.CELL_LABELS[c] for c in C.CELLS], index=len(C.CELLS) - 1, horizontal=True,
                      key="view_select",
                      help="Reine Anzeigewahl im Ergebnisbereich: die Live-Instanz hat immer alle vier Zellen gerechnet, hier wählen Sie nur, "
                           "welchen Fahrplan Sie sehen.")
view_cell = UI.cell_from_label(view_label)
st.markdown("#### 🗺️ Karte und Fahrplan der gewählten Zelle")
UI.render_schedule("main", res, view_cell)

pdf_slot = st.container()

st.markdown("---")

# ---------------------------------------------------------------------------------------------------
# Kernabschnitt (vorgerechnet)
# ---------------------------------------------------------------------------------------------------
st.markdown("### 📐 Was die Messreihe über 60 Instanzen zeigt")
st.markdown(
    f"""
Kernfrage dieser Demo: Addieren sich die Mehrkosten von Fahrerregeln und Elektro-Lkw, oder helfen sich die Pflichten, weil die Pflichtpause zum Laden genutzt werden kann? Die Antwort steht auf **60 gepaarten Instanzen je Größe**
(dieselben Instanzen in allen vier Zellen), vorgerechnet und **nie live** gerechnet: {DATA['_timings']['messreihe_wanduhr_min']} Minuten auf {DATA['_timings']['messreihe_kerne']} Kernen. Jede Zahl trägt ihre Größe (Kunden, Lkw) und die Zahl der Instanzen;
ein Vorzeichen gilt nur ab 2 Standardfehlern (Mittel ± Standardfehler, keine Prozentwerte ohne Streuung). Alle Prozentwerte sind Prozent der regelfreien Kosten, gepaart je Instanz.
"""
)
UI.render_series_verdict(res, DATA)

st.markdown("**1 · Summe gegen Kombination** – Mehrkosten von Fahrerregeln und Elektro allein (gestapelt = Summe) gegenüber der gemessenen Kombination")
st.plotly_chart(V.sum_vs_combo_figure(DATA), width="stretch", key="core_sum_chart")
st.dataframe(UI.sum_table(DATA), width="stretch", hide_index=True)
_i_free, _i_tw = R.stat(DATA, "kein_fenster"), R.stat(DATA, "basis")
_mech = DATA["kein_fenster"]["mechanism"]
st.caption(f"Die Überlappung von Pause und Laden ist real: {_mech['share_breaks_at_charger']['mean']:.0f} % der Pausen liegen an einer Ladesäule "
           f"(18 Kunden, 3 Lkw, ohne Zeitfenster). Aber ohne Zeitfenster addieren sich die Kosten praktisch (I = {UI.fmt_band(_i_free)}), und mit Zeitfenstern ist die "
           f"Kombination teurer als die Summe (I = {UI.fmt_band(_i_tw)}), weil sich Verspätungen aufschaukeln (abgeleitet, nicht getrennt gemessen).")

st.markdown("**2 · Wechselwirkung I über eine wählbare Achse** – in beiden Größen, je Stufe Mittel ± Standardfehler")
axis = st.selectbox("Achse", list(R.AXIS_NAMES), key="axis_select",
                    help="Reine Anzeigewahl: welche Einstellung der vorgerechneten Messreihe die Grafik über die Stufen zeigt.")
axis_rows = R.axis_rows(DATA, axis)
st.plotly_chart(V.axis_figure(axis_rows, axis), width="stretch", key="core_axis_chart")
st.dataframe(UI.axis_table(axis_rows), width="stretch", hide_index=True)
st.caption("I unter 0: die Kombination ist billiger als die Summe der Einzelkosten, über 0: teurer. Urteil in drei Zuständen: belastbar nur, wenn das "
           "Mittel mehr als 2 Standardfehler von 0 entfernt liegt. „Anteil I < 0“ ist der Anteil der einzelnen Instanzen mit Kombination billiger als Summe. "
           "Bei „Fahrzeuge“ hat jede Stufe ihre eigene Größe (2 Lkw: 12 Kunden, 3 Lkw: 18 Kunden, 4 Lkw: 24 Kunden).")

st.markdown("**3 · Zerlegung nach Kostenart** – woher die Wechselwirkung kommt")
comp_window = st.radio("Zeitfenster der Zerlegung", ["mittel", "keine"], horizontal=True, key="comp_window",
                       format_func=lambda v: "Zeitfenster mittel" if v == "mittel" else "ohne Zeitfenster",
                       help="Reine Anzeigewahl: welche vorgerechnete Messreihe zerlegt wird.")
st.plotly_chart(V.components_figure(DATA, comp_window), width="stretch", key="core_comp_chart")
_ci = DATA["kein_fenster"]["comps_I"]
_cb = DATA["basis"]["comps_I"]
st.caption(f"Die Fahrerzeit ist unteradditiv (Überlappung von Pause und Laden; 18 Kunden, ohne Zeitfenster {UI.fmt_num(_ci['fahrer']['mean'], 0, True)} ± {UI.fmt_num(_ci['fahrer']['se'], 0)} EUR je Flottenlösung), wird aber fast "
           f"aufgezehrt von mehr Übernachtungen ({UI.fmt_num(_ci['naechte']['mean'], 0, True)} EUR: Umweg und Ladezeit reißen die 9-Stunden-Grenze früher) und Fahrzeugzeit ({UI.fmt_num(_ci['fahrzeug']['mean'], 0, True)} EUR). "
           f"Mit Zeitfenstern kommt die Verspätung dazu ({UI.fmt_num(_cb['verspaetung']['mean'], 0, True)} ± {UI.fmt_num(_cb['verspaetung']['se'], 0)} EUR), während die Betriebskosten allein "
           f"praktisch additiv bleiben (I = {UI.fmt_band(R.stat(DATA, 'basis', 'I_oper'))}).")

st.markdown("**4 · Fest oder neu geplant** – die Touren müssen sich an die Regeln anpassen")
_fix_i, _new_i = R.stat_fix(DATA, "basis"), R.stat(DATA, "basis")
_fix_l, _new_l = R.stat_fix(DATA, "live10"), R.stat(DATA, "live10")
st.info(f"Wer die regelfreien Touren nur unter den Regeln neu bewertet, statt neu zu planen, überschätzt die Wechselwirkung mit Zeitfenstern mehr als doppelt: "
        f"18 Kunden, 3 Lkw: I = {UI.fmt_band(_fix_i)} bei festen Touren gegen {UI.fmt_band(_new_i)} bei neu geplanten; 10 Kunden, 2 Lkw: {UI.fmt_band(_fix_l)} "
        f"gegen {UI.fmt_band(_new_l)}. Die Tabelle steht im Expander unten (Tab „Fest oder neu geplant“), dort mit der Live-Instanz.")

st.markdown("**5 · Annahmen-Vergleich** – welche Aussage hängt an einer erfundenen Annahme (Größe), welche nicht (Vorzeichen)")
a1, a2 = st.columns(2)
with a1:
    st.plotly_chart(V.assumption_figure(DATA, "pause"), width="stretch", key="core_pause_chart")
with a2:
    st.plotly_chart(V.assumption_figure(DATA, "strafe"), width="stretch", key="core_penalty_chart")
st.dataframe(UI.pause_table(DATA), width="stretch", hide_index=True)
st.dataframe(UI.penalty_table(DATA), width="stretch", hide_index=True)
_reg = R.stat(DATA, "fenster_regelbewusst")
st.caption(f"Pausen zählen in der Grundannahme als bezahlte Fahrerzeit; mit unbezahlten Pausen bleibt das Vorzeichen, die Größe ändert sich. Die Verspätungsstrafe skaliert die Wechselwirkung mit Zeitfenstern "
           f"fast linear (Größe hängt an der erfundenen Strafe, das Vorzeichen nicht); die Betriebskosten allein bleiben klein. Zeitfenster sind an einer regelfreien Referenztour kalibriert; "
           f"legt man sie an einen Regelplan an, gilt dieselbe Richtung (18 Kunden, 3 Lkw, {DATA['fenster_regelbewusst']['used']} Instanzen: I = {UI.fmt_band(_reg)}).")

st.markdown("**6 · Ausgeschlossene Instanzen und Rechenzeiten**")
_ex = R.excluded_series(DATA)
st.caption("Ausgeschlossen bei Reichweite 300 km: " + "; ".join(
    f"{e['size']}: {e['used']} von {e['instances']} Lagen auswertbar" + (f" ({e['excluded']} ausgeschlossen: "
    f"{e['reasons']['basistouren_unter_E_nicht_fahrbar']} Mal waren die regelfreien Basistouren mit E nicht fahrbar, "
    f"{e['reasons']['suche_ohne_loesung']} Mal fand die Suche keine zulässige Lösung)" if e["reasons"] else f" ({e['excluded']} ausgeschlossen)")
    for e in _ex) + ". Die ausgeschlossenen sind die schwierigeren Lagen, die 300-km-Zahlen sind also eher zu günstig.")
_t = DATA["_timings"]
_ev = _t["evaluator_ms_je_6_stopp_route"]
_ls = _t["live_suche_s"]
st.caption("Rechenzeiten (gemessen, dieses Gerät): Live-Instanz mit 2 Lkw, vier Zellen, 3 Neustarts, Zeitfenster mittel: "
           + ", ".join(f"{k} Kunden {' und '.join(UI.fmt_num(v) for v in _ls[k])} s" for k in sorted(_ls, key=int))
           + f". Evaluator je Route mit 6 Stopps: ohne Regeln unter {UI.fmt_num(_ev['aus'])} ms, F {UI.fmt_num(_ev['F'])} ms, E {UI.fmt_num(_ev['E'])} ms, F+E {UI.fmt_num(_ev['FE'], 0)} ms. "
           "Deshalb rechnet die Live-Instanz höchstens 12 Kunden, mit Spinner und Zwischenspeicher je Einstellung; auf einem langsameren Server dauert es entsprechend länger.")

# PDF (nach der Live-Rechnung, damit der Fahrplan der gewählten Zelle drinsteht)
with pdf_slot:
    st.download_button(
        "📄 Fahrplan als PDF herunterladen",
        data=generate_fv_pdf(dict(customers=customers, charge=charge, range_km=range_km, window=window, seed=seed), res, view_cell, x, msg_text,
                             [(R.number_label(DATA[name]), R.Stat.from_dict(DATA[name]["I"])) for name in UI.matching_series(res, DATA)]),
        file_name="fernverkehr_fahrplan.pdf", mime="application/pdf", key="primary_pdf_download",
        help="Einstellungen, Kosten der vier Zellen, Wechselwirkung, Vergleich mit der Messreihe und die Halteliste der gewählten Zelle.")

st.markdown("---")

# ---------------------------------------------------------------------------------------------------
# Ansichten
# ---------------------------------------------------------------------------------------------------
with st.expander("🔧 Wie wir das erreichen – Fahrplan-Evaluator und Tourensuche"):
    tabs = st.tabs(["🗺️ Fahrplan", "📊 Kostenzerlegung", "🔁 Fest oder neu geplant", "📈 Messreihe"])
    with tabs[0]:
        st.markdown(
            "Der **Fahrplan-Evaluator** macht aus einer Stoppfolge den kostenoptimalen Fahrplan: wo geladen wird, wie viel, wo die Pflichtpause "
            "und die Tagesruhe liegen (Label-Setting mit Pareto-Dominanz, siehe „Wie funktioniert diese Demo?“). Die **Tourensuche** rechnet mit dem "
            "Evaluator der jeweiligen Zelle: die Touren passen sich an die Regeln an. Unten die vier Zellen der Live-Instanz nebeneinander; Halteliste "
            "und Zeitstrahl der gewählten Zelle stehen oben in der Hauptansicht."
        )
        st.dataframe(UI.live_cost_table(res), width="stretch", hide_index=True)
        map_cols = [st.columns(2), st.columns(2)]
        for i, (slot, c) in enumerate(zip(map_cols[0] + map_cols[1], C.CELLS)):
            with slot:
                st.markdown(f"**{C.CELL_LABELS[c]}**")
                if res["cells"][c]["feasible"]:
                    st.plotly_chart(V.route_map_figure(res, c), width="stretch", key=f"tab_map_{i}")
                else:
                    st.warning("keine zulässige Lösung")
        st.caption("Die Kundenreihenfolge und die Zuordnung der Kunden zu den beiden Lkw ändern sich mit den Regeln – nur so misst man den Preis der Regeln "
                   "und nicht die Nachbewertung fester Touren.")
    with tabs[1]:
        if x is None:
            st.warning("Keine Kostenzerlegung: für diese Lage fand die Suche keine zulässige Lösung in allen Zellen.")
        else:
            st.plotly_chart(V.cost_breakdown_figure(res), width="stretch", key="tab_cost_live")
            st.dataframe(UI.cost_component_table(res), width="stretch", hide_index=True)
        st.markdown(f"**Zerlegung der Wechselwirkung aus der Messreihe** (EUR je Flottenlösung, Mittel ± Standardfehler, {R.number_label(DATA['basis'])}, mit Zeitfenstern):")
        st.dataframe(UI.comps_I_table(DATA), width="stretch", hide_index=True)
        st.caption("Kilometer, Fahrerzeit (bezahlte Zeit ohne Tagesruhe), Fahrzeugzeit (auch Stillstand), Übernachtungen (100 EUR je Tagesruhe) und Verspätung (40 EUR je Stunde) "
                   "ergeben die Gesamtkosten. Ein Wert unter 0 heißt: in dieser Kostenart ist die Kombination billiger als die Summe der Einzelkosten.")
    with tabs[2]:
        if x is None:
            st.warning("Kein Vergleich: für diese Lage fand die Suche keine zulässige Lösung in allen Zellen.")
        else:
            st.plotly_chart(V.fix_vs_replanned_figure(res), width="stretch", key="tab_fix_live")
            st.caption("Live-Instanz (ein Fall): dieselben regelfreien Touren unter den Regeln nachbewertet („feste Touren“) gegenüber neu geplanten Touren. "
                       "Neu geplant ist nie schlechter als die Nachbewertung; „nicht fahrbar“ heißt: die regelfreie Tour reicht mit der Akkuladung nicht.")
        st.markdown("**Messreihe** (Mehrkosten und Wechselwirkung, fest gegenüber neu geplant):")
        st.dataframe(UI.fix_table(DATA), width="stretch", hide_index=True)
    with tabs[3]:
        st.markdown("Alle vorgerechneten Messreihen, Mittel ± Standardfehler in Prozent der regelfreien Kosten (F, E, F+E: Mehrkosten gegenüber der regelfreien Tour; I: Wechselwirkung), "
                    "dazu Median und Quartile der Wechselwirkung und der Anteil der Instanzen mit Kombination billiger als die Summe.")
        st.dataframe(UI.measured_overview(DATA), width="stretch", hide_index=True)
        st.markdown("**Mechanismus** – die Überlappung von Pause und Laden (Zelle F+E):")
        st.dataframe(UI.mechanism_table(DATA), width="stretch", hide_index=True)
        _nz = DATA["_ap0_b_suchrauschen"]["gepoolt"]
        st.caption(f"Suchrauschen (Live-Größe, {_nz['n']} Instanzen mit zwei Such-Seeds): nur die Zelle F+E rauscht, das 95. Perzentil des Unterschieds der Wechselwirkung liegt bei "
                   f"{UI.fmt_num(_nz['abs_dI']['p95'], 1)} % der regelfreien Kosten, das Maximum bei {UI.fmt_num(_nz['abs_dI']['max'], 1)} %; daraus die Meldungsschwelle von {C.THRESHOLD_PCT:.0f} %. "
                   "Die Suche findet die Kombination höchstens zu teuer, nie zu billig.")

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        f"""
**Basis.** Wie in der `vrp_demo`: ein CVRP mit Zeitfenstern, 800 × 800 km, Depot in der Mitte, Kunden mit Bedarf 1 bis 10 und Service 30 bis 60 Minuten, Luftlinie, {CFG.speed:.0f} km/h. Die Live-Instanz hat 2 Lkw, die Hauptmessreihe 3 Lkw
(18 Kunden); die Kapazität ist so gewählt, dass die Bedarfssumme 80 % der Flottenkapazität ausmacht. **Zeitfenster** sind weich: {CFG.c_late:.0f} EUR je Stunde Verspätung je Stopp. Sie liegen um die Servicebeginne einer regelfreien
Referenztour, deshalb hat die regelfreie Basis 0 Verspätung (Konstruktion, kein Fehler); Anteil und Breite stellt der Regler „Zeitfenster“ ein.

**Fahrerregeln (F).** Nach {CFG.blk / 60:.1f} Stunden Lenkzeit {CFG.brk:.0f} Minuten Pause am Stück, höchstens {CFG.day / 60:.0f} Stunden Lenkzeit je Schicht, danach {CFG.rest / 60:.0f} Stunden Tagesruhe (das Fahrzeug steht, {CFG.c_night:.0f} EUR
Übernachtung). Pause und Ruhe dürfen freiwillig früher genommen werden, am Kunden und an jeder Ladesäule. **Elektro (E).** Reichweite {CFG.R:.0f} km bei vollem Akku (Start voll), 12 feste Ladesäulen, Laden nur an Ladesäulen (Umweg, Zeit); eine
„typische Ladung“ füllt 60 % der Reichweite in der eingestellten Ladezeit, das Laden ist proportional zur Energie. Am Lader dauert eine Pause max(45 Minuten, Ladezeit), und eine Tagesruhe am Lader macht den Akku voll.

**Kosten.** {CFG.c_km:.2f} EUR je km (Energie neutral: gemessen wird, was Reichweite und Ladezwang kosten, nicht der Energiepreis), {CFG.c_drv:.0f} EUR je Stunde bezahlte Fahrerzeit (auch Pausen, Warten, Laden),
{CFG.c_veh:.0f} EUR je Stunde Fahrzeugzeit (auch Stillstand), {CFG.c_night:.0f} EUR je Tagesruhe, {CFG.c_late:.0f} EUR je Stunde Verspätung. Diese Parameter sind **erfunden, nicht kalibriert**: Prozentwerte sind Größenordnungen, keine Euro-Aussagen.

**Fahrplan-Evaluator.** Gegeben eine Stoppfolge, wählt er den kostenoptimalen Fahrplan aus Ladestopps, Ladeumfang, Pausen und Tagesruhen (Label-Setting mit Pareto-Dominanz über Kosten, Zeit, Lenkzeit-Zähler und Akkustand, mit
kleinen Toleranzen für die Geschwindigkeit). Er wurde gegen einen unabhängigen Tick-Simulator mit Plan-Enumeration geprüft (in den Tests des Repos) und liegt nie unter dem exakten Wert. **Tourensuche.** Savings- und Einfüge-Starts,
Relocate, Swap, 2-opt, 2-opt* und eine kleine ILS – alles mit dem Evaluator der jeweiligen Zelle. Sie ist eine Heuristik, kein Optimalitätsbeweis.

**Wechselwirkung.** I = Kosten(F+E) − Kosten(F) − Kosten(E) + Kosten(ohne Regeln), in Prozent der regelfreien Kosten. Unter 0: die Kombination ist billiger als die Summe der Einzelkosten, über 0: teurer. Die Meldung der Live-Instanz hat drei
Zustände mit einer Schwelle von {C.THRESHOLD_PCT:.0f} % der regelfreien Kosten, abgeleitet aus dem Suchrauschen: darunter „praktisch additiv“.

**Warum die Touren mitplanen müssen.** Die Tourensuche passt Kundenreihenfolge und Zuordnung an die Regeln an. Nur so misst man den Preis der Regeln; wer die regelfreien Touren bloß nachbewertet, überschätzt die Wechselwirkung mit Zeitfenstern
mehr als doppelt (Kernabschnitt, Punkt 4).

**Warum Live-Instanz und Messreihe nebeneinanderstehen.** Eine einzelne kleine Instanz streut: das Vorzeichen der Wechselwirkung kippt von Instanz zu Instanz (Anteil der Instanzen mit I < 0 in der Tabelle). Live macht die Fahrpläne anfassbar
(Halteliste, Zeitstrahl), die Mittelwerte über 60 Instanzen tragen die Aussage. Deshalb nennt die Meldung beides.

**Grenzen dieses Modells** (bewusst so gewählt, damit die Aussage ehrlich bleibt):

- **Stark stilisiert** – Luftlinie, konstante Geschwindigkeit, ein Depot, alle Lkw starten gleichzeitig mit vollem Akku und frischem Fahrer.
- **Kostenparameter erfunden** – besonders alles mit Verspätung hängt an den {CFG.c_late:.0f} EUR je Stunde; die Größe der Wechselwirkung mit Zeitfenstern skaliert fast linear mit der Strafe (Kernabschnitt, Punkt 5), das Vorzeichen nicht.
- **Pausen zählen als bezahlte Fahrerzeit** – mit unbezahlten Pausen bleibt das Vorzeichen, die Größe ändert sich (vorgerechnet, kein Regler).
- **EU-Regeln vereinfacht** – keine 15+30-Aufteilung der Pause, keine 10-Stunden-Tage, keine Wochenruhe, keine Uhrzeiten; keine juristische Aussage.
- **Ladeinfrastruktur vereinfacht** – Ladeleistung linear (keine Kurve), keine Wartezeit an der Säule, jede Säule beliebig oft nutzbar, Energiepreis neutral.
- **Weiche Zeitfenster** sind eine Modellwahl: harte Fenster wären mit Regeln massenhaft unzulässig, dann gäbe es keine Kostenmessung.
- **Ausgeschlossene Lagen** – bei 300 km Reichweite sind nur gut erreichbare Lagen zulässig; die Messreihe wertet dort weniger Instanzen aus (siehe Kernabschnitt, Punkt 6).
- **Nicht Teil dieser Demo** – Stafette und Fahrerdienstplan (eigenes Modell, möglicher Folgeausbau), Geschwindigkeitswahl, Energiepreise, Ladeleistungskurve, unbezahlte Pausen als Regler, Wochenlenkzeit.
        """
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Tour und Fahrplan.** Eine Tour ist $r = (0, c_1, \dots, c_m, 0)$ mit Depot $0$. Ein Fahrplan zerlegt sie in Fahrt, Service, Warten, Pause, Laden und Tagesruhe. Zulässig ist er, wenn die Lenkzeit seit der letzten Pause höchstens $270$ min beträgt,
die Lenkzeit je Schicht höchstens $540$ min und der Akkustand $b$ immer zwischen $0$ und der Reichweite $R$ liegt:
$$d_c \le 270,\qquad d_s \le 540,\qquad 0 \le b \le R .$$

**Kosten.** Mit $\text{km}$ gefahrenen Kilometern, $h_F$ bezahlten Fahrerstunden (ohne Tagesruhe), $h_V$ Fahrzeugstunden (auch Stillstand), $N$ Tagesruhen und $L$ Verspätungsstunden (Summe über die Stopps):
$$\text{Kosten}(r) = 0{,}70\,\text{km} + 32\,h_F + 15\,h_V + 100\,N + 40\,L .$$
Der Evaluator bestimmt den kostenminimalen zulässigen Fahrplan zu $r$ per Label-Setting; Zustand ist (Zeit, Lenkzeit seit Pause, Tageslenkzeit, Akku), dominierte Zustände werden verworfen.

**Tourenproblem.** $\min \sum_r \text{Kosten}(r)$ über die Zuordnung der Kunden zu den $K$ Lkw und die Reihenfolge, mit Kapazität je Lkw. Die vier Zellen (ohne Regeln, F, E, F+E) unterscheiden sich nur im Evaluator: ohne Regeln
entfällt Pause, Ruhe und Akku, F schaltet Lenk- und Ruhezeiten ein, E Reichweite und Laden.

**Wechselwirkung.** Für eine Instanz mit den Zellkosten $C_\emptyset, C_F, C_E, C_{FE}$:
$$I = C_{FE} - C_F - C_E + C_\emptyset,\qquad I_\% = 100\,I / C_\emptyset .$$
$I < 0$: die Kombination ist billiger als die Summe der Einzelkosten. Über $j = 1..N$ gepaarte Instanzen sind $\bar I$ und $\text{SE} = s / \sqrt{N}$ Mittel und Standardfehler; ein Vorzeichen gilt als belastbar, wenn $|\bar I| > 2\,\text{SE}$.
Zerlegung: $I = \sum_k I_k$ über die Kostenarten $k$ (Kilometer, Fahrerzeit, Fahrzeugzeit, Übernachtungen, Verspätung), jeweils mit demselben Vierer-Term.

**Meldung der Live-Instanz.** $I_\% < -2$: „billiger als die Summe“; $|I_\%| \le 2$: „praktisch additiv“; $I_\% > 2$: „teurer als die Summe“ (mögliches Suchartefakt, weil die Heuristik $C_{FE}$ nur zu hoch finden kann).

Implementiert in `fv_model.py` (Parameter, Instanz), `fv_evaluator.py` (Fahrplan), `fv_search.py` (Tourensuche, Zeitfenster), `fv_live.py` (Live-Rechnung) und `fv_results.py` (Messreihe, Urteil).
        """
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
