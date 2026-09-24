"""Wiederverwendbares Panel: Kennzahlen (2 x 2), Meldung in drei Zuständen, Vergleichstabelle, Karte und Fahrplan, Tabellen des
Kernabschnitts (Plan Abschnitt 6/8)."""
import pandas as pd
import streamlit as st

import fv_constants as C
import fv_results as R
import fv_schedule as S
import fv_visualization as V


# ---------------------------------------------------------------------------------------------------
# Zahlenformate (deutsches Dezimalkomma)
# ---------------------------------------------------------------------------------------------------
def fmt_num(v, digits=1, signed=False):
    text = f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"
    return text.replace(".", ",")


def fmt_pct(v, digits=1, signed=False):
    return f"{fmt_num(v, digits, signed)} %"


def fmt_eur(v, signed=False):
    text = f"{v:+,.0f}" if signed else f"{v:,.0f}"
    return text.replace(",", ".") + " EUR"


def fmt_band(s: R.Stat, digits=1):
    """Mittel ± Standardfehler mit Vorzeichen: '+7,9 ± 1,0 %'."""
    return f"{fmt_num(s.mean, digits, True)} ± {fmt_num(s.se, digits)} %"


def fmt_share(v):
    return f"{100.0 * v:.0f} %"


CELL_ORDER = list(C.CELLS)
CHART_TABLE_HEIGHT = C.CHART_HEIGHT + 60                     # die Halteliste ist so hoch wie die Karte daneben und scrollt


# ---------------------------------------------------------------------------------------------------
# Live-Instanz: Kennzahlen, Meldung, Vergleichsspalte
# ---------------------------------------------------------------------------------------------------
def live_costs(res):
    """Kosten der vier Zellen, wenn alle zulässig sind, sonst None."""
    if not all(res["cells"][c]["feasible"] for c in C.CELLS):
        return None
    return {c: res["cells"][c]["total"] for c in C.CELLS}


def infeasible_cells(res):
    return [c for c in C.CELLS if not res["cells"][c]["feasible"]]


def render_metrics(columns, res):
    """Vier Kennzahlen im 2 x 2-Raster: Mehrkosten von F, E, F+E in % der regelfreien Kosten und die Wechselwirkung I."""
    costs = live_costs(res)
    if costs is None:
        for col, label in zip(columns, ("Mehrkosten Fahrerregeln", "Mehrkosten Elektro", "Mehrkosten beides", "Wechselwirkung I")):
            col.metric(label, "–", help="Für diese Lage fand die Suche in mindestens einer Zelle keine zulässige Lösung.")
        return None
    x = R.interaction_from_costs(costs)
    columns[0].metric(
        "Mehrkosten Fahrerregeln (F)", fmt_pct(x["dF_pct"], signed=True), delta=fmt_eur(x["dF_eur"], signed=True), delta_color="off",
        delta_arrow="off",
        help="Kosten der Flottenlösung mit Lenk- und Ruhezeiten (Touren neu geplant) gegenüber der regelfreien Lösung, in Prozent der "
             "regelfreien Kosten (darunter in EUR). Live-Instanz: ein einzelner Fall.")
    columns[1].metric(
        "Mehrkosten Elektro (E)", fmt_pct(x["dE_pct"], signed=True), delta=fmt_eur(x["dE_eur"], signed=True), delta_color="off",
        delta_arrow="off",
        help="Kosten mit Reichweite und Ladestopps an festen Ladesäulen (Touren neu geplant) gegenüber der regelfreien Lösung. "
             "Energiepreis neutral: gemessen wird nur, was Reichweite und Ladezwang an Zeit und Umweg kosten.")
    columns[2].metric(
        "Mehrkosten beides (F+E)", fmt_pct(x["dFE_pct"], signed=True), delta=f"Summe der Einzelnen {fmt_pct(x['dF_pct'] + x['dE_pct'], signed=True)}",
        delta_color="off", delta_arrow="off",
        help="Kosten mit beiden Pflichten gegenüber der regelfreien Lösung. Darunter zum Vergleich die Summe der beiden Einzel-Mehrkosten.")
    columns[3].metric(
        "Wechselwirkung I", fmt_pct(x["I_pct"], signed=True), delta=fmt_eur(x["I_eur"], signed=True), delta_color="inverse",
        help="I = Kosten(F+E) − Kosten(F) − Kosten(E) + Kosten(ohne Regeln), in % der regelfreien Kosten (darunter in EUR). Negativ: die "
             "Kombination ist billiger als die Summe der Einzelkosten (Pause und Laden helfen sich), positiv: teurer. Eine einzelne "
             "Instanz streut stark - die Messreihe unten trägt die Aussage.")
    return x


