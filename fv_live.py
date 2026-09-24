"""Die Live-Instanz: 6 bis 12 Kunden, 2 Lkw, immer vier Zellen (ohne Regeln, F, E, F+E), gerechnet mit dem Fahrplan-Evaluator
und der Tourensuche aus fv_model / fv_evaluator / fv_search (unverändert aus der Messreihe).

Nur Standardbibliothek, kein Streamlit: `solve_live` liefert ein reines Daten-Wörterbuch (Listen, Tupel, Zahlen), das sich mit
st.cache_data zwischenspeichern lässt. Die Seed-Regel ist dieselbe wie in der Messreihe (tools/sweep.py, valid_seeds): der i-te
GÜLTIGE Seed, d. h. jeder Kunde ist mit der eingestellten Reichweite per Rundfahrt erreichbar."""
import threading
import time
from dataclasses import replace

import fv_constants as C
from fv_evaluator import Ev, plan_stats
from fv_model import INF, Cfg, is_feasible, make_geometry
from fv_search import make_instance, solve_all, total_cost


def live_cfg(charge, range_km):
    """Parameter der Live-Instanz: Standardparameter der Messreihe (Cfg(max_rl=4)) mit eingestellter Ladezeit und Reichweite."""
    return replace(Cfg(max_rl=4), t_typ=float(charge), R=float(range_km))


# ----------------------------------------------------------------------------------------------------------------
# Gültige Seeds (wie tools/sweep.py, valid_seeds)
# ----------------------------------------------------------------------------------------------------------------
_VALID = {}
_LOCK = threading.Lock()


def seed_is_valid(seed, n, K, range_km):
    """Jeder Kunde ist per Rundfahrt (Depot, Kunde, Depot) mit dieser Reichweite und den festen Ladesäulen erreichbar."""
    inst = make_geometry(seed, n, K)
    ev = Ev(inst, live_cfg(C.CHARGE_DEFAULT, range_km), 0, 1, 0)
    return all(is_feasible(ev.cost((c,))) for c in range(1, n + 1))


def valid_seeds(count, n, K, range_km):
    """Die ersten `count` gültigen Seeds (aufsteigend ab 0) für Kundenzahl n, Fahrzeuge K und Reichweite; je (n, K, Reichweite)
    wird nur einmal und nur so weit wie nötig gesucht."""
    key = (int(n), int(K), int(range_km))
    with _LOCK:
        entry = _VALID.setdefault(key, [[], 0])
        seeds, nxt = entry
        while len(seeds) < count:
            if seed_is_valid(nxt, n, K, range_km):
                seeds.append(nxt)
            nxt += 1
        entry[1] = nxt
        return list(seeds[:count])


def nth_valid_seed(index, n, K, range_km):
    """Der Seed der Instanz Nr. `index` (0-basiert) unter den gültigen Seeds."""
    return valid_seeds(int(index) + 1, n, K, range_km)[int(index)]


# ----------------------------------------------------------------------------------------------------------------
# Kennzahlen je Zelle (dieselben Formeln wie tools/sweep.py, cell_metrics, ohne Nachbewertung)
# ----------------------------------------------------------------------------------------------------------------
_SUM_KEYS = ("km", "drive_min", "nights", "rest_min", "breaks", "breaks_at_charger", "charges", "charge_km",
             "charge_min_plain", "free_charge_min", "rests_at_charger", "swaps", "wait_min", "late_min", "late_n",
             "idle_min", "pause_min")


