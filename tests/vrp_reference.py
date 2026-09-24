"""Kopie der Bewertungsfunktionen der vrp_demo (vrp_evaluation.py: route_cost, route_timeline, evaluate_route), unverändert
bis auf die eingesetzte Konstante EPS (dort aus vrp_constants.py). Bewusst eine KOPIE und kein Import über Repogrenzen: der
Grenzfall "alle Regeln aus == Bewertung der vrp_demo" (tests/fv_checks.py, check_alloff_equals_vrp_demo) prüft, dass die
Fahrplan-Auswertung dieser Demo ohne Regeln genau die Bewertung des Basismodells liefert.

vrp_demo indiziert die Stopps 0-basiert (Knoten s + 1, Depot = 0)."""

EPS = 1e-9


def route_cost(route, D):
    """Distanz einer einzelnen Tour: Depot -> Stopps in Reihenfolge -> Depot."""
    if not route:
        return 0.0
    nodes = [0] + [s + 1 for s in route] + [0]
    return sum(D[nodes[k]][nodes[k + 1]] for k in range(len(nodes) - 1))


def route_timeline(route, D, earliest, latest, service):
    """Simuliert Ankunft/Wartezeit/Start je Stopp entlang einer Tour und
    markiert Zeitfenster-Verletzungen (Ankunft nach dem spätesten Start)."""
    t = 0.0
    prev = 0
    timeline = []
    for s in route:
        node = s + 1
        travel = D[prev][node]
        arrival = t + travel
        start = max(arrival, earliest[s])
        violation = start > latest[s] + EPS
        timeline.append(
            {"stop": s, "arrival": arrival, "start": start, "wait": start - arrival, "violation": violation}
        )
        t = start + service[s]
        prev = node
    return timeline


def evaluate_route(route, D, earliest, latest, service, tw_enabled):
    """Distanz und Anzahl Zeitfenster-Verletzungen einer Tour (Verletzungen
    nur berechnet, wenn tw_enabled aktiv ist - spart unnötige Arbeit sonst)."""
    dist = route_cost(route, D)
    if not tw_enabled or not route:
        return dist, 0, []
    timeline = route_timeline(route, D, earliest, latest, service)
    violations = sum(1 for t in timeline if t["violation"])
    return dist, violations, timeline