def matching_series(res, data):
    """Messreihen zur eingestellten Ladezeit, Reichweite und Zeitfenster: in Größe der Live-Instanz (falls gemessen), in der
    Live-Größe der Messreihe (10 Kunden, 2 Lkw) und in der Hauptmessreihe (18 Kunden, 3 Lkw). Namen ohne Doppelte, None-frei."""
    out = []
    for n, K in ((res["n"], res["K"]), C.SIZE_LIVE, C.SIZE_MAIN):
        name = R.find_series(data, n, K, res["window"], res["charge"], res["range_km"])
        if name and name not in out:
            out.append(name)
    return out


def context_sentence(res, data):
    """Bezug der Einzelinstanz zur Messreihe: passende 10-Kunden-Reihe mit Anteilen der drei Meldungszustände."""
    name = R.find_series(data, C.SIZE_LIVE[0], C.SIZE_LIVE[1], res["window"], res["charge"], res["range_km"])
    if name is None:
        return ("Für genau diese Kombination aus Ladezeit, Reichweite und Zeitfenster gibt es in der Größe 10 Kunden, 2 Lkw keine "
                "vorgerechnete Messreihe (siehe Vergleichstabelle und Kernabschnitt).")
    s = data[name]
    st_ = s["states"]
    i = R.Stat.from_dict(s["I"])
    return (f"Messreihe zu diesen Einstellungen ({R.number_label(s)}): I = {fmt_band(i)}; bei einer Schwelle von "
            f"{C.THRESHOLD_PCT:.0f} % meldet sie auf den einzelnen Instanzen {fmt_share(st_['billiger'])} „billiger“, "
            f"{fmt_share(st_['additiv'])} „praktisch additiv“ und {fmt_share(st_['teurer'])} „teurer“.")


def excluded_sentence(data):
    """Wie oft die Messreihe (10 Kunden, 2 Lkw, Reichweite 300 km) solche Lagen ausgeschlossen hat."""
    s = data["live10_reich300"]
    n_none = s.get("excluded_reasons", {}).get("suche_ohne_loesung", 0)
    return (f"In der Messreihe (Reichweite 300 km, {s['n']} Kunden, {s['K']} Lkw) kam das bei {n_none} von {s['instances']} Lagen vor; "
            "solche Lagen sind dort ausgeschlossen.")


def message(res, x, data):
    """Bedingte Meldung der Live-Instanz in drei Zuständen mit Schwelle 2 % der regelfreien Kosten (Plan Abschnitt 6), dazu der
    Fall, dass die Suche für diese Lage keine zulässige Lösung fand. Rückgabe: (Zustand, Text) mit Zustand 'billiger', 'additiv',
    'teurer' oder 'unzulaessig'."""
    if x is None:
        cells = ", ".join(C.CELL_LABELS[c] for c in infeasible_cells(res))
        return "unzulaessig", (
            f"⚠️ Für diese Lage ({res['n']} Kunden, Reichweite {res['range_km']} km) fand die Tourensuche in der Zelle {cells} keine "
            f"zulässige Lösung, die Kennzahlen lassen sich nicht bilden. {excluded_sentence(data)} Bitte einen anderen Seed oder eine "
            "größere Reichweite wählen.")
    state = R.message_state(x["I_pct"])
    ctx = context_sentence(res, data)
    if state == "billiger":
        return state, (
            f"✅ Hier sparen Pause und Laden zusammen: die Kombination ist um {fmt_eur(-x['I_eur'])} ({fmt_pct(-x['I_pct'])} der "
            f"regelfreien Kosten) billiger als die Summe der Einzelkosten. Das ist belastbar, weil die Tourensuche eine Lösung nur zu "
            f"teuer finden kann, nie zu billig - für eine einzelne Instanz gilt es trotzdem nur für diese Lage. {ctx}")
    if state == "additiv":
        return state, (
            f"ℹ️ Auf dieser Instanz praktisch additiv: I = {fmt_pct(x['I_pct'], signed=True)} liegt innerhalb von ±{C.THRESHOLD_PCT:.0f} % "
            f"der regelfreien Kosten (das ist die Größenordnung von Suchrauschen und Auswertungsfehler). Die Kosten der beiden Pflichten "
            f"addieren sich hier. {ctx}")
    noise = data["_ap0_b_suchrauschen"]["live10"]["best_of_6"]["gap"]
    return state, (
        f"⚠️ Hier ist die Kombination um {fmt_eur(x['I_eur'])} ({fmt_pct(x['I_pct'])} der regelfreien Kosten) teurer als die Summe der "
        f"Einzelkosten. Vorsicht: die Tourensuche ist eine Heuristik und kann die Kombination nur zu teuer finden, nie zu billig "
        f"(gegenüber dem Besten aus sechs Suchläufen lag sie in dieser Größe im Mittel {fmt_num(noise['mean'])} Prozentpunkte darüber, "
        f"im Einzelfall bis {fmt_num(noise['max'])}) - ein Suchartefakt ist möglich. {ctx}")