def cell_metrics(ev, cfg, routes):
    """Summe der Fahrplan-Kennzahlen über alle Touren einer Zelle; total/oper None, wenn eine Tour unzulässig ist."""
    m = dict(km=0.0, span_min=0.0, drive_min=0.0, nights=0, rest_min=0.0, breaks=0, breaks_at_charger=0, charges=0,
             charge_km=0.0, charge_min_plain=0.0, free_charge_min=0.0, rests_at_charger=0, swaps=0, wait_min=0.0,
             late_min=0.0, late_n=0, idle_min=0.0, used=0, pause_min=0.0)
    total = 0.0
    feasible = True
    for r in routes:
        if not r:
            continue
        p = ev.plan(r)
        if p is None:
            feasible = False
            continue
        st = plan_stats(p["events"], cfg)
        total += p["cost"]
        m["used"] += 1
        m["span_min"] += st["t_end"]
        for k in _SUM_KEYS:
            m[k] += st[k]
    m["feasible"] = feasible
    m["total"] = total if feasible else None
    m["late_cost"] = cfg.c_late * m["late_min"] / 60.0
    m["oper"] = (total - m["late_cost"]) if feasible else None
    m["driver_h"] = (m["span_min"] - m["rest_min"]) / 60.0 + m["swaps"] * cfg.t_swap / 60.0
    if not cfg.pause_paid:
        m["driver_h"] -= m["pause_min"] / 60.0
    return m


def cost_components(m, cfg):
    """Kostenarten einer Zelle (EUR); ihre Summe ist der Gesamtwert der Zelle (tests/test_live.py, Zerlegung schließt)."""
    return dict(km=cfg.c_km * m["km"], fahrer=cfg.c_drv * m["driver_h"], fahrzeug=cfg.c_veh * m["span_min"] / 60.0,
                naechte=cfg.c_night * m["nights"], verspaetung=m["late_cost"])


# ----------------------------------------------------------------------------------------------------------------
# Live-Rechnung
# ----------------------------------------------------------------------------------------------------------------
def build_instance(n, charge, range_km, window, seed_index, K=C.LIVE_TRUCKS):
    """(Instanz, Parameter, tatsächlicher Seed) der Live-Einstellung."""
    cfg = live_cfg(charge, range_km)
    share, width = C.WINDOW_PARAMS[window]
    seed = nth_valid_seed(seed_index, n, K, range_km)
    inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref="plain")
    return inst, cfg, seed


def solve_live(n, charge, range_km, window, seed_index):
    """Rechnet die vier Zellen der Live-Instanz und liefert ein reines Daten-Wörterbuch:

    Instanz (Koordinaten für die Karte, Fenster, Service) und je Zelle: Touren, Fahrpläne (Ereignislisten je Lkw), Kennzahlen,
    Kostenarten, Gesamtkosten und die Kosten der regelfreien Touren unter den Regeln der Zelle ("fest", ohne Neuplanen)."""
    t0 = time.time()
    inst, cfg, seed = build_instance(n, charge, range_km, window, seed_index)
    combos = [C.CELL_COMBOS[c] for c in C.CELLS]
    out, _pool = solve_all(inst, cfg, combos, seed, restarts=C.LIVE_RESTARTS)
    base_routes = out[C.CELL_COMBOS[C.CELL_BASE]][0]
    cells = {}
    for name in C.CELLS:
        routes, cost, ev = out[C.CELL_COMBOS[name]]
        feasible = is_feasible(cost)
        cell = dict(feasible=feasible, total=cost if feasible else None, routes=[list(r) for r in routes])
        if feasible:
            m = cell_metrics(ev, cfg, routes)
            cell["metrics"] = m
            cell["comps"] = cost_components(m, cfg)
            cell["trucks"] = [dict(truck=i + 1, route=list(r), events=[tuple(e) for e in ev.plan(r)["events"]])
                              for i, r in enumerate(routes) if r]
        else:
            cell["metrics"], cell["comps"], cell["trucks"] = None, None, []
        fixed = total_cost(ev, base_routes)
        cell["fix_total"] = fixed if is_feasible(fixed) else None
        cells[name] = cell
    return dict(
        n=int(n), K=inst.K, charge=int(charge), range_km=int(range_km), window=window, seed_index=int(seed_index), seed=seed,
        tw_count=inst.tw_count, xy=[tuple(p) for p in inst.xy], stations=list(inst.stations), capacity=inst.Q,
        dem=list(inst.dem[:n + 1]), svc=list(inst.svc[:n + 1]), early=list(inst.e[:n + 1]),
        late=[None if x == INF else x for x in inst.l[:n + 1]], cells=cells, seconds=round(time.time() - t0, 1),
        c_late=cfg.c_late)
