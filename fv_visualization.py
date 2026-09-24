"""Plotly-Figuren der Fernverkehrs-Demo: Karte, Zeitstrahl je Lkw, Kostenzerlegung, Summe gegen Kombination, Wechselwirkung über eine
Achse, Zerlegung der Wechselwirkung, fest gegen neu geplant, Annahmen-Vergleich.

Konventionen des Portfolios: Achsen `fixedrange` (Touch-Scrollen), Vorlage plotly_white, Legende unten, Farben über alle Figuren
konsistent. Plotly wird erst in den Funktionen importiert, damit die reine Rechnung ohne Plotly testbar bleibt."""
import fv_constants as C
import fv_results as R
import fv_schedule as S

LEGEND_BOTTOM = dict(orientation="h", yref="container", yanchor="bottom", y=0.0, x=0)


def _lock_axes(fig):
    """Achsen fest: verhindert Zoomen und Verschieben per Touch, damit die Seite scrollbar bleibt (Hover bleibt)."""
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _de(v, digits=1, sign=False):
    text = f"{v:+.{digits}f}" if sign else f"{v:.{digits}f}"
    return text.replace(".", ",")


def _hours(minutes):
    return _de(minutes / 60.0)


# ---------------------------------------------------------------------------------------------------
# Karte
# ---------------------------------------------------------------------------------------------------
def route_map_figure(res, cell):
    """Depot, Kunden, Ladesäulen und die Touren der Zelle (Linien in Fahrplanreihenfolge über Kunden und Ladehalte)."""
    import plotly.graph_objects as go

    xy, n = res["xy"], res["n"]
    fig = go.Figure()
    data = res["cells"][cell]
    # Ladesäulen (alle, blass) und die genutzten (Ladehalte, kräftig, nach Art)
    stations = res["stations"]
    fig.add_trace(go.Scatter(
        x=[xy[s][0] for s in stations], y=[xy[s][1] for s in stations], mode="markers", name="Ladesäule",
        marker=dict(symbol="square", size=8, color="#2e7d4f", opacity=0.45),
        text=[S.place_name(s, n) for s in stations], hovertemplate="%{text}<extra></extra>"))
    # Touren
    for t in data["trucks"]:
        nodes = S.route_nodes(t["events"])
        color = C.TRUCK_COLORS[(t["truck"] - 1) % len(C.TRUCK_COLORS)]
        fig.add_trace(go.Scatter(
            x=[xy[i][0] for i in nodes], y=[xy[i][1] for i in nodes], mode="lines", name=f"Lkw {t['truck']}",
            line=dict(color=color, width=2), hoverinfo="skip"))
    used = {}
    for t in data["trucks"]:
        for s, kind in S.charging_stops(t["events"]):
            used.setdefault(s, []).append({"plain": "Laden", "break": "Laden in der Pause", "rest": "Tagesruhe am Lader"}[kind])
    if used:
        fig.add_trace(go.Scatter(
            x=[xy[s][0] for s in used], y=[xy[s][1] for s in used], mode="markers", name="Ladehalt",
            marker=dict(symbol="square", size=11, color="#2e7d4f", line=dict(color="white", width=1)),
            text=[f"{S.place_name(s, n)}: " + ", ".join(v) for s, v in used.items()], hovertemplate="%{text}<extra></extra>"))
    # Kunden (Ring = mit Zeitfenster)
    early, late = res["early"], res["late"]
    has_tw = [late[c] is not None for c in range(1, n + 1)]
    hover = []
    for c in range(1, n + 1):
        text = f"Kunde {c}: Bedarf {res['dem'][c]}, Service {res['svc'][c]:.0f} min"
        if late[c] is not None:
            text += f"<br>Zeitfenster {_hours(early[c])} bis {_hours(late[c])} h nach Abfahrt"
        hover.append(text)
    fig.add_trace(go.Scatter(
        x=[xy[c][0] for c in range(1, n + 1)], y=[xy[c][1] for c in range(1, n + 1)], mode="markers+text",
        text=[str(c) for c in range(1, n + 1)], textposition="top center", textfont=dict(size=10),
        name="Kunde (Ring = mit Zeitfenster)", hovertext=hover, hoverinfo="text",
        marker=dict(size=9, color="#4b5d75", line=dict(color=["#e0a800" if w else "#4b5d75" for w in has_tw],
                                                        width=[3 if w else 0 for w in has_tw]))))
    fig.add_trace(go.Scatter(x=[xy[0][0]], y=[xy[0][1]], mode="markers", name="Depot",
                             marker=dict(symbol="diamond", size=14, color=C.COMBO_COLOR, line=dict(color="white", width=1)),
                             hovertemplate="Depot<extra></extra>"))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT + 60, margin=dict(t=20, b=90, l=10, r=10),
                      legend=LEGEND_BOTTOM, xaxis=dict(range=[-30, 830], title="km"),
                      yaxis=dict(range=[-30, 830], scaleanchor="x", scaleratio=1, title="km"))
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Zeitstrahl je Lkw
# ---------------------------------------------------------------------------------------------------
def timeline_figure(res, cell):
    """Ein Balken je Ereignis, eine Zeile je Lkw: Fahrt, Service, Warten, Pause, Laden, Laden in der Pause, Tagesruhe."""
    import plotly.graph_objects as go

    n = res["n"]
    trucks = res["cells"][cell]["trucks"]
    per_kind = {}
    for t in trucks:
        label = f"Lkw {t['truck']}"
        for b in S.bars(t["events"], n):
            key = (b["art"], b["late"] > 1e-9)
            d = per_kind.setdefault(key, dict(x=[], base=[], y=[], text=[]))
            d["x"].append(b["t1"] - b["t0"])
            d["base"].append(b["t0"])
            d["y"].append(label)
            d["text"].append(f"{b['text']}<br>{_de(b['t0'], 1)} bis {_de(b['t1'], 1)} h nach Abfahrt")
    fig = go.Figure()
    order = ["drive", "serve", "wait", "break", "charge", "charge_break", "rest"]
    for art in order:
        for late in (False, True):
            d = per_kind.get((art, late))
            if not d:
                continue
            name = C.EVENT_NAMES[art] + (", verspätet" if late else "")
            fig.add_trace(go.Bar(
                x=d["x"], base=d["base"], y=d["y"], orientation="h", name=name, hovertext=d["text"], hoverinfo="text",
                marker=dict(color=C.EVENT_COLORS[art], line=dict(color="#c0392b" if late else "white", width=2.5 if late else 0.5))))
    total_h = max([b["t1"] for t in trucks for b in S.bars(t["events"], n)] + [1.0])
    for day in range(1, int(total_h // 24) + 1):
        fig.add_vline(x=24 * day, line=dict(color="#9aa5b4", width=1, dash="dot"))
    fig.update_layout(template="plotly_white", height=max(C.CHART_HEIGHT - 120, 150 + 60 * len(trucks)), barmode="overlay",
                      margin=dict(t=20, b=90), legend=LEGEND_BOTTOM, xaxis_title="Stunden seit Abfahrt",
                      bargap=0.25)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(rangemode="tozero")
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Kostenzerlegung der Live-Instanz
# ---------------------------------------------------------------------------------------------------
def cost_breakdown_figure(res):
    """Gestapelte Kostenarten je Zelle (EUR), darüber die Gesamtkosten. Unzulässige Zellen fehlen."""
    import plotly.graph_objects as go

    cells = [c for c in C.CELLS if res["cells"][c]["feasible"]]
    xs = [C.CELL_SHORT[c] for c in cells]
    fig = go.Figure()
    for key in C.COST_KEYS:
        fig.add_trace(go.Bar(
            x=xs, y=[res["cells"][c]["comps"][key] for c in cells], name=C.COST_LABELS[key], marker_color=C.COST_COLORS[key],
            hovertemplate=f"{C.COST_LABELS[key]}: %{{y:,.0f}} EUR<extra></extra>"))
    for c, x in zip(cells, xs):
        fig.add_annotation(x=x, y=res["cells"][c]["total"], text=f"{res['cells'][c]['total']:,.0f} EUR".replace(",", "."),
                           showarrow=False, yshift=12, font=dict(size=11))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT, barmode="stack", margin=dict(t=30, b=70),
                      legend=LEGEND_BOTTOM, yaxis_title="Kosten der Flottenlösung (EUR)")
    return _lock_axes(fig)


def fix_vs_replanned_figure(res):
    """Live: Mehrkosten von F, E und F+E in % der regelfreien Kosten - regelfreie Touren nachbewertet (fest) gegen neu geplant."""
    import plotly.graph_objects as go

    base = res["cells"][C.CELL_BASE]["total"]
    cells = [c for c in (C.CELL_F, C.CELL_E, C.CELL_FE) if res["cells"][c]["feasible"]]
    xs = [C.CELL_LABELS[c] for c in cells]
    fixed = [None if res["cells"][c]["fix_total"] is None else 100.0 * (res["cells"][c]["fix_total"] - base) / base for c in cells]
    replanned = [100.0 * (res["cells"][c]["total"] - base) / base for c in cells]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=xs, y=fixed, name="feste Touren nachbewertet", marker_color=C.BASE_COLOR,
                         text=["nicht fahrbar" if v is None else f"{_de(v, 1, True)} %" for v in fixed], textposition="outside",
                         hovertemplate="%{x}, feste Touren: %{y:+.1f} %<extra></extra>"))
    fig.add_trace(go.Bar(x=xs, y=replanned, name="neu geplant", marker_color=C.SIZE_COLORS["10/2"],
                         text=[f"{_de(v, 1, True)} %" for v in replanned], textposition="outside",
                         hovertemplate="%{x}, neu geplant: %{y:+.1f} %<extra></extra>"))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT, barmode="group", margin=dict(t=30, b=70),
                      legend=LEGEND_BOTTOM, yaxis_title="Mehrkosten gegenüber regelfreier Tour (%)")
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Kernabschnitt (vorgerechnet)
# ---------------------------------------------------------------------------------------------------
def sum_vs_combo_figure(data):
    """Mehrkosten von Fahrerregeln und Elektro allein (gestapelt = Summe) gegenüber der gemessenen Kombination, je Größe und
    Fensterstufe. Balkenbeschriftung: Summe und Kombination in % der regelfreien Kosten."""
    import plotly.graph_objects as go

    rows = R.sum_rows(data)
    xs = [f"{r['window']}<br>{r['size']} (Kunden/Lkw)" for r in rows]
    fig = go.Figure()
    for j, (key, label) in enumerate((("dF", "Fahrerregeln allein"), ("dE", "Elektro allein"))):
        fig.add_trace(go.Bar(
            x=xs, y=[getattr(r[key], "mean") for r in rows], name=label, marker_color=C.SUM_COLORS[j], offsetgroup="summe",
            text=[_de(r[key].mean) for r in rows], textposition="inside", textfont=dict(color="white", size=11),
            hovertemplate=f"{label}: %{{y:+.1f}} %<extra></extra>"))
    fig.add_trace(go.Bar(
        x=xs, y=[r["dFE"].mean for r in rows], name="beides, gemessen", marker_color=C.COMBO_COLOR, offsetgroup="beides",
        error_y=dict(type="data", array=[r["dFE"].se for r in rows], visible=True),
        text=[f"{_de(r['dFE'].mean)}" for r in rows], textposition="inside", textfont=dict(color="white", size=11),
        hovertemplate="beides gemessen: %{y:+.1f} %<extra></extra>"))
    for x, r in zip(xs, rows):
        fig.add_annotation(x=x, y=max(r["dF"].mean + r["dE"].mean, r["dFE"].mean), text=f"Summe {_de(r['dF'].mean + r['dE'].mean)} %",
                           showarrow=False, yshift=14, xshift=-28, font=dict(size=10))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT + 40, barmode="relative", margin=dict(t=30, b=90),
                      legend=LEGEND_BOTTOM, yaxis_title="Mehrkosten gegenüber regelfreier Tour (%)")
    return _lock_axes(fig)