def render_message(res, x, data):
    state, text = message(res, x, data)
    {"billiger": st.success, "additiv": st.info, "teurer": st.warning, "unzulaessig": st.warning}[state](text)
    return state


def comparison_table(res, x, data):
    """Vergleichstabelle Live-Instanz gegen passende Messreihen: Mehrkosten F, E, F+E und Wechselwirkung I."""
    rows = []
    for label, key in (("Mehrkosten Fahrerregeln (F)", "dF"), ("Mehrkosten Elektro (E)", "dE"), ("Mehrkosten beides (F+E)", "dFE"),
                       ("Wechselwirkung I", "I")):
        row = {"Kennzahl": label, f"Live-Instanz ({res['n']} Kunden, 2 Lkw, 1 Instanz)":
               ("–" if x is None else fmt_pct(x[key + "_pct"], signed=True))}
        for name in matching_series(res, data):
            s = data[name]
            row[R.number_label(s)] = fmt_band(R.Stat.from_dict(s[key]))
        rows.append(row)
    return pd.DataFrame(rows)


def render_comparison(res, x, data):
    names = matching_series(res, data)
    st.dataframe(comparison_table(res, x, data), width="stretch", hide_index=True)
    if names:
        note = ("Mittel ± Standardfehler je Messreihe, in Prozent der regelfreien Kosten; die Größe (Kunden, Lkw) und die Zahl der "
                "Instanzen stehen an jeder Spalte.")
        if res["n"] not in (C.SIZE_LIVE[0],) and R.find_series(data, res["n"], res["K"], res["window"], res["charge"], res["range_km"]) is None:
            note += (f" Für {res['n']} Kunden gibt es keine eigene Messreihe; die Vergleichsspalten sind die 10-Kunden-Reihe (2 Lkw) "
                     "und die 18-Kunden-Reihe (3 Lkw).")
        st.caption(note)
    else:
        st.caption("Für diese Kombination aus Ladezeit, Reichweite und Zeitfenster gibt es keine vorgerechnete Messreihe - der "
                   "Kernabschnitt unten zeigt die gemessenen Stufen.")


# ---------------------------------------------------------------------------------------------------
# Karte, Zeitstrahl, Halteliste
# ---------------------------------------------------------------------------------------------------
def cell_from_label(label):
    for cell, text in C.CELL_LABELS.items():
        if text == label:
            return cell
    raise KeyError(label)


def halteliste_frame(events, n_customers):
    rows = S.halteliste(events, n_customers)
    return pd.DataFrame([{"Von": r["von"], "Bis": r["bis"], "Ort": r["ort"], "Ereignis": r["ereignis"], "Einzelheit": r["einzelheit"],
                          "Dauer": r["dauer"]} for r in rows])


def cell_summary_line(res, cell):
    m = res["cells"][cell]["metrics"]
    counts_b = m["breaks"]
    return (f"{C.CELL_LABELS[cell]}: {fmt_eur(res['cells'][cell]['total'])}, {m['km']:.0f} km, {counts_b} Pausen, {m['nights']} "
            f"Tagesruhen, {m['charges']} Ladehalte, {fmt_num(m['late_min'] / 60.0)} h Verspätung")


