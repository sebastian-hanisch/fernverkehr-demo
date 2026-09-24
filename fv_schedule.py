"""Fahrpläne lesbar machen: Halteliste (Zeile je Ereignis), Balken für den Zeitstrahl, Knotenfolge für die Karte.

Reine Funktionen auf den Ereignislisten des Evaluators (fv_evaluator.Ev.plan): jedes Ereignis ist ein Tupel
  ("drive", t0, t1, km)                       Fahrt
  ("serve", t0, t1, kunde, verspaetung_min)   Service beim Kunden (ab t0, nach Warten)
  ("wait", t0, t1, kunde)                     Warten auf das Öffnen des Zeitfensters
  ("break", t0, t1, "road" | "cust")          Pflichtpause (45 min) unterwegs oder beim Kunden
  ("rest", t0, t1, "road" | "cust")           Tagesruhe (11 h) unterwegs oder beim Kunden
  ("charge", t0, t1, station, km, "plain" | "break" | "rest")   Laden (allein, in der Pause, in der Tagesruhe)
Zeiten in Minuten seit der Abfahrt (t = 0), alle Lkw starten gleichzeitig."""


def fmt_clock(minutes):
    """Zeit seit Abfahrt als 'Tag 2, 03:15' (Tag 1 beginnt bei 0)."""
    m = int(round(minutes))
    return f"Tag {m // 1440 + 1}, {(m % 1440) // 60:02d}:{m % 60:02d}"


def fmt_duration(minutes):
    m = int(round(minutes))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def place_name(node, n_customers):
    """Depot (0), Kunden (1..n), Ladesäulen (danach, von 1 an gezählt)."""
    if node == 0:
        return "Depot"
    if node <= n_customers:
        return f"Kunde {node}"
    return f"Ladesäule {node - n_customers}"


def _destinations(events):
    """Zu jedem Ereignis der nächste Ort, an dem der Lkw hält (Kunde oder Ladesäule, sonst das Depot)."""
    dest = [0] * len(events)
    nxt = 0
    for i in range(len(events) - 1, -1, -1):
        if events[i][0] in ("serve", "charge"):
            nxt = events[i][3]
        dest[i] = nxt
    return dest


def bar_kind(event):
    """Farbklasse des Ereignisses im Zeitstrahl (fv_constants.EVENT_COLORS)."""
    kind = event[0]
    if kind == "charge":
        return {"plain": "charge", "break": "charge_break", "rest": "rest"}[event[5]]
    return kind


def halteliste(events, n_customers):
    """Zeilen der Halteliste: von, bis, Ort, Ereignis, Einzelheit, Dauer."""
    rows = []
    dest = _destinations(events)
    for e, d in zip(events, dest):
        kind, t0, t1 = e[0], e[1], e[2]
        if kind == "drive":
            ort, name, detail = f"unterwegs nach {place_name(d, n_customers)}", "Fahrt", f"{e[3]:.0f} km"
        elif kind == "serve":
            ort, name = place_name(e[3], n_customers), "Service"
            detail = "pünktlich" if e[4] <= 1e-9 else f"{e[4]:.0f} min verspätet"
        elif kind == "wait":
            ort, name, detail = place_name(e[3], n_customers), "Warten", "bis das Zeitfenster öffnet"
        elif kind == "break":
            at_cust = e[3] == "cust"
            ort = place_name(d, n_customers) if at_cust else f"unterwegs nach {place_name(d, n_customers)}"
            name, detail = "Pflichtpause", "45 min am Stück"
        elif kind == "rest":
            at_cust = e[3] == "cust"
            ort = place_name(d, n_customers) if at_cust else f"unterwegs nach {place_name(d, n_customers)}"
            name, detail = "Tagesruhe", "11 h, Fahrzeug steht"
        elif kind == "charge":
            ort = place_name(e[3], n_customers)
            name = {"plain": "Laden", "break": "Laden in der Pause", "rest": "Tagesruhe am Lader"}[e[5]]
            detail = f"+{e[4]:.0f} km Reichweite"
        else:                                          # pragma: no cover - der Evaluator kennt nur die Ereignisse oben
            raise ValueError(f"unbekanntes Ereignis {kind!r}")
        rows.append(dict(von=fmt_clock(t0), bis=fmt_clock(t1), ort=ort, ereignis=name, einzelheit=detail,
                         dauer=fmt_duration(t1 - t0), minuten=t1 - t0, art=bar_kind(e)))
    return rows


def bars(events, n_customers):
    """Balken des Zeitstrahls: (Art, Start h, Ende h, Beschriftung, Verspätung in min)."""
    out = []
    for row, e in zip(halteliste(events, n_customers), events):
        late = e[4] if e[0] == "serve" else 0.0
        out.append(dict(art=row["art"], t0=e[1] / 60.0, t1=e[2] / 60.0, text=f"{row['ereignis']}: {row['ort']} ({row['einzelheit']})",
                        late=late))
    return out


def route_nodes(events):
    """Knotenfolge der Karte: Depot, dann jeder Kunde und jede Ladesäule in Fahrplanreihenfolge, Depot."""
    nodes = [0]
    for e in events:
        if e[0] in ("serve", "charge"):
            nodes.append(e[3])
    nodes.append(0)
    return nodes


def charging_stops(events):
    """Ladehalte (Ladesäule, Art) in Reihenfolge: Art 'plain', 'break' oder 'rest'."""
    return [(e[3], e[5]) for e in events if e[0] == "charge"]


def event_counts(events):
    """Zahl der Pausen (auch am Lader), Tagesruhen (auch am Lader) und Ladehalte in einem Fahrplan."""
    breaks = sum(1 for e in events if e[0] == "break" or (e[0] == "charge" and e[5] == "break"))
    rests = sum(1 for e in events if e[0] == "rest" or (e[0] == "charge" and e[5] == "rest"))
    charges = sum(1 for e in events if e[0] == "charge")
    return dict(breaks=breaks, rests=rests, charges=charges)
