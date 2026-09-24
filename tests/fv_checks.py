"""Korrektheits-Checks für das Fahrplan-Modell (Evaluator, Regeln, Suche): Übernahme von check.py aus messreihe_fernverkehr.

Die Prüfungen sind bis auf die Importe und die Parametrisierung UNVERÄNDERT. Jede Funktion hat als Standardparameter die
volle Fassung der Messreihe (das Bau-Gate: tools/check_full.py, einmal lokal, 3,9 Mio. simulierte Pläne); tests/test_checks.py
ruft dieselben Funktionen mit verkleinerten Parametern auf (CI). Deterministisch, nur Standardbibliothek.

  1. alle Regeln aus == Bewertung der vrp_demo (tests/vrp_reference.py, Kopie): Distanz, Zeitlinie, Verletzungen, Kosten
  2. Brute-Force-Referenz: Plan-Enumeration mit einem UNABHÄNGIGEN Tick-Simulator (Mini-Instanzen)
  3. Fahrplan-Validator: Lenk-/Ruhezeit, Akku, Reihenfolge; Kosten aus Ereignissen == DP-Kosten
  4. Schalter-greifen-Tests (F, E, S je einzeln, inkl. "R groß == E aus", "F aus => S wirkungslos", unbezahlte Pause)
  5. Monotonie: mehr Regeln kosten nie weniger; eps-Dominanz vs. exakt
  6. Suche: gültige Lösung, Kapazität, Determinismus, LS verbessert, Kosten == Summe der Pläne
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import replace

import fv_evaluator
import vrp_reference as vrp
from fv_evaluator import Ev, cost_from_events, plan_stats
from fv_model import INF, Cfg, Inst, is_feasible
from fv_search import make_instance, savings_routes, solve, solve_all, total_cost


# ----------------------------------------------------------------------------------------------------------------
# 1. Grenzfall: alle Schalter aus == vrp_demo
# ----------------------------------------------------------------------------------------------------------------
def check_alloff_equals_vrp_demo(n_inst: int = 25) -> None:
    cfg = Cfg()
    v = cfg.speed / 60.0
    n_routes = 0
    for seed in range(n_inst):
        inst = make_instance(seed, n=14, K=3, tw_share=0.7, tw_width_h=5.0)
        ev = Ev(inst, cfg)
        n = inst.n
        Dkm = [row[:n + 1] for row in inst.D[:n + 1]]
        Dmin = [[x / v for x in row] for row in Dkm]
        earliest = [inst.e[c] for c in range(1, n + 1)]
        latest = [inst.l[c] for c in range(1, n + 1)]
        service = [inst.svc[c] for c in range(1, n + 1)]
        rng = random.Random(seed)
        for _ in range(6):
            perm = rng.sample(range(1, n + 1), rng.randint(2, 8))
            r0 = [c - 1 for c in perm]                      # vrp_demo indiziert Stopps 0-basiert
            dist_v = vrp.route_cost(r0, Dkm)
            tl = vrp.route_timeline(r0, Dmin, earliest, latest, service)
            viol_v = sum(1 for x in tl if x["violation"])
            plan = ev.plan(perm)
            st = plan_stats(plan["events"], cfg)
            serves = [e for e in plan["events"] if e[0] == "serve"]
            assert abs(st["km"] - dist_v) < 1e-6, (seed, st["km"], dist_v)
            for e, x in zip(serves, tl):
                assert abs((e[1]) - x["start"]) < 1e-6, (seed, e, x)         # Servicebeginn identisch
                assert (e[4] > 1e-9) == x["violation"], (seed, e, x)
            assert st["late_n"] == viol_v
            # Endzeit wie in vrp_demo: letzter Servicebeginn + Service + Rueckfahrt
            last = tl[-1]
            t_end_v = last["start"] + service[last["stop"]] + Dmin[last["stop"] + 1][0]
            assert abs(st["t_end"] - t_end_v) < 1e-6
            late_min_v = sum(max(0.0, x["start"] - latest[x["stop"]]) for x in tl)
            rate = (cfg.c_drv + cfg.c_veh) / 60.0
            expect = cfg.c_km * dist_v + rate * t_end_v + cfg.c_late * late_min_v / 60.0
            assert abs(ev.cost(perm) - expect) < 1e-6, (seed, ev.cost(perm), expect)
            # reine Distanzgewichtung == route_cost exakt
            cfg_d = replace(cfg, c_km=1.0, c_drv=0.0, c_veh=0.0, c_late=0.0)
            assert abs(Ev(inst, cfg_d).cost(perm) - dist_v) < 1e-9
            n_routes += 1
    print(f"alle-aus == vrp_demo: {n_routes} Touren auf {n_inst} Instanzen; Distanz, Servicebeginn, Verletzungen, "
          f"Endzeit und Kosten stimmen ueberein")


# ----------------------------------------------------------------------------------------------------------------
# Unabhaengiger Tick-Simulator + Brute-Force
# ----------------------------------------------------------------------------------------------------------------
def sim_plan(inst: Inst, cfg: Cfg, route, legs, cust, F: bool, E: bool, tick_min: float = 5.0):
    """Simuliert einen VORGEGEBENEN Plan (legs[k] = [(w, art, B)], cust[i] = Aktion) in 5-min-Ticks.
    Liefert (kosten, ereignisse) oder None (unzulaessig). Bewusst anders gebaut als der DP in fv_evaluator.py."""
    D = inst.D
    v = cfg.speed / 60.0
    rate = (cfg.c_drv + cfg.c_veh) / 60.0
    rveh = cfg.c_veh / 60.0
    tk = cfg.t_typ / cfg.typ_share / cfg.R
    bc = rate * cfg.brk if cfg.pause_paid else rveh * cfg.brk          # Kosten einer Pflichtpause
    nodes = [0] + list(route) + [0]
    st = dict(t=0.0, dc=0.0, dd=0.0, b=cfg.R if E else 0.0, cost=0.0)
    ev = []

    def drive(dist):
        if E:
            st["b"] -= dist
            if st["b"] < -1e-7:
                return False
        st["cost"] += cfg.c_km * dist
        rem = dist / v
        while rem > 1e-9:
            if F and st["dd"] >= cfg.day - 1e-9:
                ev.append(("rest", st["t"], st["t"] + cfg.rest, "road"))
                st["t"] += cfg.rest
                st["cost"] += rveh * cfg.rest + cfg.c_night
                st["dc"] = st["dd"] = 0.0
                continue
            if F and st["dc"] >= cfg.blk - 1e-9:
                ev.append(("break", st["t"], st["t"] + cfg.brk, "road"))
                st["t"] += cfg.brk
                st["cost"] += bc
                st["dc"] = 0.0
                continue
            tick = min(tick_min, rem)
            if F:
                tick = min(tick, cfg.blk - st["dc"], cfg.day - st["dd"])
            ev.append(("drive", st["t"], st["t"] + tick, tick * v))
            st["t"] += tick
            st["cost"] += rate * tick
            st["dc"] += tick
            st["dd"] += tick
            rem -= tick
        return True

    for k in range(len(nodes) - 1):
        pos, target = nodes[k], nodes[k + 1]
        for (w, kind, B) in legs[k]:
            if not drive(D[pos][w]):
                return None
            pos = w
            if kind == "swap":
                d = cfg.t_swap
                ev.append(("swap", st["t"], st["t"] + d, w))
                st["t"] += d
                st["cost"] += rate * d + cfg.c_drv * d / 60.0 + cfg.c_swap + cfg.c_ret * D[w][0]
                st["dc"] = st["dd"] = 0.0
            else:
                b_in = st["b"]
                if B is None or B > cfg.R + 1e-9 or (kind != "rest" and B <= b_in + 1e-9):
                    return None
                if kind == "plain":
                    d = (B - b_in) * tk
                    ev.append(("charge", st["t"], st["t"] + d, w, B - b_in, "plain"))
                    st["t"] += d
                    st["cost"] += rate * d
                elif kind == "break":
                    d = max(cfg.brk, (B - b_in) * tk)
                    ev.append(("charge", st["t"], st["t"] + d, w, B - b_in, "break"))
                    st["t"] += d
                    st["cost"] += rate * d if cfg.pause_paid else bc + rate * (d - cfg.brk)
                    st["dc"] = 0.0
                elif kind == "rest":
                    B = cfg.R
                    ev.append(("charge", st["t"], st["t"] + cfg.rest, w, B - b_in, "rest"))
                    st["t"] += cfg.rest
                    st["cost"] += rveh * cfg.rest + cfg.c_night
                    st["dc"] = st["dd"] = 0.0
                st["b"] = B
        if not drive(D[pos][target]):
            return None
        if target != 0:
            act = cust[k]
            if act == "break":
                ev.append(("break", st["t"], st["t"] + cfg.brk, "cust"))
                st["t"] += cfg.brk
                st["cost"] += bc
                st["dc"] = 0.0
            elif act == "rest":
                ev.append(("rest", st["t"], st["t"] + cfg.rest, "cust"))
                st["t"] += cfg.rest
                st["cost"] += rveh * cfg.rest + cfg.c_night
                st["dc"] = st["dd"] = 0.0
            start = max(st["t"], inst.e[target])
            if start > st["t"] + 1e-9:
                ev.append(("wait", st["t"], start, target))
            late = max(0.0, start - inst.l[target])
            st["cost"] += rate * (start - st["t"] + inst.svc[target]) + cfg.c_late * late / 60.0
            ev.append(("serve", start, start + inst.svc[target], target, late))
            st["t"] = start + inst.svc[target]
    return st["cost"], ev


def mini_instance(seed: int, n: int = 2, ns: int = 3, nr: int = 1, unit: float = 5.0) -> Inst:
    """Kleine Instanz fuer die Enumeration; Distanzen auf `unit` km gerundet (Gitter der Ladeumfaenge)."""
    rng = random.Random(seed * 13 + 5)
    m = 1 + n + ns + nr
    xy = [(rng.uniform(20, 100), rng.uniform(20, 100)) for _ in range(m)]
    D = [[0.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(i + 1, m):
            d = max(unit, unit * round(math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1]) / unit))
            D[i][j] = D[j][i] = d
    e = [0.0] * m
    l = [INF] * m
    for c in range(1, n + 1):
        if rng.random() < 0.8:
            e[c] = float(rng.randint(40, 160))
            l[c] = e[c] + float(rng.randint(20, 90))
    svc = [0.0] + [float(rng.randint(10, 30)) for _ in range(n)] + [0.0] * (ns + nr)
    return Inst(n=n, K=1, Q=100.0, xy=xy, ns=ns, nr=nr, dem=[0] + [1] * n + [0] * (ns + nr), e=e, l=l, svc=svc, D=D)


MINI_CFG = Cfg(speed=60.0, blk=90.0, day=180.0, brk=30.0, rest=240.0, R=100.0, t_typ=36.0, typ_share=0.6,
               t_swap=15.0, max_detour=1e9, max_st=10, max_rl=10, eps_g=0.0, eps_t=0.0, eps_c=0.0, eps_b=0.0)


def brute_best(inst: Inst, cfg: Cfg, route, F: bool, E: bool, S: bool, chain: int = 1, step: float = 5.0,
               tick_min: float = 5.0):
    """Beste Kosten ueber alle Plaene mit <= `chain` Waypoints je Leg, Ladeumfang auf 5-km-Gitter."""
    S = S and F
    nodes = [0] + list(route) + [0]
    wp = []
    if E:
        wp += [(s, "st") for s in inst.stations]
    if S:
        wp += [(s, "rl") for s in inst.relays]
    levels = [step * i for i in range(1, int(cfg.R / step) + 1)]
    visit_opts = []
    for (w, typ) in wp:
        if typ == "rl":
            visit_opts.append([(w, "swap", None)])
        else:
            o = [(w, "plain", B) for B in levels]
            if F:
                o += [(w, "break", B) for B in levels] + [(w, "rest", cfg.R)]
            visit_opts.append(o)
    seqs = [()]
    for c in range(1, chain + 1):
        for idx in itertools.permutations(range(len(wp)), c):
            for combo in itertools.product(*[visit_opts[i] for i in idx]):
                seqs.append(tuple(combo))
    acts = ["direct"] + (["break", "rest"] if F else [])
    best, best_plan = INF, None
    n_plans = 0
    for legs in itertools.product(seqs, repeat=len(nodes) - 1):
        for cust in itertools.product(acts, repeat=len(route)):
            cu = list(cust) + [None]
            n_plans += 1
            r = sim_plan(inst, cfg, route, legs, cu, F, E, tick_min)
            if r is not None and r[0] < best:
                best, best_plan = r[0], (legs, cu)
    return best, best_plan, n_plans


def check_brute_force(n_seeds: int = 6, n_multi: int = 2, n_unpaid: int = 4) -> None:
    """DP (exakt, eps=0) gegen Plan-Enumeration mit unabhaengigem Tick-Simulator. Erwartung: DP <= Brute-Force immer
    (DP-Raum enthaelt die enumerierten Plaene); Gleichheit, wenn der DP-Plan <= 1 Waypoint je Leg nutzt.
    Teil 1: 1 Kunde (2 Legs), 3 Ladesaeulen + 1 Relais, 5-km-Gitter, alle Kombinationen.
    Teil 2: 2 Kunden (3 Legs), 2 Ladesaeulen + 1 Relais, 10-km-Gitter, F+E und F+E+S."""
    stats = dict(cases=0, equal=0, dp_better=0, worst_gap=0.0, plans=0)
    UNPAID = replace(MINI_CFG, pause_paid=False)
    jobs = []
    for seed in range(n_seeds):
        for combo in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 1, 1)]:
            jobs.append((seed, combo, dict(n=1, ns=3, nr=1, unit=5.0), 5.0, 5.0, MINI_CFG))
    for seed in range(n_multi):
        for combo in [(1, 1, 0), (1, 1, 1)]:
            jobs.append((seed + 100, combo, dict(n=2, ns=2, nr=1, unit=10.0), 10.0, 30.0, MINI_CFG))
    for seed in range(n_unpaid):                                      # AP 0 c: unbezahlte Pflichtpause
        for combo in [(1, 0, 0), (1, 1, 0), (1, 1, 1)]:
            jobs.append((seed + 300, combo, dict(n=1, ns=3, nr=1, unit=5.0), 5.0, 5.0, UNPAID))
    for seed, combo, kw, step, tick, cfg in jobs:
        F, E, S = combo
        inst = mini_instance(seed, **kw)
        route = tuple(range(1, kw["n"] + 1))
        ev = Ev(inst, cfg, F, E, S)
        dp = ev.cost(route)
        bf, _, npl = brute_best(inst, cfg, route, F, E, S, chain=1, step=step, tick_min=tick)
        stats["cases"] += 1
        stats["plans"] += npl
        if not is_feasible(dp) and bf == INF:
            stats["equal"] += 1
            continue
        assert is_feasible(dp) or bf == INF, (seed, combo, kw, dp, bf)
        assert dp <= bf + 1e-6, f"DP schlechter als Brute-Force: seed={seed} combo={combo} {kw} dp={dp} bf={bf}"
        if dp < bf - 1e-6:
            plan = ev.plan(route)
            stats["dp_better"] += 1
            stats["worst_gap"] = max(stats["worst_gap"], bf - dp)
            nvis = sum(1 for e in plan["events"] if e[0] in ("charge", "swap"))
            assert nvis >= 2, f"DP besser als Brute-Force ohne Mehrfachwaypoint: {seed} {combo} {kw} {dp} {bf}"
        else:
            stats["equal"] += 1
    print(f"brute-force (chain<=1): {stats['cases']} Faelle ({stats['plans']} Plaene simuliert), {stats['equal']} exakt gleich, "
          f"{stats['dp_better']} DP besser (nur mit Mehrfach-Waypoints, groesste Differenz {stats['worst_gap']:.2f} EUR), nie schlechter")


def check_brute_force_chain2(n_e: int = 4, n_fe: int = 4) -> None:
    """Enumeration mit bis zu 2 Waypoints je Leg (1 Kunde, 2 Ladesaeulen): der DP muss den Enumerationswert erreichen
    (Gleichheit), nicht nur unterbieten. E allein mit 5-km-Gitter; F+E mit 25-km-Gitter (Plananzahl)."""
    cfg = MINI_CFG
    cases = 0
    jobs = [(seed + 50, (0, 1, 0), 5.0, 5.0) for seed in range(n_e)] + [(seed + 60, (1, 1, 0), 25.0, 30.0) for seed in range(n_fe)]
    for seed, combo, unit, tick in jobs:
        F, E, S = combo
        inst = mini_instance(seed, n=1, ns=2, nr=0, unit=unit)
        ev = Ev(inst, cfg, F, E, S)
        dp = ev.cost((1,))
        bf, _, npl = brute_best(inst, cfg, (1,), F, E, S, chain=2, step=unit, tick_min=tick)
        cases += 1
        if bf == INF:
            assert not is_feasible(dp)
            continue
        assert abs(dp - bf) < 1e-6, (seed, combo, dp, bf)
    print(f"brute-force (chain<=2, 1 Kunde, 2 Ladesaeulen): {cases} Faelle, DP == Enumeration exakt")


# ----------------------------------------------------------------------------------------------------------------
# 3. Fahrplan-Validator (unabhaengig vom DP)
# ----------------------------------------------------------------------------------------------------------------
def validate_events(inst: Inst, cfg: Cfg, route, events, F: bool, E: bool) -> None:
    D = inst.D
    t = 0.0
    dc = dd = 0.0
    b = cfg.R if E else None
    served = []
    for e in events:
        kind = e[0]
        assert e[1] >= t - 1e-6, ("Ereignisse ueberlappen", e, t)
        assert e[1] <= t + 1e-6, ("Luecke in der Zeitlinie", e, t)
        t = e[2]
        dur = e[2] - e[1]
        if kind == "drive":
            dc += dur
            dd += dur
            if E:
                b -= e[3]
                assert b >= -1e-6, ("Akku leer", e, b)
            if F:
                assert dc <= cfg.blk + 1e-6, ("Lenkzeit ohne Pause > 4,5 h", dc)
                assert dd <= cfg.day + 1e-6, ("Lenkzeit je Schicht > 9 h", dd)
        elif kind == "break":
            assert dur >= cfg.brk - 1e-6
            dc = 0.0
        elif kind == "rest":
            assert dur >= cfg.rest - 1e-6
            dc = dd = 0.0
        elif kind == "swap":
            dc = dd = 0.0
        elif kind == "charge":
            assert E, "Laden ohne E-Schalter"
            b += e[4]
            assert b <= cfg.R + 1e-6, ("Akku ueber Kapazitaet", b)
            assert dur >= e[4] * cfg.t_typ / cfg.typ_share / cfg.R - 1e-6, "Ladezeit zu kurz"
            if e[5] == "break":
                assert dur >= cfg.brk - 1e-6
                dc = 0.0
            elif e[5] == "rest":
                assert dur >= cfg.rest - 1e-6
                dc = dd = 0.0
        elif kind == "wait":
            pass
        elif kind == "serve":
            served.append(e[3])
            assert e[1] >= inst.e[e[3]] - 1e-6, "Service vor Fensteroeffnung"
            assert abs((e[2] - e[1]) - inst.svc[e[3]]) < 1e-6
    assert served == list(route), (served, route)


def check_validator_and_cost_recompute(n_inst: int = 12) -> None:
    cfg = Cfg()
    n_plans = 0
    for seed in range(n_inst):
        inst = make_instance(seed, n=12, K=2, tw_share=0.5, tw_width_h=6.0)
        rng = random.Random(seed)
        for combo in [(1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 0, 0)]:
            F, E, S = combo
            ev = Ev(inst, cfg, F, E, S)
            for _ in range(3):
                route = tuple(rng.sample(range(1, 13), rng.randint(3, 7)))
                plan = ev.plan(route)
                if plan is None:
                    assert not is_feasible(ev.cost(route))
                    continue
                validate_events(inst, cfg, route, plan["events"], F, E)
                assert abs(cost_from_events(plan["events"], cfg, inst) - plan["cost"]) < 1e-6, (seed, combo, route)
                assert abs(plan["cost"] - ev.cost(route)) < 1e-9
                n_plans += 1
    print(f"validator+nachrechnung: {n_plans} Fahrplaene (F/E/FE/FES/aus): Lenk-/Ruhezeit, Akku, Reihenfolge, Zeitlinie "
          f"lueckenlos, Kosten aus Ereignissen == DP-Kosten")


def check_dp_dominance_off(n: int = 6) -> None:
    """Dominanz darf nichts abschneiden: eps=0 mit Dominanz == ohne jede Dominanz (nur Mini-Faelle)."""
    cfg = MINI_CFG
    orig = fv_evaluator._insert
    def nodom(lst, lab, tol):
        lst.append(lab)
    cases = 0
    for seed in range(n):
        for combo in [(1, 0, 0), (1, 1, 0), (1, 1, 1), (0, 1, 0)]:
            inst = mini_instance(seed + 200, n=1, ns=2, nr=1)
            ev = Ev(inst, cfg, *combo)
            a = ev.cost((1,))
            fv_evaluator._insert = nodom
            try:
                b = Ev(inst, cfg, *combo).cost((1,))
            finally:
                fv_evaluator._insert = orig
            assert abs(a - b) < 1e-6, (seed, combo, a, b)
            cases += 1
    print(f"dominanz: {cases} Faelle, Pareto-Dominanz (eps=0) == vollstaendige Enumeration ohne Dominanz")


# ----------------------------------------------------------------------------------------------------------------
# 4. Schalter greifen
# ----------------------------------------------------------------------------------------------------------------
def line_instance(R_stations=True, relay=False, c_far=380.0) -> Inst:
    """Depot (400,400); Kunde 1 im Osten, Kunde 2 im Nordosten; Ladesaeulen/Relais laengs der Route."""
    xy = [(400, 400), (780, 400), (780, 780)]
    st = [(600, 400), (780, 590), (600, 620), (400, 600), (250, 400)] if R_stations else []
    rl = [(780, 590), (590, 590)] if relay else []
    xy += st + rl
    m = len(xy)
    D = [[math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1]) for j in range(m)] for i in range(m)]
    return Inst(n=2, K=1, Q=100, xy=xy, ns=len(st), nr=len(rl), dem=[0, 1, 1] + [0] * (len(st) + len(rl)),
                e=[0.0] * m, l=[INF] * m, svc=[0.0, 45.0, 45.0] + [0.0] * (len(st) + len(rl)), D=D)


EXACT = dict(eps_g=0.0, eps_t=0.0, eps_c=0.0, eps_b=0.0)      # exakte Pareto-Mengen (fuer Gleichheitstests)


def check_switches_bite() -> None:
    cfg = replace(Cfg(), **EXACT)
    inst = line_instance(relay=True)
    route = (1, 2)
    length = inst.D[0][1] + inst.D[1][2] + inst.D[2][0]
    base = Ev(inst, cfg)
    p0 = base.plan(route)
    s0 = plan_stats(p0["events"], cfg)
    assert s0["breaks"] == 0 and s0["nights"] == 0 and s0["charges"] == 0 and s0["swaps"] == 0
    # F: lange Tour => Pausen und Tagesruhe, teurer
    evF = Ev(inst, cfg, 1, 0, 0)
    pF = evF.plan(route)
    sF = plan_stats(pF["events"], cfg)
    assert sF["breaks"] >= 2 and sF["nights"] >= 1, sF
    assert evF.cost(route) > base.cost(route) + 100
    assert sF["nights"] == math.ceil(sF["drive_min"] / cfg.day - 1e-9) - 1, sF     # genau die noetigen Tagesruhen
    # E: R < Tourlaenge => Ladestopps noetig; ohne Ladesaeulen unmoeglich; R gross == E aus (exakt)
    evE = Ev(inst, cfg, 0, 1, 0)
    sE = plan_stats(evE.plan(route)["events"], cfg)
    assert length > cfg.R and sE["charges"] >= math.ceil(length / cfg.R) - 1 and sE["breaks"] == 0 and sE["nights"] == 0, sE
    assert evE.cost(route) > base.cost(route) + 20
    noST = line_instance(R_stations=False)
    assert not is_feasible(Ev(noST, cfg, 0, 1, 0).cost(route)), "ohne Ladesaeulen muss die lange Tour unzulaessig sein"
    assert is_feasible(Ev(noST, cfg, 0, 0, 0).cost(route))
    big = replace(cfg, R=1e7)
    assert abs(Ev(inst, big, 0, 1, 0).cost(route) - base.cost(route)) < 1e-6, "E mit riesiger Reichweite muss == E aus sein"
    # S: mit F ein Relais nutzbar (Fahrerwechsel statt Tagesruhe), ohne F wirkungslos
    cfg_s = replace(cfg, c_ret=0.05, c_swap=40.0)
    evFS = Ev(inst, cfg_s, 1, 0, 1)
    evF2 = Ev(inst, cfg_s, 1, 0, 0)
    sFS = plan_stats(evFS.plan(route)["events"], cfg_s)
    sF2 = plan_stats(evF2.plan(route)["events"], cfg_s)
    assert sFS["swaps"] >= 1 and sFS["nights"] < sF2["nights"], (sFS, sF2)
    assert evFS.cost(route) < evF2.cost(route) - 1
    assert abs(Ev(inst, cfg_s, 0, 0, 1).cost(route) - Ev(inst, cfg_s, 0, 0, 0).cost(route)) < 1e-9, "S ohne F muss wirkungslos sein"
    assert abs(Ev(inst, cfg_s, 0, 1, 1).cost(route) - Ev(inst, cfg_s, 0, 1, 0).cost(route)) < 1e-9
    print(f"schalter greifen: F -> {sF['breaks']} Pausen/{sF['nights']} Tagesruhen (aus: 0/0); E -> {sE['charges']} Ladestopps, "
          f"ohne Saeulen unzulaessig, R=1e7 == aus; S -> {sFS['swaps']} Wechsel, Tagesruhen {sF2['nights']} -> {sFS['nights']}; "
          f"S ohne F wirkungslos")


def check_unpaid_pause() -> None:
    """AP 0 c: Option Cfg.pause_paid=False. Die 45-min-Pflichtpause zaehlt nicht als Fahrerlohn (Fahrzeugzeit laeuft weiter),
    Warten/Laden ausserhalb der Pause/Service bleiben bezahlt. Test auf Handinstanz: der bisherige (bezahlte) Plan kostet unbezahlt
    GENAU Pausen x 45 min x Fahrerlohn weniger; der DP-Optimum unbezahlt ist <= dieser Wert; Standard ist bezahlt."""
    assert Cfg().pause_paid is True, "Standard muss bezahlt sein (bisheriges Verhalten)"
    inst = line_instance(relay=True)
    route = (1, 2)
    paid = replace(Cfg(), **EXACT)
    unp = replace(paid, pause_paid=False)
    per_break = paid.brk * paid.c_drv / 60.0
    out = []
    for combo in [(1, 0, 0), (1, 1, 0)]:
        ev_p, ev_u = Ev(inst, paid, *combo), Ev(inst, unp, *combo)
        plan_p = ev_p.plan(route)
        st = plan_stats(plan_p["events"], paid)
        nb = st["breaks"]
        assert nb >= 2, st
        assert abs(st["pause_min"] - nb * paid.brk) < 1e-9
        re_u = cost_from_events(plan_p["events"], unp, inst)          # derselbe Plan, unbezahlt nachgerechnet
        assert abs(re_u - (plan_p["cost"] - nb * per_break)) < 1e-6, (combo, re_u, plan_p["cost"], nb * per_break)
        dp_u = ev_u.cost(route)
        assert dp_u <= re_u + 1e-6 and dp_u < plan_p["cost"] - 1.0, (combo, dp_u, re_u)
        if combo == (1, 0, 0):                                          # nur erzwungene Pausen: Plan bleibt, Ersparnis exakt
            assert abs(dp_u - re_u) < 1e-6 and abs(ev_p.cost(route) - dp_u - nb * per_break) < 1e-6
        plan_u = ev_u.plan(route)
        validate_events(inst, unp, route, plan_u["events"], combo[0], combo[1])
        assert abs(cost_from_events(plan_u["events"], unp, inst) - plan_u["cost"]) < 1e-6
        out.append(f"{combo_name_(combo)}: {nb} Pausen x {per_break:.1f} EUR = {nb * per_break:.1f} EUR, bezahlt {plan_p['cost']:.1f} -> unbezahlt {dp_u:.1f}")
    # Zufallsrouten: Nachrechnung == DP, unbezahlt nie teurer als bezahlt
    cfg = Cfg()
    cfg_u = replace(cfg, pause_paid=False)
    n = 0
    for seed in range(6):
        inst2 = make_instance(seed, n=12, K=2, tw_share=0.5, tw_width_h=6.0)
        rng = random.Random(seed)
        for combo in [(1, 0, 0), (1, 1, 0)]:
            evp, evu = Ev(inst2, cfg, *combo), Ev(inst2, cfg_u, *combo)
            for _ in range(3):
                r = tuple(rng.sample(range(1, 13), rng.randint(3, 6)))
                pu = evu.plan(r)
                if pu is None:
                    continue
                validate_events(inst2, cfg_u, r, pu["events"], combo[0], combo[1])
                assert abs(cost_from_events(pu["events"], cfg_u, inst2) - pu["cost"]) < 1e-6
                assert pu["cost"] <= evp.cost(r) + 1e-6, (seed, combo, r)
                n += 1
    print("unbezahlte Pause: Standard bezahlt; Handinstanz " + "; ".join(out) + f"; {n} Zufallsrouten: Nachrechnung == DP, unbezahlt <= bezahlt; "
          f"Brute-Force-Faelle mit unbezahlter Pause siehe oben")


def combo_name_(c):
    return "".join(ch if v else "-" for ch, v in zip("FES", c))


def check_monotonicity_and_eps(n_inst: int = 10) -> None:
    """Je Route: F/E teuer als aus, FE >= F und >= E, FES <= FE (Stafette nur zusaetzliche Optionen); eps-Dominanz
    weicht hoechstens minimal vom exakten DP ab."""
    cfg = Cfg()
    cfg_ex = replace(cfg, eps_g=0.0, eps_t=0.0, eps_c=0.0, eps_b=0.0)
    worst = 0.0
    worst_rel = 0.0
    worst_mono = 0.0
    n = 0
    n_cmp = 0
    for seed in range(n_inst):
        inst = make_instance(seed, n=12, K=2, tw_share=0.5, tw_width_h=6.0)
        rng = random.Random(seed + 9)
        evs = {c: Ev(inst, cfg, *c) for c in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 1, 1)]}
        for _ in range(4):
            route = tuple(rng.sample(range(1, 13), rng.randint(3, 6)))
            c = {k: v.cost(route) for k, v in evs.items()}
            if not all(is_feasible(x) for x in c.values()):
                continue
            n += 1
            assert c[(1, 0, 0)] >= c[(0, 0, 0)] - 1e-6 and c[(0, 1, 0)] >= c[(0, 0, 0)] - 1e-6
            tol = 8.0                                 # eps-Dominanz kann Kosten je Route um wenige EUR verfaelschen (siehe unten)
            worst_mono = max(worst_mono, c[(1, 1, 1)] - c[(1, 1, 0)], max(c[(1, 0, 0)], c[(0, 1, 0)]) - c[(1, 1, 0)])
            assert c[(1, 1, 0)] >= max(c[(1, 0, 0)], c[(0, 1, 0)]) - tol, (seed, route, c)
            assert c[(1, 1, 1)] <= c[(1, 1, 0)] + tol, (seed, route, c)
            if n_cmp < 30:
                ex = Ev(inst, cfg_ex, 1, 1, 1).cost(route)
                worst = max(worst, abs(c[(1, 1, 1)] - ex))
                worst_rel = max(worst_rel, abs(c[(1, 1, 1)] - ex) / ex)
                assert c[(1, 1, 1)] >= ex - 1e-6            # eps-DP darf nie billiger sein als der exakte DP
                n_cmp += 1
    print(f"monotonie: {n} Routen (F,E >= aus; FE >= max(F,E); FES <= FE; groesste eps-bedingte Verletzung {worst_mono:.2f} EUR, "
          f"Toleranz 8 EUR); eps-DP vs exakt auf "
          f"{n_cmp} FES-Routen: groesste Abweichung {worst:.2f} EUR ({100 * worst_rel:.2f} %), nie billiger als exakt")


# ----------------------------------------------------------------------------------------------------------------
# 6. Suche
# ----------------------------------------------------------------------------------------------------------------
def check_search(n_inst: int = 3) -> None:
    cfg = Cfg()
    for seed in range(n_inst):
        inst = make_instance(seed, n=9, K=2, tw_share=0.5, tw_width_h=6.0)
        for combo in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 1)]:
            ev = Ev(inst, cfg, *combo)
            routes, c = solve(ev, seed)
            covered = sorted(x for r in routes for x in r)
            assert covered == list(range(1, inst.n + 1)), (seed, combo)
            for r in routes:
                assert sum(inst.dem[x] for x in r) <= inst.Q + 1e-9
            assert abs(c - total_cost(ev, routes)) < 1e-9
            # Kosten == Summe der Fahrplaene, nachgerechnet
            tot = 0.0
            for r in routes:
                if r:
                    p = ev.plan(r)
                    validate_events(inst, cfg, tuple(r), p["events"], *combo[:2])
                    tot += cost_from_events(p["events"], cfg, inst)
            assert abs(tot - c) < 1e-6, (seed, combo, tot, c)
            # Determinismus
            ev2 = Ev(inst, cfg, *combo)
            routes2, c2 = solve(ev2, seed)
            assert routes2 == routes and abs(c2 - c) < 1e-9
            # Suche verbessert die Konstruktionsloesung (oder ist gleich)
            assert c <= total_cost(ev, savings_routes(inst)) + 1e-9
    print(f"suche: {n_inst} Instanzen x aus/F/E/F-S (n=9): Partition, Kapazitaet, Determinismus, Kosten == nachgerechnete Fahrplaene, "
          f"LS nie schlechter als Savings")


def check_adaptation(n_seeds: int = 8) -> None:
    """Die Suche passt Touren an: bei eingeschalteten Regeln ist die neu optimierte Loesung nie schlechter als die
    unveraenderte Basisloesung unter denselben Regeln - und auf mindestens einer Instanz strikt besser."""
    cfg = Cfg()
    better = 0
    cases = 0
    for seed in range(n_seeds):
        inst = make_instance(seed, n=10, K=2, tw_share=0.6, tw_width_h=5.0)
        base_routes, _ = solve(Ev(inst, cfg), seed)
        for combo in [(1, 0, 0), (0, 1, 0)]:
            ev = Ev(inst, cfg, *combo)
            fixed = total_cost(ev, base_routes)
            re_routes, re_c = solve(ev, seed, starts=[base_routes])
            assert re_c <= fixed + 1e-6, (seed, combo, re_c, fixed)
            cases += 1
            if re_c < fixed - 1e-6:
                better += 1
    assert better > 0, "Neuoptimierung verbessert nie - Suche passt sich nicht an"
    print(f"anpassung: {cases} Faelle, Neuoptimierung nie schlechter als Nachbewertung der Basistouren, "
          f"strikt besser in {better}")


def check_solve_all(n_inst: int = 3) -> None:
    """solve_all: gueltige Partition, Kosten == nachgerechnete Fahrplaene, Pool-Konsistenz (keine Zelle ist schlechter als
    eine im Pool vorhandene Loesung unter ihrem Evaluator), daraus folgend Monotonie F,E <= FE (+eps), FES <= FE (+eps)."""
    cfg = Cfg(max_rl=4)
    combos = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 1), (1, 1, 1)]
    for i in range(n_inst):
        inst = make_instance(3 * i + 1, n=9, K=2, cfg=cfg, tw_share=0.5, tw_width_h=6.0)
        out, pool = solve_all(inst, cfg, combos, i, restarts=2)
        for c, (routes, cost, ev) in out.items():
            assert sorted(x for r in routes for x in r) == list(range(1, inst.n + 1))
            assert all(sum(inst.dem[x] for x in r) <= inst.Q + 1e-9 for r in routes)
            tot = 0.0
            for r in routes:
                if r:
                    p = ev.plan(r)
                    validate_events(inst, cfg, tuple(r), p["events"], c[0], c[1])
                    tot += cost_from_events(p["events"], cfg, inst)
            assert abs(tot - cost) < 1e-6, (i, c, tot, cost)
            assert is_feasible(cost)
            for s_ in pool.values():
                assert cost <= total_cost(ev, s_) + 1e-9, (i, c)
        tol = 3.0
        assert out[(1, 1, 0)][1] >= max(out[(1, 0, 0)][1], out[(0, 1, 0)][1]) - tol
        assert out[(1, 0, 0)][1] >= out[(0, 0, 0)][1] - tol and out[(0, 1, 0)][1] >= out[(0, 0, 0)][1] - tol
        assert out[(1, 1, 1)][1] <= out[(1, 1, 0)][1] + tol and out[(1, 0, 1)][1] <= out[(1, 0, 0)][1] + tol
    print(f"solve_all: {n_inst} Instanzen x 6 Zellen: Partition, Kapazitaet, Kosten == Fahrplaene, Pool-Konsistenz, "
          f"Monotonie F,E <= FE und S <= ohne S")