def render_schedule(prefix, res, cell):
    """Zeitstrahl der gewählten Zelle über die ganze Breite, darunter Karte und Halteliste je Lkw nebeneinander."""
    data = res["cells"][cell]
    if not data["feasible"]:
        st.warning(f"Für {C.CELL_LABELS[cell]} fand die Suche keine zulässige Lösung (Reichweite {res['range_km']} km): kein Fahrplan.")
        return
    st.caption(cell_summary_line(res, cell) + ".")
    st.plotly_chart(V.timeline_figure(res, cell), width="stretch", key=f"{prefix}_timeline")
    st.caption("Zeitstrahl: ein Balken je Ereignis, Zeitangaben in Stunden seit der gemeinsamen Abfahrt; gepunktete Linien sind Tagesgrenzen, "
               "ein roter Rand am Service heißt verspätet.")
    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(V.route_map_figure(res, cell), width="stretch", key=f"{prefix}_map")
        st.caption("Karte: Linien zeigen die Fahrplanreihenfolge (Kunden und Ladehalte); Pausen und Tagesruhen sind Zeiten, keine Orte, "
                   "und stehen im Zeitstrahl und in der Halteliste.")
    with right:
        trucks = data["trucks"]
        tabs = st.tabs([f"Halteliste Lkw {t['truck']}" for t in trucks])
        for tab, t in zip(tabs, trucks):
            with tab:
                st.dataframe(halteliste_frame(t["events"], res["n"]), width="stretch", hide_index=True, height=CHART_TABLE_HEIGHT)


# ---------------------------------------------------------------------------------------------------
# Kernabschnitt: Tabellen
# ---------------------------------------------------------------------------------------------------
def sum_table(data):
    rows = []
    for r in R.sum_rows(data):
        rows.append({
            "Größe": r["size_label"], "Zeitfenster": r["window"], "Instanzen": r["count"],
            "Fahrerregeln allein": fmt_band(r["dF"]), "Elektro allein": fmt_band(r["dE"]),
            "Summe der Einzelnen": fmt_pct(r["dF"].mean + r["dE"].mean, signed=True),
            "beides, gemessen": fmt_band(r["dFE"]),
            "Wechselwirkung I": fmt_band(r["I"]), "Urteil": R.VERDICT_SHORT[r["I"].verdict()]})
    return pd.DataFrame(rows)


def axis_table(rows):
    out = []
    for r in rows:
        s = r["stat"]
        out.append({"Gruppe": r["group"], "Stufe": r["level"], "Größe": r["size_label"], "Instanzen": r["count"],
                    "Wechselwirkung I": fmt_band(s), "Median [Q1; Q3]": f"{fmt_num(s.median, 1, True)} [{fmt_num(s.q1, 1, True)}; {fmt_num(s.q3, 1, True)}]",
                    "Anteil I < 0": fmt_share(s.neg_share), "Urteil": R.VERDICT_SHORT[r["verdict"]]})
    return pd.DataFrame(out)


def fix_table(data):
    """Fest oder neu geplant: I mit nachbewerteten regelfreien Touren gegen I mit neu geplanten Touren (vier Messreihen)."""
    rows = []
    for name, window in (("live10_kein_fenster", "ohne Zeitfenster"), ("live10", "Zeitfenster mittel"),
                         ("kein_fenster", "ohne Zeitfenster"), ("basis", "Zeitfenster mittel")):
        s = data[name]
        fx = {k: R.Stat.from_dict(v) for k, v in s["fix"].items()}
        rows.append({
            "Größe": R.size_label(s), "Zeitfenster": window, "Instanzen": R.count_label(s),
            "F fest / neu": f"{fmt_pct(fx['dF'].mean, 1, True)} / {fmt_pct(s['dF']['mean'], 1, True)}",
            "E fest / neu": f"{fmt_pct(fx['dE'].mean, 1, True)} / {fmt_pct(s['dE']['mean'], 1, True)}",
            "F+E fest / neu": f"{fmt_pct(fx['dFE'].mean, 1, True)} / {fmt_pct(s['dFE']['mean'], 1, True)}",
            "I fest": fmt_band(fx["I"]), "I neu geplant": fmt_band(R.Stat.from_dict(s["I"]))})
    return pd.DataFrame(rows)