def axis_figure(rows, axis):
    """Wechselwirkung I (in % der regelfreien Kosten, Mittel ± Standardfehler) über die gewählte Achse, je Gruppe und Größe eine Reihe.
    Unter null ist die Kombination billiger als die Summe der Einzelkosten, über null teurer."""
    import plotly.graph_objects as go

    levels = list(dict.fromkeys(r["level"] for r in rows))
    groups = list(dict.fromkeys(r["group"] for r in rows))
    fig = go.Figure()
    for group in groups:
        in_group = [r for r in rows if r["group"] == group]
        hatched = len(groups) > 1 and group == groups[0]          # bei zwei Gruppen: die erste (ohne Zeitfenster) schraffiert
        pattern = dict(shape="/", fgcolor="white") if hatched else None
        one_per_level = len({r["level"] for r in in_group}) == len(in_group)
        # Eine Reihe je Größe; hat jede Stufe nur eine Messreihe (Achse Fahrzeuge: je Stufe eine eigene Größe), eine gemeinsame Reihe
        series = [(group, in_group)] if one_per_level else [
            (f"{group}, {size} (Kunden/Lkw)", [r for r in in_group if r["size"] == size]) for size in dict.fromkeys(r["size"] for r in in_group)]
        for name, sub in series:
            colors = [C.SIZE_COLORS.get(r["size"], C.COMBO_COLOR) for r in sub]
            fig.add_trace(go.Bar(
                x=[r["level"] for r in sub], y=[r["stat"].mean for r in sub], name=name,
                marker=dict(color=colors[0] if len(set(colors)) == 1 else colors, pattern=pattern),       # Muster verträgt nur eine Farbe je Reihe
                error_y=dict(type="data", array=[r["stat"].se for r in sub], visible=True),
                customdata=[[r["count"], r["size_label"]] for r in sub],
                hovertemplate="%{x}: I = %{y:+.1f} %<br>%{customdata[1]}, %{customdata[0]}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#5b6b80", width=1))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT + 30, barmode="group", margin=dict(t=30, b=100),
                      legend=LEGEND_BOTTOM, yaxis_title="Wechselwirkung I (% der regelfreien Kosten)", xaxis_title=axis)
    fig.update_xaxes(categoryorder="array", categoryarray=levels)
    return _lock_axes(fig)