def pause_table(data):
    rows = []
    for key, label in (("kein_fenster_45min", "ohne Zeitfenster, 45 min"), ("basis_45min_mit_fenster", "Zeitfenster mittel, 45 min"),
                       ("kein_fenster_20min", "ohne Zeitfenster, 20 min"), ("kein_fenster_90min", "ohne Zeitfenster, 90 min")):
        c = data["_ap0_c_unbezahlte_pausen"][key]
        rows.append({"Einstellung (18 Kunden, 3 Lkw)": label, "Instanzen": c["n"],
                     "Fahrerregeln bezahlt → unbezahlt": f"{fmt_pct(c['dF_paid']['mean'], 1, True)} → {fmt_pct(c['dF_unpaid']['mean'], 1, True)}",
                     "I, Pausen bezahlt": fmt_band(R.Stat.from_dict(c["I_paid"])),
                     "I, Pausen unbezahlt": fmt_band(R.Stat.from_dict(c["I_unpaid"])),
                     "Urteil unbezahlt": R.VERDICT_SHORT[R.Stat.from_dict(c["I_unpaid"]).verdict()]})
    return pd.DataFrame(rows)


def penalty_table(data):
    rows = []
    for lv in ("20", "40", "80"):
        p = data["_ap0_d_verspaetungsstrafe"][lv]
        i = R.Stat.from_dict(p["I"])
        rows.append({"Verspätungsstrafe (18 Kunden, 3 Lkw, Zeitfenster mittel)": f"{lv} EUR/h" + (" (Grundannahme)" if lv == "40" else ""),
                     "Instanzen": p["n"], "Wechselwirkung I": fmt_band(i), "I in EUR": fmt_eur(p["I_eur"]["mean"], signed=True),
                     "nur Betriebskosten": fmt_band(R.Stat.from_dict(p["I_oper"])), "Anteil I < 0": fmt_share(p["neg_share"]),
                     "Urteil": R.VERDICT_SHORT[i.verdict()]})
    return pd.DataFrame(rows)


def mechanism_table(data):
    rows = []
    for name, window in (("kein_fenster", "ohne Zeitfenster"), ("basis", "Zeitfenster mittel"), ("live10_kein_fenster", "ohne Zeitfenster"),
                         ("live10", "Zeitfenster mittel")):
        s = data[name]
        m = s["mechanism"]
        rows.append({"Größe": R.size_label(s), "Zeitfenster": window,
                     "Pausen je Flottenlösung (F+E)": fmt_num(m["breaks_total"]["mean"]),
                     "davon an einer Ladesäule": f"{fmt_num(m['breaks_at_charger']['mean'])} ({fmt_num(m['share_breaks_at_charger']['mean'], 0)} %)",
                     "Lademinuten „gratis“ in der Pause": fmt_num(m["free_charge_min_FE"]["mean"], 0),
                     "Tagesruhen F+E gegen F": f"{fmt_num(m['nights_FE']['mean'], 2)} gegen {fmt_num(m['nights_F']['mean'], 2)}"})
    return pd.DataFrame(rows)


def measured_overview(data):
    """Tabelle aller Messreihen (Tab 'Messreihe'): Größe, Einstellungen, Instanzen, Mehrkosten, I, Median und Quartile, Anteil I < 0."""
    rows = []
    for name in R.series_names(data):
        s = data[name]
        o = s["overrides"]
        if o.get("c_late") is not None or "pause_paid" in o or s["tw_ref"] != "plain":
            continue
        i = R.Stat.from_dict(s["I"])
        window = "keine" if s["tw_share"] == 0 else f"{round(100 * s['tw_share'])} % der Kunden, {s['tw_width_h']:.0f} h"
        rows.append({"Größe": R.size_label(s), "Zeitfenster": window, "Ladezeit": f"{o.get('t_typ', 45.0):.0f} min",
                     "Reichweite": f"{o.get('R', 400.0):.0f} km", "Instanzen": R.count_label(s),
                     "F": fmt_band(R.Stat.from_dict(s["dF"])), "E": fmt_band(R.Stat.from_dict(s["dE"])),
                     "F+E": fmt_band(R.Stat.from_dict(s["dFE"])), "Wechselwirkung I": fmt_band(i),
                     "Median [Q1; Q3]": f"{fmt_num(i.median, 1, True)} [{fmt_num(i.q1, 1, True)}; {fmt_num(i.q3, 1, True)}]",
                     "Anteil I < 0": fmt_share(i.neg_share), "Urteil": R.VERDICT_SHORT[i.verdict()]})
    return pd.DataFrame(rows)


def live_cost_table(res):
    """Kosten und Fahrplan-Kennzahlen der vier Zellen der Live-Instanz (Tab 'Fahrplan')."""
    rows = []
    for c in C.CELLS:
        cell = res["cells"][c]
        if not cell["feasible"]:
            rows.append({"Zelle": C.CELL_LABELS[c], "Kosten": "keine zulässige Lösung"})
            continue
        m = cell["metrics"]
        rows.append({"Zelle": C.CELL_LABELS[c], "Kosten": fmt_eur(cell["total"]), "Kilometer": f"{m['km']:.0f}",
                     "Pflichtpausen": m["breaks"], "davon am Lader": m["breaks_at_charger"], "Tagesruhen": m["nights"],
                     "Ladehalte": m["charges"], "Fahrzeit (h)": fmt_num(m["drive_min"] / 60.0),
                     "Wartezeit (h)": fmt_num(m["wait_min"] / 60.0), "Verspätung (h)": fmt_num(m["late_min"] / 60.0)})
    return pd.DataFrame(rows)


def render_series_verdict(res, data):
    """Urteil der Messreihe zu den eingestellten Werten in drei Zuständen (Mittel mehr als 2 Standardfehler von 0 entfernt: billiger
    oder teurer als die Summe, sonst nicht von additiv zu unterscheiden). Der Kasten folgt der Reihe in Live-Größe (10 Kunden,
    2 Lkw), sonst der ersten passenden. Rückgabe: das Urteil ('neg', 'pos', 'none') oder None, wenn keine Reihe passt."""
    names = matching_series(res, data)
    setting = f"Ladezeit {res['charge']} min, Reichweite {res['range_km']} km, Zeitfenster {res['window']}"
    if not names:
        st.info(f"Für genau diese Einstellungen ({setting}) gibt es keine vorgerechnete Messreihe. Die gemessenen Stufen zeigen die Grafiken "
                "und Tabellen unten.")
        return None
    lines, verdicts = [], {}
    for name in names:
        s = data[name]
        i = R.Stat.from_dict(s["I"])
        verdicts[name] = i.verdict()
        lines.append(f"- {R.number_label(s)}: I = {fmt_band(i)} – {R.VERDICT_TEXT[verdicts[name]]}")
    lead = next((n for n in names if data[n]["n"] == C.SIZE_LIVE[0] and data[n]["K"] == C.SIZE_LIVE[1]), names[0])
    text = f"**Urteil der Messreihe zu Ihren Einstellungen** ({setting}):\n\n" + "\n".join(lines)
    {"neg": st.success, "pos": st.warning, "none": st.info}[verdicts[lead]](text)
    return verdicts[lead]


def cost_component_table(res):
    """Kostenarten je Zelle der Live-Instanz (EUR) und die Wechselwirkung je Kostenart."""
    rows = []
    cells = res["cells"]
    for key in C.COST_KEYS:
        v = {c: cells[c]["comps"][key] for c in C.CELLS}
        rows.append({"Kostenart": C.COST_LABELS[key], **{C.CELL_LABELS[c]: fmt_eur(v[c]) for c in C.CELLS},
                     "Wechselwirkung I": fmt_eur(v[C.CELL_FE] - v[C.CELL_F] - v[C.CELL_E] + v[C.CELL_BASE], signed=True)})
    return pd.DataFrame(rows)


def comps_I_table(data):
    """Wechselwirkung je Kostenart aus der Messreihe: 18 Kunden/3 Lkw und 10 Kunden/2 Lkw, ohne und mit Zeitfenstern (EUR ± SE)."""
    cols = (("kein_fenster", "ohne Zeitfenster"), ("basis", "Zeitfenster mittel"), ("live10_kein_fenster", "ohne Zeitfenster"),
            ("live10", "Zeitfenster mittel"))
    rows = []
    for key in C.COST_KEYS:
        row = {"Kostenart": C.COST_LABELS[key]}
        for name, window in cols:
            s = data[name]
            v = s["comps_I"][key]
            row[f"{R.size_label(s)}, {window}"] = f"{fmt_num(v['mean'], 0, True)} ± {fmt_num(v['se'], 0)} EUR"
        rows.append(row)
    return pd.DataFrame(rows)