def components_figure(data, window):
    """Zerlegung der Wechselwirkung nach Kostenart (in % der regelfreien Kosten, Mittel ± Standardfehler), beide Größen.
    window: 'mittel' (mit Zeitfenstern) oder 'keine'."""
    import plotly.graph_objects as go

    names = {"keine": (("live10_kein_fenster", "10/2"), ("kein_fenster", "18/3")), "mittel": (("live10", "10/2"), ("basis", "18/3"))}[window]
    fig = go.Figure()
    for name, size in names:
        s = data[name]
        base = s["base_eur"]["mean"]
        fig.add_trace(go.Bar(
            x=[C.COST_LABELS[k] for k in C.COST_KEYS], y=[100.0 * s["comps_I"][k]["mean"] / base for k in C.COST_KEYS],
            name=f"{R.size_label(s)} ({R.count_label(s)})", marker_color=C.SIZE_COLORS[size],
            error_y=dict(type="data", array=[100.0 * s["comps_I"][k]["se"] / base for k in C.COST_KEYS], visible=True),
            text=[_de(100.0 * s["comps_I"][k]["mean"] / base, 1, True) for k in C.COST_KEYS], textposition="outside",
            hovertemplate="%{x}: %{y:+.1f} % der regelfreien Kosten<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#5b6b80", width=1))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT, barmode="group", margin=dict(t=30, b=90),
                      legend=LEGEND_BOTTOM, yaxis_title="Anteil an der Wechselwirkung (% der regelfreien Kosten)")
    return _lock_axes(fig)


def assumption_figure(data, kind):
    """Annahmen-Vergleich: kind 'pause' (Pausen bezahlt gegen unbezahlt) oder 'strafe' (Verspätungsstrafe 20 / 40 / 80 EUR/h)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    if kind == "pause":
        cmp_ = data["_ap0_c_unbezahlte_pausen"]
        groups = (("kein_fenster_45min", "ohne Zeitfenster"), ("basis_45min_mit_fenster", "Zeitfenster mittel"))
        for label, key, color in (("Pausen bezahlt (Grundannahme)", "I_paid", C.SIZE_COLORS["18/3"]), ("Pausen unbezahlt", "I_unpaid", "#7d5ba6")):
            fig.add_trace(go.Bar(
                x=[g for _, g in groups], y=[cmp_[k][key]["mean"] for k, _ in groups], name=label, marker_color=color,
                error_y=dict(type="data", array=[cmp_[k][key]["se"] for k, _ in groups], visible=True),
                text=[_de(cmp_[k][key]["mean"], 1, True) for k, _ in groups], textposition="outside",
                hovertemplate=f"{label}: I = %{{y:+.1f}} %<extra></extra>"))
    else:
        pen = data["_ap0_d_verspaetungsstrafe"]
        levels = ("20", "40", "80")
        fig.add_trace(go.Bar(
            x=[f"{lv} EUR/h" for lv in levels], y=[pen[lv]["I"]["mean"] for lv in levels], name="Wechselwirkung I gesamt",
            marker_color=C.COST_COLORS["verspaetung"], error_y=dict(type="data", array=[pen[lv]["I"]["se"] for lv in levels], visible=True),
            text=[_de(pen[lv]["I"]["mean"], 1, True) for lv in levels], textposition="outside",
            hovertemplate="Strafe %{x}: I = %{y:+.1f} %<extra></extra>"))
        fig.add_trace(go.Bar(
            x=[f"{lv} EUR/h" for lv in levels], y=[pen[lv]["I_oper"]["mean"] for lv in levels], name="nur Betriebskosten (ohne Verspätung)",
            marker_color=C.COST_COLORS["km"], error_y=dict(type="data", array=[pen[lv]["I_oper"]["se"] for lv in levels], visible=True),
            text=[_de(pen[lv]["I_oper"]["mean"], 1, True) for lv in levels], textposition="outside",
            hovertemplate="Strafe %{x}: I (Betrieb) = %{y:+.1f} %<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#5b6b80", width=1))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT - 60, barmode="group", margin=dict(t=30, b=90),
                      legend=LEGEND_BOTTOM, yaxis_title="Wechselwirkung I (% der regelfreien Kosten)")
    return _lock_axes(fig)
